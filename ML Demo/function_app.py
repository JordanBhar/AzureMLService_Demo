import azure.functions as func
import logging

app = func.FunctionApp()

@app.event_hub_message_trigger(
    arg_name="azeventhub",
    event_hub_name="alphabet-topic",
    connection="CRAVEventHub_RootManageSharedAccessKey_EVENTHUB"
)
def ImageHub_ImageProduced_trigger(azeventhub: func.EventHubEvent):
    logging.info("✅ EventHub Triggered! Processing event...")
    logging.info("Received event: %s", azeventhub.get_body().decode('utf-8'))