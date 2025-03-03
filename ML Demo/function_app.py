import azure.functions as func
import requests
import json
import logging
import base64
import io
import datetime
from PIL import Image
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.cognitiveservices.vision.customvision.prediction import CustomVisionPredictionClient
from msrest.authentication import ApiKeyCredentials
from azure.eventhub import EventHubProducerClient, EventData

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

def get_custom_vision_client(endpoint, key):
    """
    Create a Custom Vision prediction client.
    The endpoint should be the base endpoint without the project ID.
    Example: https://southcentralus.api.cognitive.microsoft.com/
    """
    # Ensure the endpoint ends with a slash
    if not endpoint.endswith('/'):
        endpoint += '/'
        
    credentials = ApiKeyCredentials(in_headers={"Prediction-Key": key, "Ocp-Apim-Subscription-Key": key})
    return CustomVisionPredictionClient(endpoint, credentials)

def upload_image_to_blob(image_data, container_name, blob_name):
    """
    Upload image to blob storage for archiving purposes.
    Note: For training Custom Vision models, images should be manually uploaded 
    through the Azure Custom Vision portal (https://www.customvision.ai/).
    """
    blob_connection_string = CONFIG.get("AzuriteConnectionString")
    if not blob_connection_string:
        logging.error("AzuriteConnectionString is missing in JSON config.")
        return
    blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
    container_client = blob_service_client.get_container_client(container_name)
    container_client.upload_blob(blob_name, image_data, overwrite=True, content_settings=ContentSettings(content_type="image/jpeg"))
    logging.info(f"Image uploaded to blob storage: {blob_name}")

@app.event_hub_message_trigger(arg_name="event", event_hub_name=CONFIG.get("EVENT_HUB_NAME"), connection="EventHubConnectionString")
def main(event: func.EventHubEvent):
    """
    Process images from Event Hub:
    1. Save the image locally and to blob storage
    2. Use the Custom Vision Prediction API to classify the image
    3. Send the prediction results to another Event Hub

    Note: This function only handles prediction. For training the Custom Vision model,
    use the Azure Custom Vision portal (https://www.customvision.ai/) to manually
    upload and tag images, then train and publish the model.
    """
    try:
        base64_data = event.get_body().decode("utf-8")
        image_data = base64.b64decode(base64_data)

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"received_image_{timestamp}.jpg"
        save_path = f"/tmp/{filename}"  # Use /tmp for Azure Functions compatibility

        try:
            image = Image.open(io.BytesIO(image_data))
            image.save(save_path, format="JPEG")
            logging.info(f"Image saved at: {save_path}")
        except Exception as e:
            logging.error(f"Error saving image: {str(e)}")
            return

        # Save image to blob storage for archiving or later manual training
        upload_image_to_blob(image_data, "training-images", filename)

        # Fetch Custom Vision API details from JSON config
        prediction_endpoint = CONFIG.get("VISION_PREDICTION_ENDPOINT")
        project_id = CONFIG.get("CustomVisionProjectId")
        prediction_key = CONFIG.get("VISION_PREDICTION_KEY")

        if not all([prediction_endpoint, project_id, prediction_key]):
            logging.error("Missing Custom Vision API configuration")
            return

        # Fix the endpoint URL format - it should be the base URL without the trailing path
        # Example: https://southcentralus.api.cognitive.microsoft.com/
        base_endpoint = prediction_endpoint
        if "customvision/v3.0/Prediction/" in base_endpoint:
            base_endpoint = base_endpoint.split("customvision")[0]
            logging.info(f"Adjusted base endpoint to: {base_endpoint}")

        try:
            predictor = get_custom_vision_client(base_endpoint, prediction_key)
            published_name = CONFIG.get("CustomVisionPublishedName", "Iteration1")
            
            # Log the parameters being used
            logging.info(f"Making prediction with: Project ID: {project_id}, Published Name: {published_name}")
            
            # Use a try block specifically for the API call
            try:
                results = predictor.classify_image(project_id, published_name, image_data)
                logging.info("Custom Vision API call successful")
            except Exception as api_error:
                logging.error(f"Custom Vision API error: {str(api_error)}")
                # Try with a different method if the first one fails
                try:
                    logging.info("Attempting alternative method with image URL...")
                    # This is a fallback in case the direct image data method fails
                    blob_url = f"http://127.0.0.1:10000/devstoreaccount1/training-images/{filename}"
                    results = predictor.classify_image_url(project_id, published_name, {"url": blob_url})
                    logging.info("Custom Vision API call with URL successful")
                except Exception as url_api_error:
                    logging.error(f"Custom Vision API URL method error: {str(url_api_error)}")
                    raise
        except Exception as cv_error:
            logging.error(f"Error setting up Custom Vision client: {str(cv_error)}")
            raise

        if results.predictions:
            top_prediction = results.predictions[0]
            prediction_text = f"Predicted: {top_prediction.tag_name} ({top_prediction.probability:.2f})"
            logging.info(prediction_text)

            event_hub_conn_str = CONFIG.get("EventHubConnectionString")
            producer = EventHubProducerClient.from_connection_string(event_hub_conn_str, eventhub_name="predictions-topic")
            with producer:
                event_data = EventData(prediction_text)
                producer.send_batch([event_data])

            logging.info(f"Prediction sent to Event Hub: {prediction_text}")
        else:
            logging.warning("No predictions found.")

    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
