from flask import Flask, jsonify
from flask_cors import CORS
from azure.eventhub import EventHubConsumerClient
import threading
import json
import logging
import time
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

# Required settings for the Consumer
REQUIRED_SETTINGS = [
    "EventHubConnectionString",
    "PREDICTIONS_EVENT_HUB",
    "CONSUMER_GROUP"
]

# Validate required settings
missing_settings = config_manager.validate_required_settings(REQUIRED_SETTINGS)
if missing_settings:
    logging.error(f"Missing required settings: {', '.join(missing_settings)}")
    logging.error("Please run provision_services.py to generate these settings")
else:
    logging.info("All required settings are available")

# Store received predictions and track which ones have been delivered
received_predictions = []
delivered_predictions = set()

# Event Hub consumer client (will be initialized in start_consumer)
consumer_client = None
consumer_thread = None

def get_event_hub_connection():
    """Get Event Hub connection settings with automatic refresh"""
    # This will refresh the config if needed
    event_hub_connection_str = config_manager.get_setting("EventHubConnectionString")
    event_hub_name = config_manager.get_setting("PREDICTIONS_EVENT_HUB")
    consumer_group = config_manager.get_setting("CONSUMER_GROUP", "$Default")
    
    if not event_hub_connection_str or not event_hub_name:
        logging.error("Event Hub connection settings are missing or invalid")
        return None, None, None
    
    return event_hub_connection_str, event_hub_name, consumer_group

def on_event(partition_context, event):
    global received_predictions
    prediction = event.body_as_str()

    logging.info(f"✅ Received Prediction: {prediction}")

    # Append the new prediction to the list
    received_predictions.append(prediction)

    partition_context.update_checkpoint(event)  # Checkpoint the event

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify the service is running and connected"""
    event_hub_connection_str, event_hub_name, consumer_group = get_event_hub_connection()
    
    if not event_hub_connection_str or not event_hub_name:
        return jsonify({
            "status": "error",
            "message": "Event Hub connection settings are missing",
            "timestamp": time.time()
        }), 500
    
    # Check if consumer thread is running
    global consumer_thread
    if consumer_thread is None or not consumer_thread.is_alive():
        return jsonify({
            "status": "error",
            "message": "Consumer thread is not running",
            "timestamp": time.time()
        }), 500
    
    return jsonify({
        "status": "healthy",
        "connections": {
            "event_hub": True,
            "consumer_thread": True
        },
        "predictions_received": len(received_predictions),
        "timestamp": time.time()
    }), 200

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
    global consumer_client
    
    # Get the latest connection settings
    event_hub_connection_str, event_hub_name, consumer_group = get_event_hub_connection()
    
    if not event_hub_connection_str or not event_hub_name or not consumer_group:
        logging.error("Cannot start consumer: Event Hub connection settings are missing")
        return
    
    try:
        # Close existing consumer if it exists
        if consumer_client:
            try:
                consumer_client.close()
                logging.info("Closed existing consumer client")
            except Exception as e:
                logging.warning(f"Error closing existing consumer: {str(e)}")
        
        # Create new consumer with latest settings
        consumer_client = EventHubConsumerClient.from_connection_string(
            event_hub_connection_str, 
            consumer_group=consumer_group, 
            eventhub_name=event_hub_name
        )
        
        logging.info(f"🔹 Listening for predictions on {event_hub_name}...")
        
        with consumer_client:
            consumer_client.receive(on_event=on_event, starting_position="-1")
    
    except Exception as e:
        logging.error(f"Error in consumer thread: {str(e)}")
        # Sleep before attempting to restart
        time.sleep(5)
        start_consumer()  # Recursive restart

# Monitor thread to ensure consumer is running
def monitor_consumer():
    global consumer_thread
    
    while True:
        # Check if consumer thread is alive
        if consumer_thread is None or not consumer_thread.is_alive():
            logging.warning("Consumer thread is not running. Restarting...")
            
            # Start a new consumer thread
            consumer_thread = threading.Thread(target=start_consumer, daemon=True)
            consumer_thread.start()
            logging.info("Consumer thread restarted")
        
        # Check for configuration changes
        config_manager.refresh_config()
        
        # Sleep for a while before checking again
        time.sleep(30)

# Start Flask server and consumer in parallel
if __name__ == "__main__":
    # Start the consumer thread
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    
    # Start the monitor thread
    monitor_thread = threading.Thread(target=monitor_consumer, daemon=True)
    monitor_thread.start()
    
    # Start the Flask server
    app.run(host="0.0.0.0", port=5002, debug=True)
