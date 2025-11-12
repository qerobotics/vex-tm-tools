import asyncio
import websockets
import json
import os
import logging
from urllib.parse import urlparse
from datetime import datetime, timezone

from models.events import Event
from .api_client import VexTmApiClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VexTmConnector:
    def __init__(self, event_queue, api_client, base_url, field_set_id):
        self.event_queue = event_queue
        self.api_client = api_client
        self.base_url = base_url
        self.field_set_id = field_set_id

    async def connect(self):
        """
        Connects to the VEX TM Field Set Websocket and listens for events.
        Rebuilt from scratch following VEX API documentation precisely.
        """
        # Ensure we have a valid auth token
        self.api_client.get_auth_token()
        if not self.api_client.token:
            logger.error("Cannot connect to websocket without an auth token.")
            return

        # Parse the base URL to construct the websocket URL
        parsed_base = urlparse(self.base_url)
        
        # Determine websocket scheme based on HTTP/HTTPS
        ws_scheme = "wss" if parsed_base.scheme == "https" else "ws"
        
        # Construct the URI path for the field set websocket
        uri_path = f"/api/fieldsets/{self.field_set_id}"
        
        # Build the complete websocket URL
        # Use hostname without port for standard ports (80/443), otherwise include port
        if parsed_base.port:
            ws_host = f"{parsed_base.hostname}:{parsed_base.port}"
        else:
            ws_host = parsed_base.hostname
        
        ws_url = f"{ws_scheme}://{ws_host}{uri_path}"
        
        logger.debug(f"Websocket URL constructed: {ws_url}")
        logger.debug(f"Base URL parsed - scheme: {parsed_base.scheme}, hostname: {parsed_base.hostname}, port: {parsed_base.port}")
        
        while True:
            try:
                # Refresh token if needed before each connection attempt
                self.api_client.get_auth_token()
                if not self.api_client.token:
                    logger.error("Failed to obtain auth token. Waiting 60 seconds before retrying.")
                    await asyncio.sleep(60)
                    continue
                
                # Generate timestamp in RFC1123 format as required by VEX TM API
                date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                
                # The host value for signature MUST match what will be in the Host header
                # For websockets, if port is specified in URL, it will be in the Host header
                if parsed_base.port:
                    host_for_signature = f"{parsed_base.hostname}:{parsed_base.port}"
                else:
                    host_for_signature = parsed_base.hostname
                
                logger.debug(f"Creating signature with host: {host_for_signature}")
                logger.debug(f"URI path: {uri_path}")
                logger.debug(f"Date: {date}")
                logger.debug(f"Token (first 20 chars): {self.api_client.token[:20]}...")
                
                # Create the HMAC signature according to VEX TM API spec
                signature = self.api_client.create_signature("GET", uri_path, host_for_signature, date)
                
                logger.debug(f"Generated signature: {signature}")

                # Build headers for websocket connection
                # Note: websockets library automatically adds Host header, so we don't include it
                headers = {
                    "Authorization": f"Bearer {self.api_client.token}",
                    "x-tm-date": date,
                    "x-tm-signature": signature
                }

                logger.info(f"Connecting to websocket at {ws_url}")
                logger.debug(f"Headers being sent: {headers}")

                # Connect to websocket with authentication headers
                async with websockets.connect(ws_url, extra_headers=headers) as websocket:
                    logger.info("Websocket connection established successfully!")
                    
                    # Listen for messages from the websocket
                    while True:
                        message = await websocket.recv()
                        logger.debug(f"Raw message received: {message}")
                        
                        try:
                            data = json.loads(message)
                            logger.info(f"Parsed message type: {data.get('type')}, field: {data.get('fieldID')}")
                            
                            # Create event object and add to queue
                            event = Event(
                                type=data.get("type"),
                                field=data.get("fieldID"),
                                payload=data
                            )
                            await self.event_queue.put(event)
                            logger.info(f"Enqueued event: {event.to_json()}")
                            
                        except json.JSONDecodeError as e:
                            logger.warning(f"Could not decode JSON from message: {message}. Error: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)

            except websockets.exceptions.InvalidStatusCode as e:
                logger.error(f"Websocket connection rejected with status {e.status_code}: {e}. Retrying in 15 seconds...")
                await asyncio.sleep(15)
                
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Websocket connection closed (code: {e.code}, reason: {e.reason}). Reconnecting in 5 seconds...")
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Unexpected error during websocket connection: {e}. Retrying in 15 seconds...", exc_info=True)
                await asyncio.sleep(15)

if __name__ == '__main__':
    # Example usage for testing
    async def main():
        event_queue = asyncio.Queue()
        
        # These should be loaded from a secure config, not hardcoded
        client_id = os.environ.get("VEX_TM_CLIENT_ID")
        client_secret = os.environ.get("VEX_TM_CLIENT_SECRET")
        api_key = os.environ.get("VEX_TM_API_KEY")
        base_url = os.environ.get("VEX_TM_BASE_URL", "http://localhost:8080")
        field_set_id = int(os.environ.get("VEX_TM_FIELD_SET_ID", 1))

        if not all([client_id, client_secret, api_key]):
            logger.error("Missing required environment variables for VEX TM connection.")
            return

        api_client = VexTmApiClient(
            client_id=client_id,
            client_secret=client_secret,
            api_key=api_key,
            base_url=base_url
        )

        connector = VexTmConnector(
            event_queue=event_queue,
            api_client=api_client,
            base_url=base_url,
            field_set_id=field_set_id
        )
        
        # Start the connector
        asyncio.create_task(connector.connect())

        # Example of consuming events from the queue
        while True:
            event = await event_queue.get()
            print(f"Dequeued event: {event.to_json()}")
            event_queue.task_done()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
