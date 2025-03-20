import json
import logging
import base64
import os
import time
import sys
import datetime
from PIL import Image
import azure.functions as func
from azureml.core import Workspace, Experiment
from azure.storage.blob import BlobServiceClient
from azure.eventhub import EventHubProducerClient, EventData
from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Model, ManagedOnlineEndpoint, ManagedOnlineDeployment

# Add the current directory to the path so we can import config_utils
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Import our configuration manager
from config_utils import ConfigurationManager

# Create configuration manager
config_manager = ConfigurationManager()

# Required settings for the Azure Functions
REQUIRED_SETTINGS = [
    "AZURE_BLOB_STORAGE_CONNECTION_STRING", 
    "ALPHABET_EVENT_HUB", 
    "PREDICTIONS_EVENT_HUB",
    "EventHubConnectionString", 
    "AZURE_ML_SUBSCRIPTION_ID", 
    "AZURE_ML_RESOURCE_GROUP", 
    "AZURE_ML_WORKSPACE_NAME",
    "AZURE_ML_PREDICTION_ENDPOINT",
    "AZURE_ML_KEY"
]

# Get ML workspace storage details
training_storage_info = config_manager.get_ml_workspace_storage(for_models=False)
models_storage_info = config_manager.get_ml_workspace_storage(for_models=True)
storage_account = training_storage_info["name"]
training_container_name = training_storage_info["container_name"]
models_container_name = models_storage_info["container_name"]
model_blob_path = "models/handwriting_model.keras"

print(f"Storage account: {storage_account}")
print(f"Training container: {training_container_name}")
print(f"Models container: {models_container_name}")

# Get Azure ML settings
subscription_id = config_manager.get_setting("AZURE_ML_SUBSCRIPTION_ID")
resource_group = config_manager.get_setting("AZURE_ML_RESOURCE_GROUP")
workspace_name = config_manager.get_setting("AZURE_ML_WORKSPACE_NAME")


# Validate required settings
missing_settings = config_manager.validate_required_settings(REQUIRED_SETTINGS)
if missing_settings:
    logging.error(f"Missing required settings: {', '.join(missing_settings)}")
    logging.error("Some functions may not work correctly without these settings")
else:
    logging.info("All required settings are available")

# Helper functions to get connection settings

def get_event_hub_connection(event_hub_name_key="ALPHABET_EVENT_HUB"):
    """Get Event Hub connection settings with automatic refresh"""
    event_hub_connection_str = config_manager.get_setting("EventHubConnectionString")
    event_hub_name = config_manager.get_setting(event_hub_name_key)
    
    if not event_hub_connection_str or not event_hub_name:
        logging.error(f"Event Hub connection settings are missing for {event_hub_name_key}")
        return None, None
    
    return event_hub_connection_str, event_hub_name

def get_blob_storage_connection(for_models=False):
    """
    Get Blob Storage connection settings with automatic refresh
    
    Args:
        for_models: If True, returns the models container connection instead of training data container
    
    Returns:
        Tuple of (connection_string, container_name) or (None, None) if connection fails
    """
    # Force a refresh of settings
    config_manager.refresh_config()
    
    # Get ML workspace storage details
    storage_details = config_manager.get_ml_workspace_storage(for_models=for_models)
    connection_string = storage_details.get("connection_string")
    container_name = storage_details.get("container_name")
    storage_account = storage_details.get("name")
    
    if not connection_string or not container_name:
        container_type = "Models" if for_models else "Training data"
        logging.error(f"{container_type} blob storage connection settings are missing")
        return None, None
    
    logging.info(f"Using storage account: {storage_account} with container: {container_name}")
    
    # Verify the connection string is valid
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        # Try to list containers to verify connection
        next(blob_service_client.list_containers(), None)
        logging.info("✅ Successfully connected to blob storage")
    except Exception as e:
        logging.error(f"❌ Failed to connect to blob storage: {str(e)}")
        return None, None
    
    return connection_string, container_name

def get_ml_workspace():
    """Get Azure ML workspace client"""
    try:
        credential = DefaultAzureCredential()
        subscription_id = config_manager.get_setting("AZURE_ML_SUBSCRIPTION_ID")
        resource_group = config_manager.get_setting("AZURE_ML_RESOURCE_GROUP")
        workspace_name = config_manager.get_setting("AZURE_ML_WORKSPACE_NAME")
        
        if not all([subscription_id, resource_group, workspace_name]):
            logging.error("Missing required ML workspace settings")
            return None
        
        ml_client = MLClient(
            credential=credential,
            subscription_id=subscription_id,
            resource_group_name=resource_group,
            workspace_name=workspace_name
        )
        return ml_client
    except Exception as e:
        logging.error(f"Error connecting to ML workspace: {str(e)}")
        return None

# Initialize Azure Function App
app = func.FunctionApp()

# Event Hub triggers for image storage and training data
@app.event_hub_message_trigger(arg_name="event", event_hub_name="alphabet-topic", connection="EventHubConnectionString", cardinality="one", consumer_group="image_save")
def store_training_data(event: func.EventHubEvent):
    """Store images with labels in ML workspace storage for training"""
    try:
        # Get the event data and properties
        event_body = event.get_body().decode('utf-8')
        event_properties = event.metadata.get('Properties', {})
        label = event_properties.get('label', 'unknown')
        
        # Log the incoming data
        image_size_kb = len(base64.b64decode(event_body)) / 1024
        logging.info(f"📥 Received image of size: {image_size_kb:.2f} KB with label: {label}")
        
        # Get blob storage connection for training data (not models)
        storage_connection_string, container_name = get_blob_storage_connection(for_models=False)
        if not storage_connection_string or not container_name:
            logging.error("Cannot store training data: Missing storage settings")
            return
            
        # Create a unique filename with timestamp and label
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"training_data/{label}/{timestamp}.jpg"
        
        # Connect to blob storage and ensure container exists
        blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
        container_client = blob_service_client.get_container_client(container_name)
        
        # Create container if it doesn't exist
        try:
            container_client.get_container_properties()
        except Exception:
            logging.info(f"Creating container: {container_name}")
            container_client.create_container()
        
        # Upload the image with retry logic
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                blob_client = container_client.get_blob_client(filename)
                blob_client.upload_blob(base64.b64decode(event_body), overwrite=True)
                logging.info(f"✅ Stored training image with label '{label}' as {filename}")
                break
            except Exception as upload_error:
                if attempt == max_retries - 1:  # Last attempt
                    raise upload_error
                logging.warning(f"Upload attempt {attempt + 1} failed: {str(upload_error)}")
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
        
    except Exception as e:
        logging.error(f"❌ Error storing training data: {str(e)}")

# Event Hub trigger for image prediction
@app.event_hub_message_trigger(arg_name="event", event_hub_name="alphabet-topic", connection="EventHubConnectionString", cardinality="one", consumer_group="image_prediction")
def process_single_image(event: func.EventHubEvent):
    """Process image for prediction (strips label) and sends to ML endpoint"""
    try:
        # Get the event data and properties
        event_body = event.get_body().decode('utf-8')
        event_properties = event.metadata.get('Properties', {})
        label = event_properties.get('label', 'unknown')
        
        # Log the original image and label
        image_size_kb = len(base64.b64decode(event_body)) / 1024
        logging.info(f"✅ Processing image of size: {image_size_kb:.2f} KB with label: {label}")
        
        # Get ML endpoint settings
        prediction_endpoint = config_manager.get_setting("AZURE_ML_PREDICTION_ENDPOINT")
        ml_key = config_manager.get_setting("AZURE_ML_KEY")
        
        if not prediction_endpoint or not ml_key:
            logging.error("Missing ML endpoint settings")
            return
            
        
        # MARK - Commented out for now as we don't have the ML endpoint
        # Send to ML endpoint for prediction
        # try:
        #     # Import here to avoid errors if package not installed
        #     from azure.ai.ml import MLClient
        #     from azure.core.credentials import AzureKeyCredential
        #     from azure.ai.ml.entities import Model, Environment, CodeConfiguration
        #     from azure.ai.ml.constants import AssetTypes
            
        #     # Create headers for the request
        #     headers = {
        #         "Authorization": f"Bearer {ml_key}",
        #         "Content-Type": "application/json"
        #     }
            
        #     # Create payload (image without label)
        #     payload = {
        #         "input_data": {
        #             "columns": ["image"],
        #             "data": [event_body]  # Send base64 image only, without label
        #         }
        #     }
            
        #     # Make prediction request
        #     import requests
        #     response = requests.post(
        #         prediction_endpoint,
        #         headers=headers,
        #         json=payload
        #     )
            
            
        #     # if response.status_code == 200:
        #     #     prediction_result = response.json()
                
        #     #     # Send prediction results to predictions event hub
        #     #     event_hub_connection_str, predictions_event_hub = get_event_hub_connection("PREDICTIONS_EVENT_HUB")
                
        #     #     if event_hub_connection_str and predictions_event_hub:
        #     #         producer = EventHubProducerClient.from_connection_string(
        #     #             conn_str=event_hub_connection_str,
        #     #             eventhub_name=predictions_event_hub
        #     #         )
                    
        #     #         # Create result payload
        #     #         result_payload = {
        #     #             "timestamp": datetime.datetime.now().isoformat(),
        #     #             "original_label": label,
        #     #             "prediction": prediction_result,
        #     #             "image_size_kb": image_size_kb
        #     #         }
                    
        #     #         # Send to predictions event hub
        #     #         with producer:
        #     #             event_data = EventData(json.dumps(result_payload))
        #     #             producer.send_batch([event_data])
                        
        #     #         logging.info(f"✅ Prediction results sent to Event Hub: {result_payload}")
        #     #     else:
        #     #         logging.error("Cannot send prediction: Event Hub settings missing")
        #     # else:
        #     #     logging.error(f"ML endpoint returned status code: {response.status_code}")
                
        # except Exception as ml_error:
        #     logging.error(f"Error calling ML endpoint: {str(ml_error)}")
            
    except Exception as e:
        logging.error(f"❌ Error in prediction processing: {str(e)}")

def deploy_model(blob_name: str, ml_client: MLClient) -> bool:
    """
    Deploy a model from blob storage to Azure ML.
    
    Args:
        blob_name: Name of the blob containing the model
        ml_client: Azure ML client
        
    Returns:
        bool: True if deployment was successful, False otherwise
    """
    try:
        # Get datastore name from config
        model_datastore = config_manager.get_setting("AZURE_MODEL_DATASTORE_NAME")
        if not model_datastore:
            logging.error("❌ Model datastore name not configured")
            return False

        # Extract model version from blob name (e.g., handwriting_model.keras -> handwriting_model)
        model_version = blob_name.split("/")[-1].replace(".keras", "")
        
        # Verify the model exists in the datastore
        try:
            # List datastores to verify access
            datastores = ml_client.datastores.list()
            if model_datastore not in [ds.name for ds in datastores]:
                logging.error(f"❌ Datastore {model_datastore} not found in workspace")
                return False
            logging.info(f"✅ Found datastore: {model_datastore}")
        except Exception as e:
            logging.error(f"❌ Error accessing datastores: {str(e)}")
            return False

        # Register the model in Azure ML using the correct datastore path
        model = Model(
            name=f"handwriting-model-{model_version}",
            path=f"azureml://datastores/{model_datastore}/paths/models/{model_version}.keras",
            description=f"Handwriting recognition model {model_version}"
        )
        registered_model = ml_client.models.create_or_update(model)
        logging.info(f"✅ Model registered: {registered_model.name} ({registered_model.version})")
        
        # Create or update the endpoint
        endpoint_name = f"handwriting-endpoint-{model_version}"
        endpoint = ManagedOnlineEndpoint(
            name=endpoint_name,
            description=f"Endpoint for handwriting model {model_version}",
            auth_mode="key"
        )
        ml_client.online_endpoints.begin_create_or_update(endpoint).wait()
        logging.info(f"✅ Endpoint created/updated: {endpoint_name}")
        
        # Create deployment configuration
        deployment = ManagedOnlineDeployment(
            name=f"deployment-{model_version}",
            endpoint_name=endpoint_name,
            model=registered_model.id,
            instance_type="Standard_DS3_v2",
            instance_count=1
        )
        
        # Deploy the model
        ml_client.online_deployments.begin_create_or_update(deployment).wait()
        
        # Update traffic to point to new deployment
        endpoint.traffic = {f"deployment-{model_version}": 100}
        ml_client.online_endpoints.begin_create_or_update(endpoint).wait()
        
        logging.info(f"🚀 Model successfully deployed to {endpoint_name}")
        return True
        
    except Exception as e:
        logging.error(f"❌ Model deployment failed: {str(e)}")
        return False

@app.blob_trigger(arg_name="myblob", path="models/{name}", connection="AZURE_BLOB_STORAGE_CONNECTION_STRING")
def deploy_latest_model(myblob: func.InputStream):
    """Triggered when a new model is uploaded to Blob Storage and deploys it to Azure ML."""
    logging.info(f"📥 New model detected: {myblob.name}")
    logging.info(f"Model content length: {myblob.length} bytes")

    try:
        ml_client = get_ml_workspace()
        if not ml_client:
            logging.error("❌ Failed to get ML workspace.")
            return
 
        # Get the datastore name from config
        model_datastore = config_manager.get_setting("AZURE_MODEL_DATASTORE_NAME")
        if not model_datastore:
            logging.error("❌ Model datastore name not configured")
            return
 
        # Load model from datastore (uri_file)
        model_path = f"azureml://datastores/{model_datastore}/paths/models/{myblob.name}"
        logging.info(f"📥 Fetching model from datastore: {model_path}")
 
        # Register the model
        model = Model(
            name="digit_recognition_model",
            path=model_path,
            type="uri_file",
            description="Digit recognition model for deployment"
        )
        registered_model = ml_client.models.create_or_update(model)
        logging.info(f"✅ Model registered: {registered_model.name} ({registered_model.version})")
        
        # Deploy the model
        if deploy_model(myblob.name, ml_client):
            logging.info("✅ Model deployment completed successfully")
        else:
            logging.error("❌ Model deployment failed")
            
    except Exception as e:
        logging.error(f"❌ Error in deploy_latest_model: {str(e)}")
        logging.error(f"Stack trace: {str(e.__traceback__)}")

@app.route(route="deploy-model-manual")
def deploy_model_manual(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger endpoint for model deployment"""
    try:
        # Get model name from query parameter
        model_name = req.params.get('model')
        if not model_name:
            return func.HttpResponse(
                "Please provide a model name in the query parameters",
                status_code=400
            )

        logging.info(f"🔄 Manual deployment requested for model: {model_name}")

        # Get models container details
        storage_connection_string, container_name = get_blob_storage_connection(for_models=True)
        if not storage_connection_string or not container_name:
            return func.HttpResponse(
                "Failed to get models container connection details",
                status_code=500
            )

        # Verify the model file exists
        blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
        container_client = blob_service_client.get_container_client(container_name)
        
        try:
            blob_client = container_client.get_blob_client(f"models/{model_name}")
            properties = blob_client.get_blob_properties()
            logging.info(f"✅ Found model file: {model_name}, size: {properties.size} bytes")
        except Exception as e:
            return func.HttpResponse(
                f"Model file not found: {str(e)}",
                status_code=404
            )

        # Connect to Azure ML
        credential = DefaultAzureCredential()
        ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)
        logging.info("✅ Connected to Azure ML workspace")
        
        # Deploy the model
        if deploy_model(model_name, ml_client):
            return func.HttpResponse(
                "Model deployment completed successfully",
                status_code=200
            )
        else:
            return func.HttpResponse(
                "Model deployment failed",
                status_code=500
            )
            
    except Exception as e:
        logging.error(f"❌ Error in manual deployment: {str(e)}")
        return func.HttpResponse(
            f"Error deploying model: {str(e)}",
            status_code=500
        )

# Timer trigger for training pipeline
@app.timer_trigger(schedule="0 0 */12 * * *", arg_name="mytimer")
def train_model_on_schedule(mytimer: func.TimerRequest):
    """Automatically triggers ML training every 12 hours."""
    utc_timestamp = datetime.datetime.utcnow().isoformat()

    logging.info(f"🚀 Training pipeline triggered at {utc_timestamp}")

    try:
        # Load Azure ML Workspace
        ws = Workspace.from_config()

        # Get the registered experiment
        experiment = Experiment(ws, "train-digits-model")

        # Submit the pipeline run
        run = experiment.submit("train_model.py")

        logging.info(f"✅ Training started successfully: Run ID {run.id}")

    except Exception as e:
        logging.error(f"❌ Error starting training pipeline: {str(e)}")

# Health check endpoint
@app.route(route="health")
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint for the Azure Functions"""
    try:
        # Check Event Hub connection
        alphabet_connection, alphabet_hub = get_event_hub_connection("ALPHABET_EVENT_HUB")
        predictions_connection, predictions_hub = get_event_hub_connection("PREDICTIONS_EVENT_HUB")
        
        # Check both Blob Storage connections
        training_connection, training_container = get_blob_storage_connection(for_models=False)
        models_connection, models_container = get_blob_storage_connection(for_models=True)
        
        # Check ML workspace
        ml_client = get_ml_workspace()
        
        # Prepare health status
        health_status = {
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat(),
            "connections": {
                "event_hub_alphabet": alphabet_connection is not None and alphabet_hub is not None,
                "event_hub_predictions": predictions_connection is not None and predictions_hub is not None,
                "training_blob_storage": training_connection is not None and training_container is not None,
                "models_blob_storage": models_connection is not None and models_container is not None,
                "ml_workspace": ml_client is not None
            }
        }
        
        # Determine overall status
        if not all(health_status["connections"].values()):
            health_status["status"] = "degraded"
            
        return func.HttpResponse(
            json.dumps(health_status),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        error_status = {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }
        return func.HttpResponse(
            json.dumps(error_status),
            mimetype="application/json",
            status_code=500
        )
