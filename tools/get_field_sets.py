import sys
import os
import json
import logging

# Add the parent directory to sys.path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.tm_manager.api_client import VexTmApiClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config(config_path='storage/config.json'):
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found at {config_path}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in config file at {config_path}")
        return None

def main():
    config = load_config()
    if not config:
        return

    vex_tm_api = config.get('vex_tm_api', {})
    client_id = vex_tm_api.get('client_id')
    client_secret = vex_tm_api.get('client_secret')
    api_key = vex_tm_api.get('api_key')
    base_url = vex_tm_api.get('base_url')

    if not all([client_id, client_secret, api_key, base_url]):
        logger.error("Missing VEX TM API configuration. Please check storage/config.json")
        return

    logger.info(f"Connecting to VEX TM at {base_url}...")
    
    client = VexTmApiClient(client_id, client_secret, api_key, base_url)
    
    # Force token fetch to verify credentials
    token = client.get_auth_token()
    if not token:
        logger.error("Failed to authenticate with VEX TM.")
        return

    logger.info("Authentication successful.")
    
    logger.info("Fetching field sets...")
    response = client.get("/api/fieldsets")
    
    if response and "fieldsets" in response:
        fieldsets = response["fieldsets"]
        print("\nAvailable Field Sets:")
        print("-" * 40)
        print(f"{'ID':<5} | {'Name'}")
        print("-" * 40)
        for fs in fieldsets:
            print(f"{fs['id']:<5} | {fs['name']}")
        print("-" * 40)
    else:
        logger.error("Failed to fetch field sets or no field sets found.")

if __name__ == "__main__":
    main()
