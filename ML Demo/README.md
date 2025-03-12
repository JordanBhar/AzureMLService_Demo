# Azure ML Service Demo

This project demonstrates integration with Azure services for text extraction from images, using Event Hubs and Blob Storage for image processing and Azure Document Intelligence (Form Recognizer) for OCR.

## Environment Setup

This project uses environment variables to manage sensitive configuration. Follow these steps to set up your environment:

### 1. Set Up Environment and Install Dependencies

#### Using the Setup Scripts (Recommended)

We provide three setup scripts for different platforms. All scripts handle dependency issues automatically, especially for newer Python versions (3.11+).

**For macOS/Linux (Bash):**
```bash
# Make the script executable
chmod +x setup.sh
# Run the setup script
./setup.sh
```

**For Windows (PowerShell):**
```powershell
# You may need to set execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
# Run the setup script
.\setup.ps1
```

**Cross-platform Python script (works on all systems):**
```bash
# Make the script executable (macOS/Linux only)
chmod +x setup.py
# Run the script
python setup.py
```

#### Python Version Compatibility

- **Python 3.8-3.10**: Fully compatible with all dependencies
- **Python 3.11-3.13**: Compatible with special handling (our setup scripts handle this automatically)

If you encounter issues with Python 3.13, consider:
1. Using our setup scripts which handle compatibility issues
2. Downgrading to Python 3.9 or 3.10 for better compatibility
3. Installing problematic packages manually with `--only-binary :all:` flag

#### Manual Setup (Advanced)

If you prefer to set up manually:
```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# Clean existing packages (if upgrading)
pip uninstall -y -r requirements.txt
pip cache purge

# Upgrade pip, setuptools, and wheel
pip install --upgrade pip setuptools wheel

# Install numpy first
pip install numpy

# Install non-problematic packages
grep -v "pillow\|gevent\|azureml-" requirements.txt > temp_requirements.txt
pip install -r temp_requirements.txt

# Install problematic packages with special handling
pip install --only-binary :all: pillow
pip install pillow-heif
pip install gevent
pip install azureml-core==1.48.0 azureml-defaults==1.48.0 azureml-mlflow==1.48.0 azureml-dataset-runtime==1.48.0

# Clean up
rm temp_requirements.txt
```

### 2. Configure Environment Variables

There are two ways to configure the application:

#### Option 1: Using a .env file (Recommended for local development)

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file and replace the placeholder values with your actual Azure credentials and endpoints.

#### Option 2: Using local.settings.json (Azure Functions local development)

1. Copy the example settings file:
   ```bash
   cp local.settings.example.json local.settings.json
   ```

2. Edit the `local.settings.json` file and replace the placeholder values with your actual Azure credentials and endpoints.

### 3. Keeping Secrets Secure

- **IMPORTANT**: Never commit your `.env` or `local.settings.json` files to version control
- Both files are already included in `.gitignore` to prevent accidental commits
- Only commit the example files with placeholder values
- For production deployment, use Azure Functions application settings or other secure methods to manage secrets

## Running the Application

```bash
func start
```

## Development Workflow

1. Make changes to your code
2. Test locally using your `.env` or `local.settings.json` file
3. When committing to GitHub, ensure your secrets are not included
4. For deployment, configure your secrets in the Azure portal or use Azure Key Vault

## Architecture

This application uses the following Azure services:

1. **Azure Event Hubs**: Receives images for processing and sends extracted text results
2. **Azure Blob Storage**: Stores images for training and reference
3. **Azure Document Intelligence** (Form Recognizer): Extracts text from images using OCR
4. **Azure Functions**: Hosts the serverless application that processes images and coordinates the workflow

### Flow

1. Images are sent to the `ALPHABET_EVENT_HUB` Event Hub
2. The `process_single_image` function is triggered by new events
3. The function extracts text from the image using Azure Document Intelligence
4. The extracted text is sent to the `PREDICTIONS_EVENT_HUB` Event Hub
5. The Consumer.py application listens to the predictions Event Hub and makes them available via an API

## Required Azure Resources

To run this application, you need to create the following Azure resources:

1. **Azure Event Hubs Namespace** with two Event Hubs:
   - One for receiving images (`ALPHABET_EVENT_HUB`)
   - One for sending predictions (`PREDICTIONS_EVENT_HUB`)

2. **Azure Storage Account** with a container named `images`

3. **Azure Document Intelligence** (formerly Form Recognizer) resource

4. **Azure Function App** to host the application

## Troubleshooting

If you encounter issues with configuration:

1. Verify that your `.env` or `local.settings.json` file contains all required values
2. Check that the python-dotenv package is installed
3. Ensure your Azure resources are properly configured and accessible

### Common Issues

#### Package Installation Problems

If you encounter issues with package installation:

1. Make sure you're using Python 3.8 or 3.9 (some Azure packages have issues with Python 3.11)
2. Try using the provided setup scripts which handle dependency installation order
3. If specific packages fail, try installing them individually with `pip install [package]`

#### Azure Document Intelligence Connection Issues

If text extraction isn't working:

1. Verify your Form Recognizer endpoint and key in the configuration
2. Check that your Azure Document Intelligence resource is properly provisioned
3. Ensure the images being sent are in a supported format (JPEG, PNG, PDF, TIFF)
