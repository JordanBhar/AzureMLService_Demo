import json
import os
import time
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import StorageAccountCreateParameters, Sku
from azure.mgmt.eventhub import EventHubManagementClient
from azure.mgmt.eventhub.models import Eventhub, AccessRights
from azure.mgmt.web import WebSiteManagementClient
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Workspace
from azure.mgmt.web.models import Site, SiteConfig, NameValuePair

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

# Load configuration
config = load_config()
azure_config = config["azure"]
resource_config = azure_config["resources"]

# Set Azure configuration from config file
SUBSCRIPTION_ID = azure_config["subscription_id"]
RESOURCE_GROUP = azure_config["resource_group"]
LOCATION = azure_config["location"]
STORAGE_ACCOUNT_NAME = resource_config["storage_account"]["name"]
EVENT_HUB_NAMESPACE = resource_config["event_hub"]["namespace"]
ALPHABET_EVENT_HUB = resource_config["event_hub"]["topics"]["alphabet"]
PREDICTIONS_EVENT_HUB = resource_config["event_hub"]["topics"]["predictions"]
FUNCTION_APP_NAME = resource_config["function_app"]["name"]
ML_WORKSPACE_NAME = resource_config["ml_workspace"]["name"]
BLOB_CONTAINER_NAME = resource_config["storage_account"]["blob_container"]

# Authenticate with Azure
try:
    credential = DefaultAzureCredential()
    resource_client = ResourceManagementClient(credential, SUBSCRIPTION_ID)
    logging.info("Successfully authenticated with Azure")
except Exception as e:
    logging.error(f"Authentication failed: {str(e)}")
    raise

# Check if Resource Group Exists
logging.info("🔹 Checking if Resource Group exists...")
try:
    rg_exists = False
    for rg in resource_client.resource_groups.list():
        if rg.name == RESOURCE_GROUP:
            rg_exists = True
            logging.info(f"✅ Resource Group '{RESOURCE_GROUP}' already exists.")
            break

    if not rg_exists:
        logging.info("🔹 Creating Resource Group...")
        resource_client.resource_groups.create_or_update(RESOURCE_GROUP, {"location": LOCATION})
        logging.info(f"✅ Resource Group '{RESOURCE_GROUP}' created.")
except Exception as e:
    logging.error(f"Error managing Resource Group: {str(e)}")
    raise

# Check if Storage Account exists
try:
    storage_client = StorageManagementClient(credential, SUBSCRIPTION_ID)
    logging.info("🔹 Checking if Storage Account exists...")
    storage_account_exists = any(sa.name == STORAGE_ACCOUNT_NAME for sa in storage_client.storage_accounts.list_by_resource_group(RESOURCE_GROUP))

    if storage_account_exists:
        logging.info(f"✅ Storage Account '{STORAGE_ACCOUNT_NAME}' already exists.")
    else:
        logging.info("🔹 Creating Storage Account...")
        storage_params = StorageAccountCreateParameters(
            sku=Sku(name=resource_config["storage_account"]["sku"]),
            kind=resource_config["storage_account"]["kind"],
            location=LOCATION
        )
        storage_client.storage_accounts.begin_create(RESOURCE_GROUP, STORAGE_ACCOUNT_NAME, storage_params).result()
        logging.info(f"✅ Storage Account '{STORAGE_ACCOUNT_NAME}' created.")
except Exception as e:
    logging.error(f"Error managing Storage Account: {str(e)}")
    raise

# Get Storage Account Keys
try:
    storage_keys = storage_client.storage_accounts.list_keys(RESOURCE_GROUP, STORAGE_ACCOUNT_NAME)
    STORAGE_KEY = storage_keys.keys[0].value
    STORAGE_CONNECTION_STRING = f"DefaultEndpointsProtocol=https;AccountName={STORAGE_ACCOUNT_NAME};AccountKey={STORAGE_KEY};EndpointSuffix=core.windows.net"
    logging.info("✅ Retrieved Storage Account keys.")
except Exception as e:
    logging.error(f"Error retrieving Storage Account keys: {str(e)}")
    raise

# Check if Event Hub Namespace exists
# I NEED TO FIX THIS FUNCTION TO SET UP EVENT HUBS WITH BLOB STORAGE CAPTURE instead of the current blob storage provisioned
try:
    eventhub_client = EventHubManagementClient(credential, SUBSCRIPTION_ID)
    logging.info("🔹 Checking if Event Hub Namespace exists...")
    eventhub_namespace_exists = any(ns.name == EVENT_HUB_NAMESPACE for ns in eventhub_client.namespaces.list_by_resource_group(RESOURCE_GROUP))

    if eventhub_namespace_exists:
        logging.info(f"✅ Event Hub Namespace '{EVENT_HUB_NAMESPACE}' already exists.")
    else:
        logging.info("🔹 Creating Event Hub Namespace...")
        eventhub_client.namespaces.begin_create_or_update(RESOURCE_GROUP, EVENT_HUB_NAMESPACE, {"location": LOCATION}).result()
        logging.info(f"✅ Event Hub Namespace '{EVENT_HUB_NAMESPACE}' created.")
except Exception as e:
    logging.error(f"Error managing Event Hub Namespace: {str(e)}")
    raise

# Check if Event Hubs exist
try:
    logging.info("🔹 Checking if Event Hubs exist...")
    existing_event_hubs = {eh.name for eh in eventhub_client.event_hubs.list_by_namespace(RESOURCE_GROUP, EVENT_HUB_NAMESPACE)}

    if ALPHABET_EVENT_HUB in existing_event_hubs:
        logging.info(f"✅ Event Hub '{ALPHABET_EVENT_HUB}' already exists.")
    else:
        logging.info(f"🔹 Creating Event Hub '{ALPHABET_EVENT_HUB}'...")
        eventhub_client.event_hubs.create_or_update(RESOURCE_GROUP, EVENT_HUB_NAMESPACE, ALPHABET_EVENT_HUB, Eventhub())
        logging.info(f"✅ Event Hub '{ALPHABET_EVENT_HUB}' created.")

    if PREDICTIONS_EVENT_HUB in existing_event_hubs:
        logging.info(f"✅ Event Hub '{PREDICTIONS_EVENT_HUB}' already exists.")
    else:
        logging.info(f"🔹 Creating Event Hub '{PREDICTIONS_EVENT_HUB}'...")
        eventhub_client.event_hubs.create_or_update(RESOURCE_GROUP, EVENT_HUB_NAMESPACE, PREDICTIONS_EVENT_HUB, Eventhub())
        logging.info(f"✅ Event Hub '{PREDICTIONS_EVENT_HUB}' created.")
except Exception as e:
    logging.error(f"Error managing Event Hubs: {str(e)}")
    raise

# Get Event Hub Connection String
try:
    eventhub_keys = eventhub_client.namespaces.list_keys(RESOURCE_GROUP, EVENT_HUB_NAMESPACE, "RootManageSharedAccessKey")
    EVENT_HUB_CONNECTION_STRING = eventhub_keys.primary_connection_string
    logging.info("✅ Retrieved Event Hub connection string.")
except Exception as e:
    logging.error(f"Error retrieving Event Hub connection string: {str(e)}")
    raise

# Check if Azure ML Workspace exists
try:
    logging.info("🔹 Checking if Azure ML Workspace exists...")
    ml_client = MLClient(credential, SUBSCRIPTION_ID, RESOURCE_GROUP)
    ml_workspaces = {ws.name for ws in ml_client.workspaces.list()}

    # Original workspace name from config
    original_ml_workspace_name = ML_WORKSPACE_NAME
    
    # Check if workspace exists
    if ML_WORKSPACE_NAME in ml_workspaces:
        logging.info(f"✅ Azure ML Workspace '{ML_WORKSPACE_NAME}' already exists.")
    else:
        # Try to create the workspace
        try:
            logging.info(f"🔹 Creating Azure ML Workspace '{ML_WORKSPACE_NAME}'...")
            workspace = Workspace(location=LOCATION, name=ML_WORKSPACE_NAME, resource_group=RESOURCE_GROUP)
            ml_client.workspaces.begin_create(workspace).result()
            logging.info(f"✅ Azure ML Workspace '{ML_WORKSPACE_NAME}' created.")
        except Exception as creation_error:
            # Check if the error is due to a soft-deleted workspace
            error_message = str(creation_error)
            if "Soft-deleted workspace exists" in error_message:
                # Generate a new unique name with timestamp
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                ML_WORKSPACE_NAME = f"{original_ml_workspace_name}-{timestamp}"
                
                logging.warning(f"⚠️ Soft-deleted workspace detected. Using alternative name: {ML_WORKSPACE_NAME}")
                
                # Try again with the new name
                workspace = Workspace(location=LOCATION, name=ML_WORKSPACE_NAME, resource_group=RESOURCE_GROUP)
                ml_client.workspaces.begin_create(workspace).result()
                logging.info(f"✅ Azure ML Workspace '{ML_WORKSPACE_NAME}' created with alternative name.")
                
                # Update the config.json file with the new name
                try:
                    config["azure"]["resources"]["ml_workspace"]["name"] = ML_WORKSPACE_NAME
                    with open("config.json", "w") as config_file:
                        json.dump(config, config_file, indent=4)
                    logging.info("✅ Updated config.json with new ML workspace name.")
                except Exception as config_error:
                    logging.warning(f"⚠️ Could not update config.json: {str(config_error)}")
            else:
                # If it's a different error, re-raise it
                raise creation_error
except Exception as e:
    logging.error(f"Error managing Azure ML Workspace: {str(e)}")
    raise

# Check if Azure Function App exists
try:
    function_client = WebSiteManagementClient(credential, SUBSCRIPTION_ID)
    logging.info("🔹 Checking if Azure Function App exists...")
    function_apps = {fa.name for fa in function_client.web_apps.list_by_resource_group(RESOURCE_GROUP)}

    if FUNCTION_APP_NAME in function_apps:
        logging.info(f"✅ Azure Function App '{FUNCTION_APP_NAME}' already exists.")
    else:
        logging.info("🔹 Creating Azure Function App...")
        # Configure app settings to use the existing storage account
        site_config = SiteConfig(
            app_settings=[
                NameValuePair(
                    name="AzureWebJobsStorage",
                    value=STORAGE_CONNECTION_STRING
                ),
                NameValuePair(
                    name="FUNCTIONS_WORKER_RUNTIME",
                    value="python"
                ),
                # Add any other settings here, e.g.:
                # NameValuePair(name="SETTING_KEY", value="SETTING_VALUE"),
            ]
        )

        # Create the Function App with the custom site configuration
        function_app_site = Site(
            location=LOCATION,
            kind="functionapp",
            site_config=site_config
        )

        function_app = function_client.web_apps.begin_create_or_update(
            RESOURCE_GROUP,
            FUNCTION_APP_NAME,
            function_app_site
        ).result()

        logging.info(f"✅ Azure Function App '{FUNCTION_APP_NAME}' created using the existing storage account!")
except Exception as e:
    logging.error(f"Error managing Azure Function App: {str(e)}")
    raise

# Get Function App Details
FUNCTION_APP_URL = f"https://{FUNCTION_APP_NAME}.azurewebsites.net"

# Track related resources
related_resources = {}

# Check if Application Insights exists (if enabled in config)
try:
    if "related_services" in resource_config and resource_config["related_services"].get("app_insights", False):
        from azure.mgmt.applicationinsights import ApplicationInsightsManagementClient
        
        logging.info("🔹 Checking if Application Insights exists...")
        app_insights_client = ApplicationInsightsManagementClient(credential, SUBSCRIPTION_ID)
        
        # Use resource prefix for consistent naming
        app_insights_name = f"{resource_config.get('prefix', 'handwrit')}insights{FUNCTION_APP_NAME.lower()[:8]}"
        
        # Check if it exists
        app_insights_exists = False
        try:
            app_insights = app_insights_client.components.get(RESOURCE_GROUP, app_insights_name)
            app_insights_exists = True
            logging.info(f"✅ Application Insights '{app_insights_name}' already exists.")
            related_resources["app_insights"] = app_insights_name
        except Exception:
            app_insights_exists = False
        
        if not app_insights_exists:
            logging.info(f"🔹 Creating Application Insights '{app_insights_name}'...")
            # Create Application Insights
            app_insights_params = {
                "location": LOCATION,
                "kind": "web",
                "application_type": "web"
            }
            app_insights = app_insights_client.components.create_or_update(
                RESOURCE_GROUP, 
                app_insights_name, 
                app_insights_params
            )
            logging.info(f"✅ Application Insights '{app_insights_name}' created.")
            related_resources["app_insights"] = app_insights_name
except Exception as e:
    logging.warning(f"Could not check/create Application Insights: {str(e)}")
    logging.warning("This is non-critical and the deployment will continue.")

# Check if Log Analytics exists (if enabled in config)
try:
    if "related_services" in resource_config and resource_config["related_services"].get("log_analytics", False):
        from azure.mgmt.loganalytics import LogAnalyticsManagementClient
        
        logging.info("🔹 Checking if Log Analytics workspace exists...")
        log_analytics_client = LogAnalyticsManagementClient(credential, SUBSCRIPTION_ID)
        
        # Use resource prefix for consistent naming
        log_analytics_name = f"{resource_config.get('prefix', 'handwrit')}logalytic{FUNCTION_APP_NAME.lower()[:8]}"
        
        # Check if it exists
        log_analytics_exists = False
        try:
            log_analytics = log_analytics_client.workspaces.get(RESOURCE_GROUP, log_analytics_name)
            log_analytics_exists = True
            logging.info(f"✅ Log Analytics workspace '{log_analytics_name}' already exists.")
            related_resources["log_analytics"] = log_analytics_name
        except Exception:
            log_analytics_exists = False
        
        if not log_analytics_exists:
            logging.info(f"🔹 Creating Log Analytics workspace '{log_analytics_name}'...")
            # Create Log Analytics workspace
            log_analytics_params = {
                "location": LOCATION,
                "sku": {
                    "name": "PerGB2018"
                },
                "retention_in_days": 30
            }
            log_analytics = log_analytics_client.workspaces.create_or_update(
                RESOURCE_GROUP, 
                log_analytics_name, 
                log_analytics_params
            )
            logging.info(f"✅ Log Analytics workspace '{log_analytics_name}' created.")
            related_resources["log_analytics"] = log_analytics_name
except Exception as e:
    logging.warning(f"Could not check/create Log Analytics workspace: {str(e)}")
    logging.warning("This is non-critical and the deployment will continue.")

# Check if Key Vault exists (if enabled in config)
try:
    if "related_services" in resource_config and resource_config["related_services"].get("key_vault", False):
        from azure.mgmt.keyvault import KeyVaultManagementClient
        from azure.mgmt.keyvault.models import VaultCreateOrUpdateParameters, VaultProperties, Sku, AccessPolicyEntry
        
        logging.info("🔹 Checking if Key Vault exists...")
        key_vault_client = KeyVaultManagementClient(credential, SUBSCRIPTION_ID)
        
        # Use resource prefix for consistent naming
        key_vault_name = f"{resource_config.get('prefix', 'handwrit')}keyvault{FUNCTION_APP_NAME.lower()[:8]}"
        
        # Check if it exists
        key_vault_exists = False
        try:
            key_vault = key_vault_client.vaults.get(RESOURCE_GROUP, key_vault_name)
            key_vault_exists = True
            logging.info(f"✅ Key Vault '{key_vault_name}' already exists.")
            related_resources["key_vault"] = key_vault_name
        except Exception:
            key_vault_exists = False
        
        if not key_vault_exists:
            logging.info(f"🔹 Creating Key Vault '{key_vault_name}'...")
            # Create Key Vault
            key_vault_params = VaultCreateOrUpdateParameters(
                location=LOCATION,
                properties=VaultProperties(
                    tenant_id=os.environ.get("AZURE_TENANT_ID", "your-tenant-id"),
                    sku=Sku(name="standard", family="A"),
                    access_policies=[],
                    enabled_for_deployment=True,
                    enabled_for_disk_encryption=True,
                    enabled_for_template_deployment=True
                )
            )
            key_vault = key_vault_client.vaults.create_or_update(
                RESOURCE_GROUP, 
                key_vault_name, 
                key_vault_params
            )
            logging.info(f"✅ Key Vault '{key_vault_name}' created.")
            related_resources["key_vault"] = key_vault_name
except Exception as e:
    logging.warning(f"Could not check/create Key Vault: {str(e)}")
    logging.warning("This is non-critical and the deployment will continue.")

# Save Credentials to JSON File
try:
    settings = {
        "IsEncrypted": False,
        "Values": {
            "AzureWebJobsStorage": STORAGE_CONNECTION_STRING,
            "FUNCTIONS_WORKER_RUNTIME": "python",
            
            "AZURE_ML_PREDICTION_ENDPOINT": f"https://{ML_WORKSPACE_NAME}.eastus.inference.azureml.net/score",
            "AZURE_ML_KEY": "your-ml-auth-key",  # You'll need to retrieve this manually
            "AZURE_ML_TRAINING_ENDPOINT": f"https://{ML_WORKSPACE_NAME}.eastus.training.azureml.net/train",
            
            "EventHubConnectionString": EVENT_HUB_CONNECTION_STRING,
            "ALPHABET_EVENT_HUB": ALPHABET_EVENT_HUB,
            "PREDICTIONS_EVENT_HUB": PREDICTIONS_EVENT_HUB,
            "CONSUMER_GROUP": resource_config["event_hub"]["consumer_group"],
            
            "AZURE_BLOB_STORAGE_CONNECTION_STRING": STORAGE_CONNECTION_STRING,
            "AZURE_BLOB_CONTAINER_NAME": BLOB_CONTAINER_NAME,
            
            "AZURE_ML_WORKSPACE_NAME": ML_WORKSPACE_NAME,
            "AZURE_ML_RESOURCE_GROUP": RESOURCE_GROUP,
            "AZURE_ML_SUBSCRIPTION_ID": SUBSCRIPTION_ID,
            "AZURE_ML_TENANT_ID": "your-tenant-id",
            "AZURE_ML_MODEL_NAME": resource_config["ml_workspace"]["model_name"],
            "AZURE_ML_EXPERIMENT_NAME": resource_config["ml_workspace"]["experiment_name"],
            
            "AZURE_FORM_RECOGNIZER_ENDPOINT": resource_config["form_recognizer"]["endpoint"],
            "AZURE_FORM_RECOGNIZER_KEY": resource_config["form_recognizer"]["key"],
            
            # Add resource identifiers for delete script
            "AZURE_STORAGE_ACCOUNT": STORAGE_ACCOUNT_NAME,
            "AZURE_EVENT_HUB_NAMESPACE": EVENT_HUB_NAMESPACE,
            "AZURE_FUNCTION_APP": FUNCTION_APP_NAME,
            "AZURE_ML_WORKSPACE": ML_WORKSPACE_NAME,
            
            # Add related resources
            "AZURE_APP_INSIGHTS": related_resources.get("app_insights", ""),
            "AZURE_LOG_ANALYTICS": related_resources.get("log_analytics", ""),
            "AZURE_KEY_VAULT": related_resources.get("key_vault", ""),
            
            # Add resource prefix for deletion script
            "AZURE_RESOURCE_PREFIX": resource_config.get("prefix", "handwrit")
        }
    }

    with open("local.settings.json", "w") as config_file:
        json.dump(settings, config_file, indent=4)
    
    logging.info("✅ Configuration saved to local.settings.json")
except Exception as e:
    logging.error(f"Error saving configuration: {str(e)}")
    raise

logging.info("✅ All services provisioned successfully!")
logging.info("✅ Related services provisioned:")
for service_type, service_name in related_resources.items():
    logging.info(f"  - {service_type}: {service_name}")
