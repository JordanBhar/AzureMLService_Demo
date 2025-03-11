import azure.functions as func
import requests
import json
import logging
import base64
import io
import datetime
from PIL import Image
from azure.storage.blob import BlobServiceClient
from azure.eventhub import EventHubProducerClient, EventData
from apscheduler.schedulers.background import BackgroundScheduler

# Load config from JSON instead of environment variables
def load_config(json_path="local.settings.json"):
    try:
        with open(json_path, "r") as config_file:
            config = json.load(config_file)
            return config.get("Values", {})
    except Exception as e:
        raise RuntimeError(f"Error loading config: {str(e)}")

CONFIG = load_config()

# Initialize Azure Function App
app = func.FunctionApp()

# Initialize the scheduler to run the training function every 12 hours
scheduler = BackgroundScheduler()

# Initialize Azure Blob Storage client
BLOB_STORAGE_CONNECTION_STRING = CONFIG.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(BLOB_STORAGE_CONNECTION_STRING)



@app.event_hub_message_trigger(arg_name="event", event_hub_name=CONFIG.get("ALPHABET_EVENT_HUB"), connection="EventHubConnectionString")
def process_single_image(event: func.EventHubEvent):
    """
    Process a single image event from Event Hub:
    1. Log the received image data for testing
    2. [TODO] Send the image to Azure ML for inference (commented out for now)
    3. [TODO] Send the prediction results to another Event Hub (commented out for now)
    
    Note: Image storage is handled automatically by Azure Event Hubs capture
    """
    try:
        # Get the event data
        base64_data = event.get_body().decode("utf-8")
        image_data = base64.b64decode(base64_data)
        
        # Log information about the received image
        image_size_kb = len(image_data) / 1024
        timestamp = datetime.datetime.now().isoformat()
        logging.info(f"✅ Received image from Event Hub at {timestamp}")
        logging.info(f"✅ Image size: {image_size_kb:.2f} KB")
        
    except Exception as e:
        logging.error(f"❌ Unexpected error in single image processing: {str(e)}")


# Optional: Create a function that can be triggered manually to start training
@app.route(route="manual-training")
def manual_training_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger function that allows manual triggering of the training process.
    This can be called via an HTTP request to start training on demand.
    """
    logging.info("Manual training triggered via HTTP request")
    
    try:
        train_model_from_blob_storage()
        return func.HttpResponse(
            "Training process started successfully",
            status_code=200
        )
    except Exception as e:
        return func.HttpResponse(
            f"Error starting training process: {str(e)}",
            status_code=500
        )

#
# FUNCTION 1: SINGLE IMAGE PREDICTION
#

def call_azure_ml(image_data):
    """
    Send image data directly to Azure ML for inference.
    """
    # ===== TODO: IMPLEMENT ML PREDICTION ENDPOINT CALL =====
    # This function will be implemented later to call the Azure ML endpoint
    # for image prediction. For now, it's commented out for testing.
    
    ml_endpoint = CONFIG.get("AZURE_ML_PREDICTION_ENDPOINT")
    ml_key = CONFIG.get("AZURE_ML_KEY")

    if not ml_endpoint or not ml_key:
        logging.error("Missing Azure ML endpoint or key in config.")
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ml_key}"
    }
    
    payload = {"input_data": {"image": image_data.decode("latin1")}}

    try:
        response = requests.post(ml_endpoint, headers=headers, json=payload)
        response.raise_for_status()
        prediction_result = response.json()
        logging.info(f"✅ ML Prediction: {prediction_result}")
        return prediction_result
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Azure ML request failed: {e}")
        return None
    
    # For testing, return a mock prediction result
    logging.info("⚠️ Using mock prediction (ML endpoint call is disabled)")
    return {"prediction": "mock_result", "confidence": 0.95}

#
# FUNCTION 2: BATCH TRAINING (EVERY 12 HOURS)
#

def train_model_from_blob_storage():
    """
    Fetch all images from blob storage and log their details for training simulation.
    This function runs every 12 hours.
    """
    container_name = "inference-images"
    container_client = blob_service_client.get_container_client(container_name)

    try:
        logging.info(f"🔄 Starting blob storage training simulation at {datetime.datetime.now().isoformat()}")
        
        blob_list = list(container_client.list_blobs())
        
        if not blob_list:
            logging.info("⚠️ No images found in blob storage.")
            return
        
        logging.info(f"✅ Simulating sending {len(blob_list)} images for training:")
        for index, blob in enumerate(blob_list):
            logging.info(f"  {index+1}. {blob.name} - {blob.size/1024:.2f} KB - Last modified: {blob.last_modified}")
            
        logging.info("✅ Training simulation completed.")
        
    except Exception as e:
        logging.error(f"❌ Error during training simulation: {e}")



scheduler.add_job(manual_training_trigger, "interval", minutes=1)
scheduler.start()
logging.info("🔄 Scheduler initialized - Blob storage check will run every 1 minute")
