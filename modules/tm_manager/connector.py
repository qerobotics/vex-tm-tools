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
        """
        self.api_client.get_auth_token()
        if not self.api_client.token:
            logger.error("Cannot connect to websocket without an auth token.")
            return

        ws_url_parts = urlparse(self.base_url)
        ws_scheme = "wss" if ws_url_parts.scheme == "https" else "ws"
        host = ws_url_parts.netloc
        uri_path = f"/api/fieldsets/{self.field_set_id}"
        ws_url = f"{ws_scheme}://{host}{uri_path}"
        
        while True:
            try:
                date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                signature = self.api_client.create_signature("GET", uri_path, host, date)

                headers = {
                    "Host": host,
                    "Authorization": f"Bearer {self.api_client.token}",
                    "x-tm-date": date,
                    "x-tm-signature": signature
                }

                logger.info(f"Connecting to websocket at {ws_url}")

                connect_args = {"extra_headers": headers}
                if hasattr(websockets.connect, "additional_headers"):
                    connect_args = {"additional_headers": headers}

                async with websockets.connect(ws_url, **connect_args) as websocket:
                    logger.info("Websocket connection established.")
                    while True:
                        message = await websocket.recv()
                        logger.info(f"Received message: {message}")
                        try:
                            data = json.loads(message)
                            event = Event(
                                type=data.get("type"),
                                field=data.get("fieldID"),
                                payload=data
                            )
                            await self.event_queue.put(event)
                            logger.info(f"Enqueued event: {event.to_json()}")
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode JSON from message: {message}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Websocket connection closed: {e}. Reconnecting in 5 seconds...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}. Retrying in 15 seconds...")
                await asyncio.sleep(15)

            # The API client will handle token refreshing automatically on the next iteration
            self.api_client.get_auth_token()
            if not self.api_client.token:
                logger.error("Failed to refresh token. Waiting 60 seconds before retrying.")
                await asyncio.sleep(60)

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
