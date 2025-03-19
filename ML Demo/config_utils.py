import json
import os
import logging
import time
import random
import string
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, TypeVar

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Type variable for generic function return type
T = TypeVar('T')

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
    
    def get_ml_workspace_storage(self) -> Dict[str, str]:
        """
        Get ML workspace's storage account details.
        
        Returns:
            Dictionary with storage account name, connection string, and container name
        """
        self.refresh_config()
        
        # Get ML workspace name
        ml_workspace_name = self.settings.get("AZURE_ML_WORKSPACE_NAME", "")
        
        # Get storage account details
        storage_account = self.settings.get("AZURE_STORAGE_ACCOUNT", "")
        connection_string = self.settings.get("AZURE_BLOB_STORAGE_CONNECTION_STRING", "")
        container_name = self.settings.get("AZURE_BLOB_CONTAINER_NAME", "")
        
        # Check if storage account is related to ML workspace
        if storage_account and ml_workspace_name and ml_workspace_name.lower() in storage_account.lower():
            return {
                "name": storage_account,
                "connection_string": connection_string,
                "container_name": container_name,
                "is_ml_workspace_storage": True
            }
        
        return {
            "name": storage_account,
            "connection_string": connection_string,
            "container_name": container_name,
            "is_ml_workspace_storage": False
        }
    
    def get_service_endpoints(self) -> Dict[str, str]:
        """
        Get all service endpoints and connection strings.
        Dynamically builds endpoints based on workspace name.
        
        Returns:
            Dictionary with all service endpoints and connection strings
        """
        self.refresh_config()
        
        # Get ML workspace details
        ml_workspace_name = self.settings.get("AZURE_ML_WORKSPACE_NAME", "")
        ml_resource_group = self.settings.get("AZURE_ML_RESOURCE_GROUP", "")
        ml_subscription_id = self.settings.get("AZURE_ML_SUBSCRIPTION_ID", "")
        
        # Get ML endpoint regions from config
        prediction_region = self.get_config("azure", "resources", "ml_workspace", "endpoints", "prediction", "region", default="eastus")
        prediction_path = self.get_config("azure", "resources", "ml_workspace", "endpoints", "prediction", "path", default="score")
        training_region = self.get_config("azure", "resources", "ml_workspace", "endpoints", "training", "region", default="eastus")
        training_path = self.get_config("azure", "resources", "ml_workspace", "endpoints", "training", "path", default="train")
        
        # Build endpoints
        endpoints = {}
        
        if ml_workspace_name:
            # ML endpoints
            endpoints["AZURE_ML_PREDICTION_ENDPOINT"] = f"https://{ml_workspace_name}.{prediction_region}.inference.azureml.net/{prediction_path}"
            endpoints["AZURE_ML_TRAINING_ENDPOINT"] = f"https://{ml_workspace_name}.{training_region}.training.azureml.net/{training_path}"
            
            # Add other endpoints that depend on ML workspace name
            # ...
        
        # Add other service endpoints
        endpoints["EventHubConnectionString"] = self.settings.get("EventHubConnectionString", "")
        endpoints["ALPHABET_EVENT_HUB"] = self.settings.get("ALPHABET_EVENT_HUB", "")
        endpoints["PREDICTIONS_EVENT_HUB"] = self.settings.get("PREDICTIONS_EVENT_HUB", "")
        
        return endpoints
    
    def update_service_settings(self, ml_workspace_name: str, storage_account: Dict[str, str], endpoints: Dict[str, str]) -> None:
        """
        Update local.settings.json with current service details.
        
        Args:
            ml_workspace_name: The ML workspace name
            storage_account: Dictionary with storage account details
            endpoints: Dictionary with service endpoints
        """
        try:
            # Load current settings
            if os.path.exists(self.settings_path):
                with open(self.settings_path, "r") as settings_file:
                    settings_data = json.load(settings_file)
            else:
                settings_data = {"IsEncrypted": False, "Values": {}}
            
            # Update settings
            values = settings_data.get("Values", {})
            
            # Update ML workspace settings
            values["AZURE_ML_WORKSPACE_NAME"] = ml_workspace_name
            
            # Update storage account settings
            values["AZURE_STORAGE_ACCOUNT"] = storage_account.get("name", "")
            values["AZURE_BLOB_STORAGE_CONNECTION_STRING"] = storage_account.get("connection_string", "")
            values["AZURE_BLOB_CONTAINER_NAME"] = storage_account.get("container_name", "")
            values["AzureWebJobsStorage"] = storage_account.get("connection_string", "")
            
            # Update endpoints
            for key, value in endpoints.items():
                if value:  # Only update if value is not empty
                    values[key] = value
            
            # Save updated settings
            settings_data["Values"] = values
            with open(self.settings_path, "w") as settings_file:
                json.dump(settings_data, settings_file, indent=4)
            
            # Reload settings
            self._load_settings()
            
            logging.info(f"Updated service settings in {self.settings_path}")
        except Exception as e:
            logging.error(f"Error updating service settings: {str(e)}")
    
    def get_retry_policy(self) -> Dict[str, Any]:
        """
        Get the retry policy configuration.
        
        Returns:
            Dictionary with retry policy settings
        """
        return self.get_config("azure", "retry_policy", default={
            "max_attempts": 3,
            "initial_delay": 1,
            "max_delay": 30,
            "exponential_base": 2
        })
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific service.
        
        Args:
            service_name: Name of the service (e.g., "producer", "consumer")
            
        Returns:
            Dictionary with service configuration
        """
        return self.get_config("services", service_name, default={})

# Create a singleton instance for global use
config_manager = ConfigurationManager()

def get_config_manager() -> ConfigurationManager:
    """
    Get the singleton ConfigurationManager instance.
    
    Returns:
        The ConfigurationManager instance
    """
    return config_manager

def with_retry(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Execute a function with retry logic based on the configured retry policy.
    
    Args:
        func: The function to execute
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The result of the function
        
    Raises:
        Exception: The last exception raised by the function after all retries
    """
    retry_policy = config_manager.get_retry_policy()
    max_attempts = retry_policy.get("max_attempts", 3)
    initial_delay = retry_policy.get("initial_delay", 1)
    max_delay = retry_policy.get("max_delay", 30)
    exponential_base = retry_policy.get("exponential_base", 2)
    
    attempt = 0
    last_exception = None
    
    while attempt < max_attempts:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            attempt += 1
            last_exception = e
            
            if attempt >= max_attempts:
                logging.error(f"Failed after {attempt} attempts: {str(e)}")
                raise
            
            # Calculate delay with exponential backoff and jitter
            delay = min(initial_delay * (exponential_base ** (attempt - 1)), max_delay)
            jitter = random.uniform(0, 0.1 * delay)
            delay += jitter
            
            logging.warning(f"Attempt {attempt} failed: {str(e)}. Retrying in {delay:.2f} seconds...")
            time.sleep(delay)
    
    # This should never be reached due to the raise in the loop
    raise last_exception if last_exception else RuntimeError("Unexpected error in retry logic")

def azure_operation(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to apply retry logic to Azure operations.
    
    Args:
        func: The function to decorate
        
    Returns:
        Decorated function with retry logic
    """
    def wrapper(*args, **kwargs):
        return with_retry(func, *args, **kwargs)
    return wrapper

def generate_unique_name(base_name: str, max_length: int = 24) -> str:
    """
    Generate a unique name for Azure resources that meets naming requirements.
    
    Args:
        base_name: Base name to use
        max_length: Maximum length for the name (default 24 for ML workspace)
        
    Returns:
        A unique name that meets Azure naming requirements
    """
    # Get configuration manager
    config_manager = get_config_manager()
    
    # Get naming configuration from config.json
    naming_config = config_manager.get_config("azure", "resources", "ml_workspace", "naming", default={})
    
    # Get pattern, max length, and allowed characters from config
    pattern = naming_config.get("pattern", "ml-{base}-{timestamp}-{random}")
    max_length = naming_config.get("max_length", max_length)
    allowed_chars_pattern = naming_config.get("allowed_chars", "a-zA-Z0-9-")
    
    # Azure ML workspace naming requirements:
    # - 2-32 characters
    # - Alphanumeric characters only
    # - Must start with a letter
    # - Must end with a letter or number
    
    # Clean the base name to meet requirements
    allowed_chars_regex = f"[^{allowed_chars_pattern}]"
    clean_name = re.sub(allowed_chars_regex, '', base_name)
    if not clean_name or not clean_name[0].isalpha():
        clean_name = 'ml' + clean_name
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%m%d%H%M")
    
    # Generate random suffix (3 characters)
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
    
    # Calculate available space for base name
    # Pattern placeholders: {base}, {timestamp}, {random}
    pattern_without_placeholders = re.sub(r'\{base\}|\{timestamp\}|\{random\}', '', pattern)
    available_space = max_length - len(pattern_without_placeholders) - len(timestamp) - len(suffix)
    
    # Truncate base name if necessary
    truncated_name = clean_name[:available_space]
    
    # Replace placeholders in pattern
    unique_name = pattern.replace("{base}", truncated_name)
    unique_name = unique_name.replace("{timestamp}", timestamp)
    unique_name = unique_name.replace("{random}", suffix)
    
    # Ensure the name is within the max length
    if len(unique_name) > max_length:
        unique_name = unique_name[:max_length]
    
    # Ensure the name ends with a letter or number
    if not unique_name[-1].isalnum():
        unique_name = unique_name[:-1] + random.choice(string.ascii_lowercase + string.digits)
    
    return unique_name

def update_blob_container_name(container_name: str) -> None:
    """
    Update blob container name in both config.json and local.settings.json.
    
    Args:
        container_name: The new blob container name
    """
    try:
        # Update config.json
        with open("config.json", "r") as f:
            config = json.load(f)
        config["azure"]["resources"]["blob_container"] = container_name
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)
        
        logging.info(f"Updated blob container name in config.json to: {container_name}")
        
        # Update local.settings.json through existing method
        config_manager.update_service_settings(
            config_manager.get_setting("AZURE_ML_WORKSPACE_NAME"),
            {
                "name": config_manager.get_setting("AZURE_STORAGE_ACCOUNT"),
                "connection_string": config_manager.get_setting("AZURE_BLOB_STORAGE_CONNECTION_STRING"),
                "container_name": container_name
            },
            config_manager.get_service_endpoints()
        )
        
        logging.info(f"Updated blob container name in local.settings.json to: {container_name}")
    except Exception as e:
        logging.error(f"Failed to update blob container name: {str(e)}")
        raise

def update_ml_workspace_name() -> str:
    """
    Generate a new unique ML workspace name and update config.json.
    
    Returns:
        The new workspace name
    """
    config_manager = get_config_manager()
    base_name = config_manager.get_config("azure", "resources", "ml_workspace", "name", default="mlworkspace")
    
    # Generate new unique name
    new_name = generate_unique_name(base_name)
    
    # Update config.json
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        
        config["azure"]["resources"]["ml_workspace"]["name"] = new_name
        
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)
        
        logging.info(f"Updated ML workspace name to: {new_name}")
    except Exception as e:
        logging.error(f"Failed to update ML workspace name in config.json: {str(e)}")
        raise
    
    return new_name
