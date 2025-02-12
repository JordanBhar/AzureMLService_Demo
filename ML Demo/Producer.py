from flask import Flask, request, jsonify
from flask_cors import CORS
from azure.eventhub import EventHubProducerClient, EventData
from PIL import Image
import pillow_heif  # HEIC Support
import base64
import io

app = Flask(__name__)
CORS(app)

EVENT_HUB_CONNECTION_STR = "Endpoint=sb://crav-eventhub.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=B8hY9hRcZLOcYTzYhklGCXCYCHEF0FCFY+AEhMbBz8k="
EVENT_HUB_NAME = "alphabet-topic"

@app.route("/upload", methods=["POST"])
def upload_images():
    try:
        data = request.json
        if not data or "images" not in data:
            return jsonify({"error": "No image data received"}), 400  

        images_data = data["images"]  # Expecting a list of Base64 images

        if not isinstance(images_data, list) or len(images_data) == 0:
            return jsonify({"error": "Invalid image format. Expected a list of images"}), 400

        # Initialize EventHub Producer
        producer = EventHubProducerClient.from_connection_string(EVENT_HUB_CONNECTION_STR, eventhub_name=EVENT_HUB_NAME)

        for index, image_data in enumerate(images_data):
            print(f"🔹 Processing Image {index + 1}/{len(images_data)}")

            # Extract Base64 payload (Remove header if present)
            if "," in image_data:
                header, image_data = image_data.split(",", 1)
                print(f"🔹 Detected Header: {header}")
            else:
                header = ""

            # Decode Base64
            decoded_image = base64.b64decode(image_data)

            # Convert HEIC if necessary
            if "heic" in header.lower():
                print("🔄 Converting HEIC to JPEG...")
                heif_image = pillow_heif.open_heif(io.BytesIO(decoded_image))
                image = Image.frombytes(heif_image.mode, heif_image.size, heif_image.data)
                print("✅ HEIC converted to JPEG")
            else:
                # Open Image Normally
                image = Image.open(io.BytesIO(decoded_image))

            # Compress Image and Convert to Base64
            compressed_io = io.BytesIO()
            image.save(compressed_io, format="JPEG", quality=50)
            compressed_base64 = base64.b64encode(compressed_io.getvalue()).decode()

            # Send each image as a **separate message**
            with producer:
                event_data = EventData(compressed_base64)
                producer.send_batch([event_data])  # Sending single image as one event

            print(f"✅ Image {index + 1} sent to Event Hub successfully!")

        return jsonify({"message": f"Successfully sent {len(images_data)} images to Event Hub!"}), 200

    except Exception as e:
        print("❌ Error:", str(e))
        return jsonify({"error": str(e)}), 400  

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)