import json
import os
import logging
import time
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ConfigurationManager:
    """
    Utility class for managing configuration across the application.
    Handles loading from config.json and local.settings.json with validation and refresh capabilities.
    """
    
    def __init__(self, config_path: str = "config.json", settings_path: str = "local.settings.json"):
        self.config_path = config_path
        self.settings_path = settings_path
        self.config = {}
        self.settings = {}
        self.last_refresh_time = 0
        self.refresh_interval = 60  # Refresh settings every 60 seconds
        
        # Load initial configuration
        self.refresh_config()
    
    def refresh_config(self) -> None:
        """
        Reload configuration from files if the refresh interval has passed.
        """
        current_time = time.time()
        if current_time - self.last_refresh_time > self.refresh_interval:
            self._load_config()
            self._load_settings()
            self.last_refresh_time = current_time
    
    def _load_config(self) -> None:
        """
        Load configuration from config.json
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as config_file:
                    self.config = json.load(config_file)
                logging.info(f"Loaded configuration from {self.config_path}")
            else:
                logging.warning(f"Configuration file {self.config_path} not found")
        except Exception as e:
            logging.error(f"Error loading configuration from {self.config_path}: {str(e)}")
    
    def _load_settings(self) -> None:
        """
        Load settings from local.settings.json
        """
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, "r") as settings_file:
                    settings_data = json.load(settings_file)
                    self.settings = settings_data.get("Values", {})
                logging.info(f"Loaded settings from {self.settings_path}")
            else:
                logging.warning(f"Settings file {self.settings_path} not found")
        except Exception as e:
            logging.error(f"Error loading settings from {self.settings_path}: {str(e)}")
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value with optional refresh and default value.
        
        Args:
            key: The setting key to retrieve
            default: Default value if the key is not found
            
        Returns:
            The setting value or the default if not found
        """
        self.refresh_config()
        return self.settings.get(key, default)
    
    def get_config(self, *keys: str, default: Any = None) -> Any:
        """
        Get a nested configuration value with optional default.
        
        Args:
            *keys: A sequence of keys to navigate the nested configuration
            default: Default value if the path is not found
            
        Returns:
            The configuration value or the default if not found
        """
        self.refresh_config()
        
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def validate_required_settings(self, required_keys: List[str]) -> List[str]:
        """
        Validate that all required settings are present.
        
        Args:
            required_keys: List of required setting keys
            
        Returns:
            List of missing keys
        """
        self.refresh_config()
        missing_keys = []
        
        for key in required_keys:
            if key not in self.settings or not self.settings[key]:
                missing_keys.append(key)
        
        return missing_keys
    
    def get_connection_info(self) -> Dict[str, str]:
        """
        Get a dictionary of all connection-related settings.
        
        Returns:
            Dictionary of connection settings
        """
        self.refresh_config()
        
        connection_keys = [
            "EventHubConnectionString",
            "ALPHABET_EVENT_HUB",
            "PREDICTIONS_EVENT_HUB",
            "AZURE_BLOB_STORAGE_CONNECTION_STRING",
            "AZURE_ML_PREDICTION_ENDPOINT",
            "AZURE_ML_TRAINING_ENDPOINT",
            "AZURE_ML_KEY"
        ]
        
        return {key: self.settings.get(key, "") for key in connection_keys}

# Create a singleton instance for global use
config_manager = ConfigurationManager()

def get_config_manager() -> ConfigurationManager:
    """
    Get the singleton ConfigurationManager instance.
    
    Returns:
        The ConfigurationManager instance
    """
    return config_manager
