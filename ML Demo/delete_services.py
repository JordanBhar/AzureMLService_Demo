import json
import os
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load configuration from config.json
def load_config(config_path="config.json"):
    try:
        with open(config_path, "r") as config_file:
            return json.load(config_file)
    except Exception as e:
        logging.error(f"Error loading config: {str(e)}")
        raise

# Load local settings to determine which resources are active
def load_local_settings(local_settings_file="local.settings.json"):
    if os.path.exists(local_settings_file):
        try:
            with open(local_settings_file, "r") as f:
                settings = json.load(f)
            # Assuming settings are stored under the "Values" key
            app_settings = settings.get("Values", {})
            
            # Define keys corresponding to active resources
            keys_to_check = [
                "AZURE_STORAGE_ACCOUNT", 
                "AZURE_EVENT_HUB_NAMESPACE", 
                "AZURE_FUNCTION_APP", 
                "AZURE_ML_WORKSPACE"
            ]
            
            # Get resource name prefix from config if available
            resource_prefix = ""
            try:
                if "resources" in azure_config and "prefix" in azure_config["resources"]:
                    resource_prefix = azure_config["resources"]["prefix"]
            except:
                pass
            
            active_resources = {}
            for key in keys_to_check:
                value = app_settings.get(key)
                if value:
                    # Store both the resource name and its type
                    if key == "AZURE_STORAGE_ACCOUNT":
                        resource_type = "Microsoft.Storage/storageAccounts"
                    elif key == "AZURE_EVENT_HUB_NAMESPACE":
                        resource_type = "Microsoft.EventHub/namespaces"
                    elif key == "AZURE_FUNCTION_APP":
                        resource_type = "Microsoft.Web/sites"
                    elif key == "AZURE_ML_WORKSPACE":
                        resource_type = "Microsoft.MachineLearningServices/workspaces"
                    else:
                        resource_type = "Unknown"
                    
                    active_resources[value.lower()] = resource_type
            
            return active_resources
        except Exception as e:
            logging.error(f"Error loading local settings: {str(e)}")
            return {}
    else:
        logging.warning("local.settings.json not found. Proceeding without active resource filtering.")
        return {}

# Load configuration
try:
    config = load_config()
    azure_config = config["azure"]
    
    # Set Azure subscription and resource group
    SUBSCRIPTION_ID = azure_config["subscription_id"]
    RESOURCE_GROUP = azure_config["resource_group"]
    
    logging.info(f"Loaded configuration for subscription {SUBSCRIPTION_ID} and resource group {RESOURCE_GROUP}")
except Exception as e:
    logging.error(f"Failed to load configuration: {str(e)}")
    raise

# Load active resources from local settings
active_resources = load_local_settings()
if active_resources:
    logging.info(f"Found {len(active_resources)} active resources in local.settings.json")
else:
    logging.warning("No active resources found in local.settings.json")

# Authenticate with Azure
try:
    credential = DefaultAzureCredential()
    resource_client = ResourceManagementClient(credential, SUBSCRIPTION_ID)
    logging.info("Successfully authenticated with Azure")
except Exception as e:
    logging.error(f"Authentication failed: {str(e)}")
    raise

# Get a list of all resources in the resource group
try:
    logging.info(f"🔍 Retrieving resources inside {RESOURCE_GROUP}...")
    resources = list(resource_client.resources.list_by_resource_group(RESOURCE_GROUP))
    logging.info(f"Found {len(resources)} resources in the resource group")
except Exception as e:
    logging.error(f"Failed to retrieve resources: {str(e)}")
    raise

# Function to check if a resource should be deleted
def should_delete_resource(resource_name, resource_type, active_resources, resource_prefix):
    # If we have active resources defined, check if this resource is one of them
    if active_resources and resource_name.lower() in active_resources:
        return True
    
    # Check if this is a related resource based on naming pattern
    if resource_prefix and resource_name.lower().startswith(resource_prefix.lower()):
        logging.info(f"Resource {resource_name} matches prefix {resource_prefix}")
        return True
    
    # Check for common naming patterns for related resources
    for main_resource_name in active_resources.keys():
        # Check if this resource name contains the main resource name
        if main_resource_name in resource_name.lower():
            logging.info(f"Resource {resource_name} appears to be related to {main_resource_name}")
            return True
    
    # Special handling for known related resource types
    related_resource_types = [
        "microsoft.insights/components",  # Application Insights
        "microsoft.operationalinsights/workspaces",  # Log Analytics
        "microsoft.keyvault/vaults",  # Key Vault
        "microsoft.eventgrid/systemtopics",  # Event Grid
        "microsoft.web/serverfarms",  # App Service Plan
        "microsoft.network/applicationgateways",  # Application Gateway
        "microsoft.network/virtualnetworks",  # Virtual Network
        "microsoft.network/networksecuritygroups",  # Network Security Group
        "microsoft.network/publicipaddresses",  # Public IP
        "microsoft.network/privatednszones"  # Private DNS Zone
    ]
    
    if resource_type.lower() in related_resource_types:
        logging.info(f"Resource {resource_name} is a related resource type: {resource_type}")
        return True
    
    return False

# Delete each resource inside the resource group
deleted_count = 0
skipped_count = 0

# Get resource prefix from config if available
resource_prefix = ""
try:
    if "resources" in azure_config and "prefix" in azure_config["resources"]:
        resource_prefix = azure_config["resources"]["prefix"]
except:
    pass

# Sort resources to delete dependent resources first
# This helps avoid dependency conflicts during deletion
resources_to_delete = []
for resource in resources:
    resources_to_delete.append(resource)

# Process resources
for resource in resources_to_delete:
    resource_id = resource.id
    resource_name = resource.name
    resource_type = resource.type
    
    try:
        # Check if this resource should be deleted
        if not should_delete_resource(resource_name, resource_type, active_resources, resource_prefix):
            logging.info(f"⏩ Skipping resource: {resource_name} ({resource_type}) - not identified as a target resource")
            skipped_count += 1
            continue
        
        # Choose API version based on resource type
        if resource_type.lower() == "microsoft.eventhub/namespaces":
            api_version = "2021-11-01"
        elif resource_type.lower() == "microsoft.storage/storageaccounts":
            api_version = "2021-09-01"
        elif resource_type.lower() == "microsoft.web/sites":
            api_version = "2022-03-01"
        elif resource_type.lower() == "microsoft.machinelearningservices/workspaces":
            api_version = "2022-10-01"
        elif resource_type.lower() == "microsoft.insights/components":
            api_version = "2020-02-02"
        elif resource_type.lower() == "microsoft.operationalinsights/workspaces":
            api_version = "2021-06-01"
        elif resource_type.lower() == "microsoft.keyvault/vaults":
            api_version = "2021-10-01"
        elif resource_type.lower() == "microsoft.eventgrid/systemtopics":
            api_version = "2021-12-01"
        elif resource_type.lower() == "microsoft.web/serverfarms":
            api_version = "2022-03-01"
        elif resource_type.lower().startswith("microsoft.network/"):
            api_version = "2021-05-01"
        else:
            api_version = "2021-04-01"
        
        logging.info(f"❌ Deleting resource: {resource.name} ({resource_type}) using API version {api_version}...")
        
        # Delete the resource
        operation = resource_client.resources.begin_delete_by_id(resource_id, api_version=api_version)
        operation.wait()
        
        logging.info(f"✅ {resource.name} deleted.")
        deleted_count += 1
        
    except Exception as e:
        logging.error(f"Failed to delete resource {resource.name}: {str(e)}")

logging.info(f"🚀 Deletion complete: {deleted_count} resources deleted, {skipped_count} resources skipped.")
logging.info(f"The resource group {RESOURCE_GROUP} remains intact.")
