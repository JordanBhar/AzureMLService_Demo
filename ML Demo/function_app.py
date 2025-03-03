import azure.functions as func
import requests
import os
import json
import logging
import base64
import io
from PIL import Image
import pillow_heif  # For HEIF/HEIC support
from azure.eventhub import EventHubProducerClient, EventData

# ✅ Define the FunctionApp instance
app = func.FunctionApp()

# ✅ Ensure correct Event Hub name and connection settings
@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="alphabet-topic",  # ✅ Using the alphabet-topic
    connection="EventHubConnectionString"  # ✅ Using CRAV EventHub connection string
)
def main(event: func.EventHubEvent):
    """
    Azure Function triggered by Event Hub (alphabet-topic in CRAV-EventHub).
    Processes an image from the event message, sends it to Azure Custom Vision,
    and forwards the prediction to the predictions-topic Event Hub.
    """
    try:
        # Get the raw event body
        raw_event_body = event.get_body()
        
        # Try to decode as UTF-8 (assuming it's base64-encoded image data)
        try:
            # Decode the message as UTF-8 (it should be base64-encoded)
            base64_data = raw_event_body.decode("utf-8")
            logging.info(f"Received base64 data of length: {len(base64_data)}")
            
            # Decode the base64 data to get the binary image data
            image_data = base64.b64decode(base64_data)
            logging.info(f"Decoded binary data of length: {len(image_data)}")
            
            # Save the image locally
            filename = "received_image.jpg"
            save_path = os.path.join(os.getcwd(), filename)
            
            # Try to open the image with Pillow to handle different formats
            try:
                # First try to open as HEIF/HEIC
                try:
                    heif_image = pillow_heif.open_heif(io.BytesIO(image_data))
                    image = Image.frombytes(heif_image.mode, heif_image.size, heif_image.data)
                    logging.info("Successfully processed HEIF/HEIC image")
                except Exception as heif_error:
                    logging.info(f"Not a HEIF/HEIC image or error processing: {str(heif_error)}")
                    # If not HEIF/HEIC, try to open with regular PIL
                    image = Image.open(io.BytesIO(image_data))
                    logging.info("Successfully opened image with PIL")
                
                # Save the image as JPEG
                image.save(save_path, format="JPEG")
                logging.info(f"Image saved locally at: {save_path}")
                
            except Exception as img_error:
                logging.error(f"Error processing image data: {str(img_error)}")
                # If we can't process with PIL, just save the raw binary data
                with open(save_path, "wb") as file:
                    file.write(image_data)
                logging.info(f"Raw binary data saved locally at: {save_path}")
                
        except UnicodeDecodeError as e:
            # If we can't decode as UTF-8, it might be raw binary data
            logging.info(f"Event doesn't appear to be UTF-8 encoded: {str(e)}. Treating as raw binary data.")
            
            # Save the binary data directly as an image
            filename = "direct_image.jpg"
            save_path = os.path.join(os.getcwd(), filename)
            
            with open(save_path, "wb") as file:
                file.write(raw_event_body)
                
            logging.info(f"Raw binary data saved locally at: {save_path}")
        
        # ✅ Fetch Custom Vision credentials from environment variables
        endpoint = os.getenv("CustomVisionEndpoint")
        project_id = os.getenv("CustomVisionProjectId")
        prediction_key = os.getenv("CustomVisionPredictionKey")
        
        if not all([endpoint, project_id, prediction_key]):
            logging.error("Missing Azure Custom Vision credentials in environment variables")
            return
        
        # ✅ Send the image to Azure Custom Vision for prediction
        # We'll use the image file API instead of the URL API
        url = f"{endpoint}/customvision/v3.0/Prediction/{project_id}/classify/iterations/Iteration1/image"
        headers = {
            "Prediction-Key": prediction_key,
            "Content-Type": "application/octet-stream",
        }
        
        # Read the saved image file
        with open(save_path, "rb") as image_file:
            image_data = image_file.read()
        
        try:
            # Send the image data directly to Custom Vision
            response = requests.post(url, headers=headers, data=image_data)
            response.raise_for_status()
            result = response.json()
            logging.info(f"Prediction Result: {json.dumps(result, indent=4)}")
            
            # Extract the top prediction
            if "predictions" in result and len(result["predictions"]) > 0:
                top_prediction = result["predictions"][0]
                prediction_text = f"Predicted: {top_prediction['tagName']} ({top_prediction['probability']:.2f})"
                logging.info(f"Top prediction: {prediction_text}")
                
                # Send the prediction to the predictions-topic Event Hub
                try:
                    # Get the Event Hub connection string from environment variables
                    event_hub_conn_str = os.getenv("EventHubConnectionString")
                    if not event_hub_conn_str:
                        logging.error("Missing EventHubConnectionString environment variable")
                        return
                    
                    # Initialize EventHub Producer for predictions-topic
                    producer = EventHubProducerClient.from_connection_string(
                        event_hub_conn_str, 
                        eventhub_name="predictions-topic"
                    )
                    
                    # Send the prediction as an event
                    with producer:
                        event_data = EventData(prediction_text)
                        producer.send_batch([event_data])
                    
                    logging.info(f"Prediction sent to predictions-topic Event Hub: {prediction_text}")
                    
                except Exception as eh_error:
                    logging.error(f"Error sending prediction to Event Hub: {str(eh_error)}")
            else:
                logging.warning("No predictions found in the result")
                
        except requests.RequestException as e:
            logging.error(f"Error calling Azure Custom Vision API: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"Response status: {e.response.status_code}")
                logging.error(f"Response text: {e.response.text}")
            return
        
        return func.HttpResponse(json.dumps(result), mimetype="application/json")
        
    except Exception as e:
        logging.error(f"Unexpected error in function: {str(e)}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
