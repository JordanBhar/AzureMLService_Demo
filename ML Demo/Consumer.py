from flask import Flask, jsonify
from flask_cors import CORS
from azure.eventhub import EventHubConsumerClient
import threading

app = Flask(__name__)
CORS(app)

# Azure Event Hub Config (for predictions)
EVENT_HUB_CONNECTION_STR = "Endpoint=sb://crav-eventhub.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=B8hY9hRcZLOcYTzYhklGCXCYCHEF0FCFY+AEhMbBz8k="
EVENT_HUB_NAME = "predictions-topic"  # Now listening to the predictions
CONSUMER_GROUP = "$Default"

# Store received predictions and track which ones have been delivered
received_predictions = []
delivered_predictions = set()

def on_event(partition_context, event):
    global received_predictions
    prediction = event.body_as_str()

    print(f"✅ Received Prediction: {prediction}")

    # Append the new prediction to the list
    received_predictions.append(prediction)

    partition_context.update_checkpoint(event)  # Checkpoint the event

# Flask Route to send predictions to the webpage
@app.route("/messages", methods=["GET"])
def get_messages():
    global received_predictions, delivered_predictions
    
    # Get only predictions that haven't been delivered yet
    new_predictions = [p for p in received_predictions if p not in delivered_predictions]
    
    # Mark these predictions as delivered
    delivered_predictions.update(new_predictions)
    
    # Return all predictions for reference, but also flag which ones are new
    return jsonify({
        "all_messages": received_predictions,
        "new_messages": new_predictions
    })

# Start Event Hub consumer in a separate thread
def start_consumer():
    consumer = EventHubConsumerClient.from_connection_string(
        EVENT_HUB_CONNECTION_STR, consumer_group=CONSUMER_GROUP, eventhub_name=EVENT_HUB_NAME
    )
    print("� Listening for predictions...")
    with consumer:
        consumer.receive(on_event=on_event, starting_position="-1")

# Start Flask server and consumer in parallel
if __name__ == "__main__":
    threading.Thread(target=start_consumer, daemon=True).start()
    app.run(host="0.0.0.0", port=5002, debug=True)
