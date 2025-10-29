import asyncio
import json
import os
import logging
import tempfile
from asyncio import Lock

from models.events import Event
from models.fields import FieldState
from models.actions import ActionMapping, AudioAction, VideoAction, LightingAction
from models.config import Config
from models.audit import AuditEntry

# Import controllers
from modules.audio.spotify.controller import SpotifyController
from modules.video.atem.controller import AtemController
from modules.vfx.zeros.controller import ZerOSController

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EventProcessor:
    def __init__(self, event_queue, storage_path='storage'):
        self.event_queue = event_queue
        self.storage_path = storage_path
        self.fields_dir = os.path.join(self.storage_path, 'fields')
        self.actions_file = os.path.join(self.storage_path, 'actions.json')
        self.config_file = os.path.join(self.storage_path, 'config.json')
        self.scheduled_matches_file = os.path.join(self.storage_path, 'scheduled_matches.json')
        self.popups_file = os.path.join(self.storage_path, 'popups.json')
        self.audit_log_file = os.path.join(self.storage_path, 'events.log')
        
        self.config = self._load_config()
        self.action_mappings = self._load_action_mappings()
        
        self._file_locks = {}
        os.makedirs(self.fields_dir, exist_ok=True)

        # Initialize controllers
        self.spotify_controller = self._init_spotify_controller()
        self.atem_controller = self._init_atem_controller()
        self.zeros_controller = self._init_zeros_controller()

    def _load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                return Config.from_json(f.read())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Config file not found or invalid at {self.config_file}. Using default config. Error: {e}")
            return Config()

    def _init_spotify_controller(self):
        if self.config.paused.get("audio"):
            logger.info("Audio is paused in config. Skipping Spotify controller initialization.")
            return None
        
        creds = self.config.device_ips.get("spotify", {})
        if all(k in creds for k in ["client_id", "client_secret", "redirect_uri"]):
            return SpotifyController(
                client_id=creds["client_id"],
                client_secret=creds["client_secret"],
                redirect_uri=creds["redirect_uri"],
                device_name=self.config.spotify_device_id
            )
        logger.warning("Spotify credentials not found in config.json. Spotify controller not initialized.")
        return None

    def _init_atem_controller(self):
        if self.config.paused.get("video"):
            logger.info("Video is paused in config. Skipping ATEM controller initialization.")
            return None
            
        ip = self.config.device_ips.get("atem")
        if ip:
            return AtemController(ip)
        logger.warning("ATEM IP not found in config.json. ATEM controller not initialized.")
        return None

    def _init_zeros_controller(self):
        if self.config.paused.get("lighting"):
            logger.info("Lighting is paused in config. Skipping ZerOS controller initialization.")
            return None

        zeros_config = self.config.device_ips.get("zeros")
        if zeros_config and "ip" in zeros_config:
            return ZerOSController(zeros_config["ip"], zeros_config.get("port", 8000))
        logger.warning("ZerOS IP not found in config.json. ZerOS controller not initialized.")
        return None

    def _get_lock(self, file_path):
        if file_path not in self._file_locks:
            self._file_locks[file_path] = Lock()
        return self._file_locks[file_path]

    def _load_action_mappings(self):
        try:
            with open(self.actions_file, 'r') as f:
                data = json.load(f)
                return ActionMapping.from_dict(data)
        except FileNotFoundError:
            logger.warning(f"Action mappings file not found at {self.actions_file}. No actions will be triggered.")
            return ActionMapping()
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {self.actions_file}.")
            return ActionMapping()

    async def _log_audit_entry(self, entry):
        lock = self._get_lock(self.audit_log_file)
        async with lock:
            try:
                await asyncio.to_thread(self._write_to_log, entry.to_json() + '\n')
            except Exception as e:
                logger.error(f"Failed to write to audit log {self.audit_log_file}: {e}")

    def _write_to_log(self, content):
        with open(self.audit_log_file, 'a') as f:
            f.write(content)

    async def _atomic_write(self, file_path, data):
        lock = self._get_lock(file_path)
        async with lock:
            try:
                await asyncio.to_thread(self._write_atomic_file, file_path, data)
                logger.info(f"Successfully wrote to {file_path}")
            except Exception as e:
                logger.error(f"Failed to atomically write to {file_path}: {e}")

    def _write_atomic_file(self, file_path, data):
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
        try:
            with os.fdopen(temp_fd, 'w') as temp_f:
                temp_f.write(data)
            os.rename(temp_path, file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    async def _get_field_state(self, field_id):
        field_file = os.path.join(self.fields_dir, f"field{field_id}.json")
        lock = self._get_lock(field_file)
        async with lock:
            try:
                content = await asyncio.to_thread(self._read_file, field_file)
                return FieldState.from_json(content)
            except FileNotFoundError:
                logger.info(f"No existing state for field {field_id}, creating new one.")
                return FieldState(field_id=field_id, state="standby")
            except json.JSONDecodeError:
                logger.error(f"Could not decode JSON for field {field_id}, creating new one.")
                return FieldState(field_id=field_id, state="standby")

    def _read_file(self, file_path):
        with open(file_path, 'r') as f:
            return f.read()

    async def _update_field_state(self, event):
        if not event.field:
            logger.info(f"Event {event.id} has no field, skipping state update.")
            return None, None

        field_id = event.field
        current_state = await self._get_field_state(field_id)
        previous_state_name = current_state.state
        
        new_state = self._determine_new_state(event, current_state)
        
        if new_state and new_state != current_state.state:
            current_state.state = new_state
            current_state.last_updated = event.timestamp
            if event.type == "fieldMatchAssigned":
                current_state.match_id = event.payload.get("match")
            
            field_file = os.path.join(self.fields_dir, f"field{field_id}.json")
            await self._atomic_write(field_file, current_state.to_json())
            
            logger.info(f"Updated field {field_id} state to {new_state}")
            return previous_state_name, new_state
        
        return None, None

    def _determine_new_state(self, event, current_state):
        # This logic will be based on the VEX TM API docs and the desired state flow
        event_type_to_state = {
            "fieldMatchAssigned": "queued",
            "fieldActivated": "active", # Or maybe a pre-active state?
            "matchStarted": "active",
            "matchStopped": "finish",
            "audienceDisplayChanged": None # This might not change field state directly
        }
        
        new_state = event_type_to_state.get(event.type)

        # More complex logic can be added here, e.g., from 'finish' it should go to 'standby'
        if current_state.state == "finish" and new_state is None:
             return "standby"

        return new_state

    async def _trigger_actions(self, event, old_state, new_state):
        actions_to_run = []
        
        # Check for actions based on event type
        if event.type in self.action_mappings.on_event:
            actions_to_run.extend(self.action_mappings.on_event[event.type])

        # Check for actions based on state change
        if old_state and new_state:
            state_transition = f"{old_state}->{new_state}"
            if state_transition in self.action_mappings.on_state_change:
                actions_to_run.extend(self.action_mappings.on_state_change[state_transition])

        for action_data in actions_to_run:
            await self._execute_action(action_data, event)

    async def _execute_action(self, action_data, event=None):
        action_type = action_data.get("type")
        if not action_type:
            logger.warning("Action data is missing 'type'.")
            return

        logger.debug(f"Executing action: {action_data}")

        if action_type == "audio":
            if self.spotify_controller and not self.config.paused.get("audio"):
                action = AudioAction(**action_data)
                self.spotify_controller.execute_action(action)
            else:
                logger.info("Skipping audio action because controller is not available or audio is paused.")
        
        elif action_type == "video":
            if self.atem_controller and not self.config.paused.get("video"):
                # Map field_id to camera_id if not specified and event is available
                if "camera_id" not in action_data and event and event.field:
                    action_data["camera_id"] = self.config.field_to_camera.get(str(event.field))
                
                if action_data.get("camera_id"):
                    action = VideoAction(**action_data)
                    self.atem_controller.execute_action(action)
                else:
                    logger.warning(f"No camera_id for video action on event: {event.id if event else 'N/A'}")
            else:
                logger.info("Skipping video action because controller is not available or video is paused.")

        elif action_type == "lighting":
            if self.zeros_controller and not self.config.paused.get("lighting"):
                action = LightingAction(**action_data)
                self.zeros_controller.execute_action(action)
            else:
                logger.info("Skipping lighting action because controller is not available or lighting is paused.")
        
        else:
            logger.warning(f"Unknown action type: {action_type}")


    async def _handle_special_events(self, event):
        if event.type == "match_scheduled":
            logger.info(f"Handling match_scheduled event: {event.payload}")
            # This file is consumed by the frontend to show popups
            await self._atomic_write(self.scheduled_matches_file, json.dumps(event.payload, indent=4))
            return True
            
        if event.type == "manual_popup":
            logger.info(f"Handling manual_popup event: {event.payload}")
            # This file holds a list of active popups
            # A real implementation would manage this list (add, remove expired)
            await self._atomic_write(self.popups_file, json.dumps([event.payload], indent=4))
            return True
        
        if event.type == "manual_action":
            logger.info(f"Handling manual action: {event.payload}")
            await self._execute_action(event.payload)
            return True
            
        return False

    async def process_events(self):
        logger.info("Event processor started.")
        while True:
            try:
                event = await self.event_queue.get()
                logger.info(f"Processing event: {event.to_json()}")

                # Handle special, non-field-related events first
                if await self._handle_special_events(event):
                    self.event_queue.task_done()
                    continue

                # 1. Update field state
                old_state, new_state = await self._update_field_state(event)

                # 2. Trigger actions
                if old_state or new_state:
                    await self._trigger_actions(event, old_state, new_state)

                self.event_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)


if __name__ == '__main__':
    # Example usage for testing
    async def main():
        event_queue = asyncio.Queue()
        processor = EventProcessor(event_queue)

        # Start the processor
        processing_task = asyncio.create_task(processor.process_events())

        # Simulate some events
        await event_queue.put(Event(type="fieldMatchAssigned", field=1, payload={"match": "Q1"}))
        await asyncio.sleep(1)
        await event_queue.put(Event(type="fieldActivated", field=1))
        await asyncio.sleep(1)
        await event_queue.put(Event(type="matchStarted", field=1))
        await asyncio.sleep(1)
        await event_queue.put(Event(type="matchStopped", field=1))
        await asyncio.sleep(1)
        await event_queue.put(Event(type="fieldMatchAssigned", field=2, payload={"match": "Q2"}))


        await event_queue.join() # Wait for all items to be processed
        processing_task.cancel()

    # Create a dummy actions.json for testing
    if not os.path.exists('storage'):
        os.makedirs('storage')
    with open('storage/actions.json', 'w') as f:
        json.dump({
            "on_event": {
                "matchStarted": [{"type": "audio", "command": "play_match_music"}]
            },
            "on_state_change": {
                "standby->queued": [{"type": "lighting", "preset_id": "ready"}],
                "queued->active": [{"type": "video", "camera_id": "field_cam"}],
                "active->finish": [{"type": "lighting", "preset_id": "finish_show"}]
            }
        }, f)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
