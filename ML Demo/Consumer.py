from azure.eventhub import EventHubConsumerClient
import base64
import os

EVENT_HUB_CONNECTION_STR = "Endpoint=sb://crav-eventhub.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=B8hY9hRcZLOcYTzYhklGCXCYCHEF0FCFY+AEhMbBz8k="
EVENT_HUB_NAME = "alphabet-topic"
CONSUMER_GROUP = "$Default"
SAVE_DIR = "received_images"  # Directory to store received images

# Ensure save directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

# Function to generate unique filename
def get_unique_filename():
    existing_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".jpg")]
    next_index = len(existing_files) + 1
    return os.path.join(SAVE_DIR, f"received_image_{next_index}.jpg")

def on_event(partition_context, event):
    print(f"✅ Received event from partition {partition_context.partition_id}")

    try:
        # Ensure data is received as a base64 string
        image_data_base64 = event.body_as_str()
        print(f"🔹 Received Base64 (First 200 chars): {image_data_base64[:200]}")

        # Decode the Base64 Image
        binary_image = base64.b64decode(image_data_base64)

        # Generate unique filename
        image_path = get_unique_filename()

        # Save the decoded image
        with open(image_path, "wb") as image_file:
            image_file.write(binary_image)

        print(f"✅ Image successfully saved as {image_path}")

    except Exception as e:
        print(f"❌ Error decoding image: {str(e)}")

    partition_context.update_checkpoint(event)  # Checkpoint the event

consumer = EventHubConsumerClient.from_connection_string(
    EVENT_HUB_CONNECTION_STR, consumer_group=CONSUMER_GROUP, eventhub_name=EVENT_HUB_NAME
)

print("🔄 Listening for events...")

with consumer:
    consumer.receive(
        on_event=on_event,
        starting_position="-1",  # Start from the beginning
    )