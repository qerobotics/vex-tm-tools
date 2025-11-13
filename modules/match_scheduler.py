import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
import tempfile
import uuid

from models.events import Event
from models.config import Config

logger = logging.getLogger(__name__)

class MatchScheduler:
    def __init__(self, event_queue, storage_path='storage', interval=10):
        self.event_queue = event_queue
        self.storage_path = storage_path
        self.schedule_file = os.path.join(self.storage_path, 'schedule.json')
        self.config_file = os.path.join(self.storage_path, 'config.json')
        self.fields_dir = os.path.join(self.storage_path, 'fields')
        self.notified_matches_file = os.path.join(self.storage_path, 'notified_matches.json')
        self.popups_file = os.path.join(self.storage_path, 'popups.json')
        self.interval = interval
        self.running = False
        self.notified_matches = self._load_notified_matches()

    def _atomic_write(self, file_path, data):
        try:
            temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
            with os.fdopen(temp_fd, 'w') as temp_f:
                json.dump(data, temp_f, indent=4)
            os.replace(temp_path, file_path)
            logger.debug(f"Successfully wrote to {file_path}")
        except Exception as e:
            logger.error(f"Failed to atomically write to {file_path}: {e}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)

    def _load_notified_matches(self):
        try:
            with open(self.notified_matches_file, 'r') as f:
                return set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def _save_notified_matches(self):
        self._atomic_write(self.notified_matches_file, list(self.notified_matches))

    def _load_json(self, file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _get_active_match_numbers(self):
        active_matches = {}
        if not os.path.exists(self.fields_dir):
            return active_matches
        
        for filename in os.listdir(self.fields_dir):
            if filename.endswith(".json"):
                state = self._load_json(os.path.join(self.fields_dir, filename))
                if state and state.get('state') in ['active', 'queued', 'finish']:
                    match_info = state.get('match_id')
                    if match_info:
                        # Assuming match_id is a dict like {"match": 1, ...}
                        match_num = match_info.get('match')
                        div_id = match_info.get('division')
                        if div_id not in active_matches:
                            active_matches[div_id] = set()
                        active_matches[div_id].add(match_num)
        return active_matches

    async def run(self):
        """Periodically checks the schedule and queues matches that are about to start."""
        logger.info(f"Match scheduler started. Will check every {self.interval} seconds.")
        while True:
            await self.check_schedule()
            await asyncio.sleep(self.interval)

    async def check_schedule(self):
        try:
            config_data = self._load_json(self.config_file)
            config = Config.from_dict(config_data) if config_data else Config()

            if config.match_queue_pause and config.match_queue_pause.get('start'):
                logger.info("Match scheduling is currently paused via config.")
                return

            schedule = self._load_json(self.schedule_file)
            if not schedule or "divisions" not in schedule:
                logger.warning("Schedule not found or invalid. Skipping scheduling run.")
                return

            active_matches_by_div = self._get_active_match_numbers()
            lead_matches = config.schedule_lead_matches
            popups = self._load_json(self.popups_file) or []

            for division in schedule["divisions"]:
                div_id = division["id"]
                active_match_nums = active_matches_by_div.get(div_id, set())
                
                last_played_match_num = max(active_match_nums) if active_match_nums else 0

                for match in division.get("matches", []):
                    match_info = match.get("matchInfo", {})
                    match_tuple = match_info.get("matchTuple", {})
                    match_num = match_tuple.get("match")
                    
                    if not match_num:
                        continue

                    is_upcoming = last_played_match_num < match_num <= last_played_match_num + lead_matches
                    notification_key = f"{div_id}-{match_num}"

                    if is_upcoming and notification_key not in self.notified_matches:
                        logger.info(f"Match {match_num} in division {div_id} is upcoming. Creating popup notification.")
                        
                        teams_in_match = [team['number'] for alliance in match_info.get('alliances', []) for team in alliance.get('teams', [])]
                        
                        rooms_for_match = []
                        for room_id, room_data in config.rooms.items():
                            if any(team in room_data.get("teams", []) for team in teams_in_match):
                                rooms_for_match.append(room_id)

                        if rooms_for_match:
                            popup_title = f"Upcoming Match: {match_num}"
                            popup_message = f"Teams: {', '.join(teams_in_match)}"
                            popup = {
                                "id": str(uuid.uuid4()),
                                "room_ids": rooms_for_match,
                                "title": popup_title,
                                "message": popup_message,
                                "duration": 30,
                                "type": "toast",
                                "source": "match_scheduler"
                            }
                            popups.append(popup)
                            
                            self.notified_matches.add(notification_key)
            
            self._atomic_write(self.popups_file, popups)
            self._save_notified_matches()
        except Exception as e:
            logger.error(f"An error occurred in the match scheduler loop: {e}", exc_info=True)

    def stop(self):
        self.running = False

if __name__ == '__main__':
    # Example usage for testing
    async def main():
        logging.basicConfig(level=logging.INFO)
        event_queue = asyncio.Queue()
        
        # Create dummy files for testing
        storage_path = 'storage_test'
        os.makedirs(os.path.join(storage_path, 'fields'), exist_ok=True)
        
        # Dummy config
        with open(os.path.join(storage_path, 'config.json'), 'w') as f:
            json.dump({
                "schedule_lead_matches": 3,
                "rooms": {
                    "room1": {"teams": ["123A", "456B"]},
                    "room2": {"teams": ["789C"]}
                }
            }, f)
            
        # Dummy schedule
        with open(os.path.join(storage_path, 'schedule.json'), 'w') as f:
            json.dump({
                "divisions": [{
                    "id": 1, "name": "Main", "matches": [
                        {"matchInfo": {"matchTuple": {"match": 1}, "alliances": [{"teams": [{"number": "111A"}]}]}},
                        {"matchInfo": {"matchTuple": {"match": 2}, "alliances": [{"teams": [{"number": "123A"}]}]}},
                        {"matchInfo": {"matchTuple": {"match": 3}, "alliances": [{"teams": [{"number": "222B"}]}]}},
                        {"matchInfo": {"matchTuple": {"match": 4}, "alliances": [{"teams": [{"number": "789C"}]}]}},
                    ]
                }]
            }, f)

        # Dummy field state
        with open(os.path.join(storage_path, 'fields', 'field1.json'), 'w') as f:
            json.dump({"field_id": 1, "state": "active", "match_id": {"division": 1, "match": 1}}, f)

        scheduler = MatchScheduler(event_queue, storage_path=storage_path, interval=5)
        scheduler_task = asyncio.create_task(scheduler.run())

        # Consume events from queue
        try:
            while True:
                event = await asyncio.wait_for(event_queue.get(), timeout=15)
                print(f"Dequeued event: {event.to_json()}")
                event_queue.task_done()
        except asyncio.TimeoutError:
            print("Test finished.")
        
        scheduler.stop()
        await scheduler_task
        
        # Cleanup
        import shutil
        shutil.rmtree(storage_path)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down.")
