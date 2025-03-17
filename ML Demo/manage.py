#!/usr/bin/env python3
import argparse
import logging
import sys
import os
from typing import Optional
import json
from config_utils import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def load_config() -> dict:
    """Load configuration from config.json"""
    config_manager = get_config_manager()
    return config_manager.config

def provision_services() -> None:
    """Provision all required Azure services"""
    try:
        import provision_services
        logging.info("✅ Services provisioned successfully")
    except Exception as e:
        logging.error(f"❌ Error provisioning services: {str(e)}")
        sys.exit(1)

def delete_services() -> None:
    """Delete all Azure services"""
    try:
        import delete_services
        logging.info("✅ Services deleted successfully")
    except Exception as e:
        logging.error(f"❌ Error deleting services: {str(e)}")
        sys.exit(1)

def start_services() -> None:
    """Start the Producer and Consumer services"""
    try:
        import subprocess
        import time

        # Start Producer
        producer_process = subprocess.Popen(
            [sys.executable, "Producer.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logging.info("✅ Producer service started")

        # Start Consumer
        consumer_process = subprocess.Popen(
            [sys.executable, "Consumer.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logging.info("✅ Consumer service started")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Stopping services...")
            producer_process.terminate()
            consumer_process.terminate()
            producer_process.wait()
            consumer_process.wait()
            logging.info("✅ Services stopped")

    except Exception as e:
        logging.error(f"❌ Error starting services: {str(e)}")
        sys.exit(1)

def verify_config() -> None:
    """Verify all required configuration is present"""
    try:
        config_manager = get_config_manager()
        required_settings = [
            "AZURE_STORAGE_ACCOUNT",
            "AZURE_EVENT_HUB_NAMESPACE",
            "AZURE_FUNCTION_APP",
            "AZURE_ML_WORKSPACE"
        ]
        
        missing = config_manager.validate_required_settings(required_settings)
        if missing:
            logging.error(f"❌ Missing required settings: {', '.join(missing)}")
            logging.error("Please run provision_services.py to generate these settings")
            sys.exit(1)
        else:
            logging.info("✅ All required settings are present")
            
    except Exception as e:
        logging.error(f"❌ Error verifying configuration: {str(e)}")
        sys.exit(1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Azure ML Service Demo")
    parser.add_argument(
        "command",
        choices=["provision", "delete", "start", "verify"],
        help="Command to execute"
    )

    args = parser.parse_args()

    try:
        if args.command == "provision":
            provision_services()
        elif args.command == "delete":
            delete_services()
        elif args.command == "start":
            verify_config()  # Verify config before starting services
            start_services()
        elif args.command == "verify":
            verify_config()
    except KeyboardInterrupt:
        logging.info("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
