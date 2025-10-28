import asyncio
import json
import os
import logging
import time

from modules.tm_manager.api_client import VexTmApiClient

logger = logging.getLogger(__name__)

class ScheduleFetcher:
    def __init__(self, api_client, storage_path='storage', interval=300):
        self.api_client = api_client
        self.storage_path = storage_path
        self.schedule_file = os.path.join(self.storage_path, 'schedule.json')
        self.interval = interval
        self.running = False

    def _fetch_and_save_schedule(self):
        logger.info("Fetching divisions...")
        divisions_data = self.api_client.get("/api/divisions")
        if not divisions_data or "divisions" not in divisions_data:
            logger.error("Could not fetch divisions. Aborting schedule fetch.")
            return

        full_schedule = {"divisions": []}

        for division in divisions_data["divisions"]:
            div_id = division["id"]
            logger.info(f"Fetching schedule for division {div_id}...")
            matches_data = self.api_client.get(f"/api/matches/{div_id}")
            
            if matches_data and "matches" in matches_data:
                division_schedule = {
                    "id": div_id,
                    "name": division["name"],
                    "matches": matches_data["matches"]
                }
                full_schedule["divisions"].append(division_schedule)
            else:
                logger.warning(f"No matches found for division {div_id}.")
        
        self._atomic_write(self.schedule_file, json.dumps(full_schedule, indent=4))
        logger.info("Successfully fetched and saved the full schedule.")

    def _atomic_write(self, file_path, data):
        temp_path = file_path + ".tmp"
        try:
            with open(temp_path, 'w') as f:
                f.write(data)
            os.rename(temp_path, file_path)
        except Exception as e:
            logger.error(f"Failed to atomically write to {file_path}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    async def run(self):
        self.running = True
        logger.info(f"Schedule fetcher started. Will fetch every {self.interval} seconds.")
        while self.running:
            try:
                self._fetch_and_save_schedule()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"An error occurred in the schedule fetcher loop: {e}", exc_info=True)
                # Wait a bit longer after an error to avoid spamming
                await asyncio.sleep(self.interval * 2)

    def stop(self):
        self.running = False

if __name__ == '__main__':
    # Example usage for testing
    async def main():
        logging.basicConfig(level=logging.INFO)
        
        client_id = os.environ.get("VEX_TM_CLIENT_ID")
        client_secret = os.environ.get("VEX_TM_CLIENT_SECRET")
        api_key = os.environ.get("VEX_TM_API_KEY")
        base_url = os.environ.get("VEX_TM_BASE_URL", "http://localhost:8080")

        if not all([client_id, client_secret, api_key]):
            logger.error("Missing required environment variables for VEX TM connection.")
            return

        if not os.path.exists('storage'):
            os.makedirs('storage')

        api_client = VexTmApiClient(client_id, client_secret, api_key, base_url)
        fetcher = ScheduleFetcher(api_client, interval=15) # Fetch every 15s for testing
        
        fetch_task = asyncio.create_task(fetcher.run())
        
        await asyncio.sleep(35) # Run for a bit
        fetcher.stop()
        await fetch_task

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down.")
