import json
from azure.storage.blob import BlobServiceClient

# Load config from JSON
def load_config(json_path="local.settings.json"):
    try:
        with open(json_path, "r") as config_file:
            config = json.load(config_file)
            return config.get("Values", {})
    except Exception as e:
        print(f"Error loading config: {str(e)}")
        return {}

# Create the container if it doesn't exist
def create_container():
    config = load_config()
    connection_string = config.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
    
    if not connection_string:
        print("❌ Error: AZURE_BLOB_STORAGE_CONNECTION_STRING not found in local.settings.json")
        return False
    
    try:
        # Create the BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Container name
        container_name = "inference-images"
        
        # Check if container exists
        container_exists = False
        containers = blob_service_client.list_containers()
        for container in containers:
            if container.name == container_name:
                container_exists = True
                break
        
        # Create container if it doesn't exist
        if not container_exists:
            print(f"🔹 Creating container '{container_name}'...")
            blob_service_client.create_container(container_name)
            print(f"✅ Container '{container_name}' created successfully!")
        else:
            print(f"✅ Container '{container_name}' already exists!")
        
        return True
    
    except Exception as e:
        print(f"❌ Error creating container: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔹 Checking for 'inference-images' container in Azure Blob Storage...")
    success = create_container()
    
    if success:
        print("✅ Setup complete! You can now run the Azure Functions app.")
    else:
        print("❌ Setup failed. Please check the error messages above.")
