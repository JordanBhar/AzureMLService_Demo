import azure.functions as func
import logging
import base64
import json
import requests  # To send data to Azure ML
from PIL import Image
import io

app = func.FunctionApp()

# Define Azure ML Endpoint (Modify this with your actual endpoint)
AZURE_ML_ENDPOINT = "https://your-ml-service-endpoint.com/predict"
AZURE_ML_API_KEY = "your-ml-api-key"  # If authentication is required

# Event Hub Trigger Function
@app.event_hub_message_trigger(
    arg_name="azeventhub",
    event_hub_name="alphabet-topic",  # Listening to raw image topic
    connection="CRAVEventHub_RootManageSharedAccessKey_EVENTHUB"
)
def ImageHub_ImageProduced_trigger(azeventhub: func.EventHubEvent):
    try:
        # Decode Image Data
        event_body = azeventhub.get_body()
        logging.info("Received event from Event Hub.")

        # Convert binary event body to image
        image = Image.open(io.BytesIO(event_body))
        logging.info(f"Image Received - Format: {image.format}, Size: {image.size}")

        # Convert image to base64 for ML processing
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # Send to Azure ML for Prediction
        payload = {"image_data": encoded_image}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {AZURE_ML_API_KEY}"}
        response = requests.post(AZURE_ML_ENDPOINT, json=payload, headers=headers)

        if response.status_code == 200:
            prediction = response.json().get("prediction", "unknown")
            logging.info(f"ML Prediction: {prediction}")

            # Send prediction result to another Event Hub
            send_to_event_hub(prediction)

        else:
            logging.error(f"ML Model Error: {response.text}")

    except Exception as e:
        logging.error(f"Error processing image: {e}")

# Function to Send Predictions to the "predictions-topic"
def send_to_event_hub(prediction):
    from azure.eventhub import EventHubProducerClient, EventData

    try:
        producer = EventHubProducerClient.from_connection_string(
            "Endpoint=sb://crav-eventhub.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=your-key-here;",
            eventhub_name="predictions-topic"
        )
        with producer:
            event_data_batch = producer.create_batch()
            event_data_batch.add(EventData(json.dumps({"prediction": prediction})))
            producer.send_batch(event_data_batch)
            logging.info("Prediction sent to Event Hub")

    except Exception as e:
        logging.error(f"Failed to send prediction to Event Hub: {e}")