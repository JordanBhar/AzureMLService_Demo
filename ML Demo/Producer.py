from flask import Flask, request, jsonify
from flask_cors import CORS
from azure.eventhub import EventHubProducerClient, EventData
import base64
import io
import json
import logging
import time
from PIL import Image
import pillow_heif
from config_utils import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
CORS(app)

# Get configuration manager
config_manager = get_config_manager()

# Required settings for the Producer
REQUIRED_SETTINGS = [
    "EventHubConnectionString",
    "ALPHABET_EVENT_HUB"
]

# Validate required settings
missing_settings = config_manager.validate_required_settings(REQUIRED_SETTINGS)
if missing_settings:
    logging.error(f"Missing required settings: {', '.join(missing_settings)}")
    logging.error("Please run provision_services.py to generate these settings")
else:
    logging.info("All required settings are available")

def get_event_hub_connection():
    """Get Event Hub connection settings with automatic refresh"""
    # This will refresh the config if needed
    event_hub_connection_str = config_manager.get_setting("EventHubConnectionString")
    event_hub_name = config_manager.get_setting("ALPHABET_EVENT_HUB")
    
    if not event_hub_connection_str or not event_hub_name:
        logging.error("Event Hub connection settings are missing or invalid")
        return None, None
    
    return event_hub_connection_str, event_hub_name

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify the service is running and connected"""
    event_hub_connection_str, event_hub_name = get_event_hub_connection()
    
    if not event_hub_connection_str or not event_hub_name:
        return jsonify({
            "status": "error",
            "message": "Event Hub connection settings are missing",
            "timestamp": time.time()
        }), 500
    
    # Test Event Hub connection
    try:
        producer = EventHubProducerClient.from_connection_string(
            event_hub_connection_str, 
            eventhub_name=event_hub_name
        )
        with producer:
            # Just create and close the connection to verify it works
            pass
        
        return jsonify({
            "status": "healthy",
            "connections": {
                "event_hub": True
            },
            "timestamp": time.time()
        }), 200
    
    except Exception as e:
        logging.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }), 500

@app.route("/upload", methods=["POST"])
def upload_images():
    try:
        data = request.json
        if not data or "images" not in data:
            return jsonify({"error": "No image data received"}), 400  

        images_data = data["images"]  # Expecting a list of Base64 images
        labels = data.get("labels", [])  # Get labels if provided

        if not isinstance(images_data, list) or len(images_data) == 0:
            return jsonify({"error": "Invalid image format. Expected a list of images"}), 400

        # Ensure labels match images
        if labels and len(labels) != len(images_data):
            return jsonify({"error": "Number of labels must match number of images"}), 400

        # If no labels provided, use empty strings
        if not labels:
            labels = ["" for _ in images_data]

        # Get the latest connection settings
        event_hub_connection_str, event_hub_name = get_event_hub_connection()
        
        if not event_hub_connection_str or not event_hub_name:
            return jsonify({"error": "Event Hub connection settings are unavailable"}), 500

        # Initialize EventHub Producer
        producer = EventHubProducerClient.from_connection_string(
            event_hub_connection_str, 
            eventhub_name=event_hub_name
        )

        for index, (image_data, label) in enumerate(zip(images_data, labels)):
            logging.info(f"🔹 Processing Image {index + 1}/{len(images_data)} with label: {label}")

            # Extract Base64 payload (Remove header if present)
            if "," in image_data:
                header, image_data = image_data.split(",", 1)
                logging.info(f"🔹 Detected Header: {header}")
            else:
                header = ""

            # Decode Base64
            decoded_image = base64.b64decode(image_data)

            # Convert HEIC if necessary
            if "heic" in header.lower():
                logging.info("🔄 Converting HEIC to JPEG...")
                heif_image = pillow_heif.open_heif(io.BytesIO(decoded_image))
                image = Image.frombytes(heif_image.mode, heif_image.size, heif_image.data)
                logging.info("✅ HEIC converted to JPEG")
            else:
                # Open Image Normally
                image = Image.open(io.BytesIO(decoded_image))

            # Compress Image and Convert to Base64
            compressed_io = io.BytesIO()
            image.save(compressed_io, format="JPEG", quality=50)
            compressed_base64 = base64.b64encode(compressed_io.getvalue()).decode()

            # Send each image as a **separate message** with label property
            with producer:
                event_data = EventData(compressed_base64)
                # Add label as a property
                event_data.properties = {"label": label}
                producer.send_batch([event_data])  # Sending single image as one event

            logging.info(f"✅ Image {index + 1} with label '{label}' sent to Event Hub successfully!")

        return jsonify({"message": f"Successfully sent {len(images_data)} images to Event Hub!"}), 200

    except Exception as e:
        logging.error(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    # Validate connection settings before starting the server
    event_hub_connection_str, event_hub_name = get_event_hub_connection()
    
    if not event_hub_connection_str or not event_hub_name:
        logging.warning("Starting server with missing Event Hub settings")
        logging.warning("Please run provision_services.py to generate these settings")
    else:
        logging.info(f"Producer configured to use Event Hub: {event_hub_name}")
    
    app.run(host="0.0.0.0", port=5001, debug=True)
