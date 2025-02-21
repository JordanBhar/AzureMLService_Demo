import azure.functions as func
import requests
import json
import logging

# Azure Vision API Credentials
VISION_ENDPOINT = "https://<your-region>.api.cognitive.microsoft.com/vision/v3.2/analyze"
VISION_KEY = "<YOUR_AZURE_VISION_API_KEY>"

# Headers for Azure Vision API
HEADERS = {
    "Ocp-Apim-Subscription-Key": VISION_KEY,
    "Content-Type": "application/octet-stream"
}

# Azure Function Triggered by Event Hub
def main(event: func.EventHubEvent):
    
    