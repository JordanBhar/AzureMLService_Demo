# Azure ML Service Demo

This project demonstrates integration with Azure ML services, Event Hubs, and Blob Storage for image processing and machine learning.

## Environment Setup

This project uses environment variables to manage sensitive configuration. Follow these steps to set up your environment:

### 1. Install Dependencies

```bash
pip install -r requirements.txt
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

## Troubleshooting

If you encounter issues with configuration:

1. Verify that your `.env` or `local.settings.json` file contains all required values
2. Check that the python-dotenv package is installed
3. Ensure your Azure resources are properly configured and accessible
