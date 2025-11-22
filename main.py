import asyncio
import threading
import os
import logging
from multiprocessing import Queue

from modules.tm_manager.api_client import VexTmApiClient
from modules.tm_manager.connector import VexTmConnector
from modules.tm_manager.schedule_fetcher import ScheduleFetcher
from modules.event_processor import EventProcessor
from modules.match_scheduler import MatchScheduler
from server import app, set_event_queue

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reduce noisy ntfy and server debug logs: keep only INFO+ from these sources
logging.getLogger("ntfy").setLevel(logging.INFO)
logging.getLogger("server").setLevel(logging.INFO)

# Enable debug logging specifically for the zeros controller
logging.getLogger("modules.vfx.zeros.controller").setLevel(logging.DEBUG)

def run_flask(host, port):
    """Function to run Flask app in a separate thread."""
    logger.info(f"Starting Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=False)

async def main():
    """
    Main function to initialize and run all components of the application.
    """
    logger.info("Initializing application...")

    # A queue that can be shared between processes if we need to scale out.
    # For now, it works fine with threads.
    event_queue = asyncio.Queue()

    # --- Load Configuration ---
    # The EventProcessor loads the full config, we'll use that as the source of truth
    event_processor = EventProcessor(event_queue)
    config = event_processor.config

    # Get VEX TM API credentials from the loaded config
    vex_tm_api_config = config.vex_tm_api
    client_id = vex_tm_api_config.get("client_id")
    client_secret = vex_tm_api_config.get("client_secret")
    api_key = vex_tm_api_config.get("api_key")
    base_url = vex_tm_api_config.get("base_url", "http://localhost:8080")
    field_set_id = int(vex_tm_api_config.get("field_set_id", os.environ.get("VEX_TM_FIELD_SET_ID", 1)))

    if not all([client_id, client_secret, api_key]):
        logger.error("Missing required VEX TM API configuration in config.json. Please set client_id, client_secret, and api_key under the 'vex_tm_api' key.")
        return

    # Share the queue with the Flask app for manual controls
    set_event_queue(event_queue, asyncio.get_running_loop())

    # --- Initialize Components ---
    # API Client
    api_client = VexTmApiClient(
        client_id=client_id,
        client_secret=client_secret,
        api_key=api_key,
        base_url=base_url
    )

    # Thread 5: Websocket Connector
    vex_tm_connector = VexTmConnector(
        event_queue=event_queue,
        api_client=api_client,
        base_url=base_url,
        field_set_id=field_set_id
    )

    # Thread 3: Schedule Fetcher
    schedule_fetcher = ScheduleFetcher(api_client)

    # Thread 4: Match Scheduler
    match_scheduler = MatchScheduler(event_queue)

    # Thread 1: Flask Frontend
    # The Flask app will run in its own thread so it doesn't block asyncio
    flask_thread = threading.Thread(target=run_flask, args=('0.0.0.0', 5000), daemon=True)

    # --- Start Services ---
    try:
        logger.info("Starting services...")
        flask_thread.start()

        # Create asyncio tasks for our async components
        connector_task = asyncio.create_task(vex_tm_connector.connect())
        processor_task = asyncio.create_task(event_processor.process_events())
        fetcher_task = asyncio.create_task(schedule_fetcher.run())
        scheduler_task = asyncio.create_task(match_scheduler.run())

        # Run forever
        await asyncio.gather(
            connector_task, 
            processor_task,
            fetcher_task,
            scheduler_task
        )

    except asyncio.CancelledError:
        logger.info("Main task cancelled.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in main: {e}", exc_info=True)
    finally:
        logger.info("Shutting down services.")
        if 'scheduler_task' in locals() and not scheduler_task.done():
            scheduler_task.cancel()
        if 'fetcher_task' in locals() and not fetcher_task.done():
            fetcher_task.cancel()
        if 'processor_task' in locals() and not processor_task.done():
            processor_task.cancel()
        if 'connector_task' in locals() and not connector_task.done():
            connector_task.cancel()
        # The Flask thread is a daemon, so it will exit when the main thread does.

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")