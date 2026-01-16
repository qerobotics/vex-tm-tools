import asyncio
import threading
import os
import logging
import json
import time
from multiprocessing import Queue

from modules.tm_manager.api_client import VexTmApiClient
from modules.tm_manager.connector import VexTmConnector
from modules.tm_manager.schedule_fetcher import ScheduleFetcher
from modules.event_processor import EventProcessor
from modules.match_scheduler import MatchScheduler
from models.events import Event
from models.timer import TimerState, Timer
from server import app, set_event_queue

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reduce noisy ntfy and server debug logs: keep only INFO+ from these sources
logging.getLogger("ntfy").setLevel(logging.INFO)
logging.getLogger("server").setLevel(logging.INFO)

# Enable debug logging for ATEM and event processor to help troubleshoot video switching
logging.getLogger("modules.video.atem.controller").setLevel(logging.DEBUG)
logging.getLogger("modules.event_processor").setLevel(logging.DEBUG)

# Enable debug logging specifically for the zeros controller
logging.getLogger("modules.vfx.zeros.controller").setLevel(logging.DEBUG)

# Global references for server.py to access
spotify_controller = None
event_processor = None

def run_flask(host, port):
    """Function to run Flask app in a separate thread."""
    logger.info(f"Starting Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=False)

class TimerTickWorker:
    """Background worker that checks active timers and triggers milestones"""
    
    def __init__(self, event_queue, storage_path='storage'):
        self.event_queue = event_queue
        self.storage_path = storage_path
        self.timer_state_file = os.path.join(storage_path, 'timer_state.json')
        self.timers_saved_file = os.path.join(storage_path, 'timers_saved.json')
        self.action_lists_file = os.path.join(storage_path, 'action_lists.json')
        self.triggered_milestones = {}  # Track which milestones have been triggered per timer
        self.tm_start_triggered = {}  # Track if auto-start TM has been triggered per timer
        self.schedule_cache = None  # Cache for schedule data
        self.schedule_cache_time = 0  # Timestamp of last schedule fetch
        self.schedule_cache_ttl = 10  # Cache schedule for 10 seconds
        
    def _read_json(self, file_path, default=None):
        """Read JSON file safely"""
        try:
            if not os.path.exists(file_path):
                return default or {}
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return default or {}
    
    def _get_current_match_from_schedule(self):
        """Get current match from TM schedule with caching"""
        current_time = time.time()
        
        # Use cached schedule if still valid
        if self.schedule_cache and (current_time - self.schedule_cache_time) < self.schedule_cache_ttl:
            return self.schedule_cache.get('current_match')
        
        # Fetch fresh schedule data
        try:
            from models.config import Config
            config_file = os.path.join(self.storage_path, 'config.json')
            with open(config_file, 'r') as f:
                config = Config.from_json(f.read())
            
            vex_tm_api = config.vex_tm_api or {}
            if not vex_tm_api.get('enabled', False):
                return None
            
            from modules.tm_manager.api_client import VexTmApiClient
            api_client = VexTmApiClient(
                vex_tm_api.get('client_id'),
                vex_tm_api.get('client_secret'),
                vex_tm_api.get('api_key'),
                vex_tm_api.get('base_url', 'http://localhost:8080')
            )
            
            field_set_id = vex_tm_api.get('field_set_id', 1)
            schedule_data = api_client.get(f"/api/fieldsets/{field_set_id}/matches")
            
            if not schedule_data:
                return None
            
            # Find current match from field control states
            fields_data = api_client.get(f"/api/fieldsets/{field_set_id}/fields")
            if not fields_data or 'fields' not in fields_data:
                return None
            
            current_match = None
            for field in fields_data['fields']:
                match_name = field.get('currentMatch')
                if match_name:
                    # Parse match name and find in schedule
                    current_match = self._find_match_tuple_by_name(schedule_data, match_name)
                    if current_match:
                        break
            
            # Cache the result
            self.schedule_cache = {'current_match': current_match}
            self.schedule_cache_time = current_time
            
            return current_match
            
        except Exception as e:
            logger.debug(f"Could not fetch current match from schedule: {e}")
            return None
    
    def _find_match_tuple_by_name(self, schedule_data, match_name):
        """Find a matchTuple in the schedule by its display name (e.g., 'Q1', 'F2')"""
        if not schedule_data or not schedule_data.get('divisions'):
            return None
        
        if len(match_name) < 2:
            return None
        
        round_prefix = match_name[0].upper()
        try:
            match_num = int(match_name[1:])
        except ValueError:
            return None
        
        # Map prefix to round value
        round_map = {
            'Q': 'QUAL',
            'F': 'TOP_N',
        }
        round_value = round_map.get(round_prefix)
        if not round_value:
            return None
        
        # Search all divisions for matching matchTuple
        for division in schedule_data.get('divisions', []):
            for match in division.get('matches', []):
                match_tuple = match.get('matchInfo', {}).get('matchTuple')
                if match_tuple and match_tuple.get('round') == round_value and match_tuple.get('match') == match_num:
                    return match_tuple
        
        return None
    
    def _find_action_list_for_match(self, match_tuple):
        """Find the action list that matches the given match tuple"""
        if not match_tuple:
            return None
        
        try:
            action_lists = self._read_json(self.action_lists_file, {})
            
            for action_list_id, action_list_data in action_lists.items():
                # Check if this action list matches the current match
                if (action_list_data.get('division_id') == match_tuple.get('division') and
                    action_list_data.get('round') == match_tuple.get('round') and
                    action_list_data.get('instance') == match_tuple.get('instance') and
                    action_list_data.get('match_number') == match_tuple.get('match')):
                    logger.info(f"Found action list '{action_list_data.get('name')}' for match {match_tuple}")
                    return action_list_id
            
            return None
            
        except Exception as e:
            logger.warning(f"Error finding action list for match: {e}")
            return None
    
    async def check_timers(self):
        """Check all active timers and trigger milestones"""
        timer_states = self._read_json(self.timer_state_file, {})
        timers_saved = self._read_json(self.timers_saved_file, {})
        
        current_time = time.time()
        
        for timer_id, state_data in list(timer_states.items()):
            try:
                state = TimerState.from_dict(state_data)
                
                if not state.is_running:
                    # Clear flags for stopped timers
                    if timer_id in self.triggered_milestones:
                        del self.triggered_milestones[timer_id]
                    if timer_id in self.tm_start_triggered:
                        del self.tm_start_triggered[timer_id]
                    continue
                
                # Calculate remaining time
                remaining = state.end_timestamp - current_time
                
                # Check if timer has finished
                if remaining <= 0 and state.is_running:
                    logger.info(f"Timer {timer_id} has finished")
                    event = Event(
                        type="timer_finished",
                        field=None,
                        payload={"timer_id": timer_id}
                    )
                    await self.event_queue.put(event)
                    # Clear triggered milestones for this timer
                    if timer_id in self.triggered_milestones:
                        del self.triggered_milestones[timer_id]
                    # Clear auto-start flag
                    if timer_id in self.tm_start_triggered:
                        del self.tm_start_triggered[timer_id]
                    continue
                
                # Get timer configuration
                if timer_id not in timers_saved:
                    logger.warning(f"Timer {timer_id} is running but config not found")
                    continue
                
                timer_config = Timer.from_dict(timers_saved[timer_id])
                
                # Get milestones from action list
                # Priority: 1) Explicit action_list_id on timer, 2) Auto-detect from current match (if enabled), 3) Timer's own milestones
                milestones = timer_config.milestones
                action_list_id = timer_config.action_list_id
                
                # If no explicit action list and auto-detect is enabled, try to auto-detect from current match
                if not action_list_id and timer_config.auto_detect_action_list and timer_config.field_id:
                    current_match = self._get_current_match_from_schedule()
                    if current_match:
                        action_list_id = self._find_action_list_for_match(current_match)
                        if action_list_id:
                            logger.info(f"Auto-detected action list '{action_list_id}' for timer {timer_id} based on current match")
                
                # Load action list milestones if we have an action list ID
                if action_list_id:
                    try:
                        action_lists = self._read_json(self.action_lists_file, {})
                        
                        if action_list_id in action_lists:
                            action_list_data = action_lists[action_list_id]
                            from models.timer import ActionList
                            action_list = ActionList.from_dict(action_list_data)
                            milestones = action_list.milestones
                            logger.debug(f"Timer {timer_id} using action list '{action_list.name}' with {len(milestones)} milestones")
                    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Could not load action list for timer {timer_id}: {e}")
                
                # Auto-start TM countdown at 3 seconds
                if (timer_config.auto_start_tm and 
                    timer_config.field_id and 
                    remaining <= 4 and remaining > 0 and
                    timer_id not in self.tm_start_triggered):
                    
                    logger.info(f"Auto-starting TM countdown for timer {timer_id} at {remaining:.1f}s remaining (field {timer_config.field_id})")
                    
                    # Queue TM start command
                    event = Event(
                        type="tm_command",
                        field=timer_config.field_id,
                        payload={
                            "command": "start",
                            "params": {}
                        }
                    )
                    await self.event_queue.put(event)
                    
                    # Mark as triggered
                    self.tm_start_triggered[timer_id] = True
                
                # Check milestones
                if timer_id not in self.triggered_milestones:
                    self.triggered_milestones[timer_id] = set()
                
                for milestone in milestones:
                    milestone_key = f"{milestone.time_remaining}_{milestone.action_type}"
                    
                    # Check if this milestone should trigger
                    # Trigger when remaining time crosses the threshold (going down)
                    if (remaining <= milestone.time_remaining and 
                        milestone_key not in self.triggered_milestones[timer_id]):
                        
                        logger.info(f"Timer {timer_id} milestone triggered: {milestone.time_remaining}s - {milestone.action_type}")
                        
                        # Enqueue milestone event
                        event = Event(
                            type="timer_milestone",
                            field=None,
                            payload={
                                "timer_id": timer_id,
                                "milestone_time": milestone.time_remaining,
                                "action_type": milestone.action_type,
                                "action_payload": milestone.action_payload,
                                "message": milestone.message
                            }
                        )
                        await self.event_queue.put(event)
                        
                        # Mark as triggered
                        self.triggered_milestones[timer_id].add(milestone_key)
                
            except Exception as e:
                logger.error(f"Error checking timer {timer_id}: {e}", exc_info=True)
    
    async def run(self):
        """Main loop - runs every 50ms"""
        logger.info("Timer tick worker started")
        while True:
            try:
                await self.check_timers()
                await asyncio.sleep(0.05)  # 50ms interval
            except asyncio.CancelledError:
                logger.info("Timer tick worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in timer tick worker: {e}", exc_info=True)
                await asyncio.sleep(1)  # Back off on error

async def main():
    """
    Main function to initialize and run all components of the application.
    """
    global spotify_controller, event_processor
    
    logger.info("Initializing application...")

    # A queue that can be shared between processes if we need to scale out.
    # For now, it works fine with threads.
    event_queue = asyncio.Queue()

    # --- Load Configuration ---
    # Load config first to get credentials
    from models.config import Config
    config_file = os.path.join('storage', 'config.json')
    try:
        with open(config_file, 'r') as f:
            config = Config.from_json(f.read())
    except:
        config = Config()

    # Get VEX TM API credentials from the loaded config
    vex_tm_api_config = config.vex_tm_api
    client_id = vex_tm_api_config.get("client_id")
    client_secret = vex_tm_api_config.get("client_secret")
    api_key = vex_tm_api_config.get("api_key")
    base_url = vex_tm_api_config.get("base_url", "http://localhost:8080")
    field_set_id = int(vex_tm_api_config.get("field_set_id", os.environ.get("VEX_TM_FIELD_SET_ID", 1)))
    
    # Check for DISABLE_VEX_TM environment variable
    disable_vex_tm = os.environ.get("DISABLE_VEX_TM", "").lower() in ("true", "1", "yes")

    if not disable_vex_tm and not all([client_id, client_secret, api_key]):
        logger.error("Missing required VEX TM API configuration in config.json. Please set client_id, client_secret, and api_key under the 'vex_tm_api' key.")
        return

    # Share the queue with the Flask app for manual controls
    set_event_queue(event_queue, asyncio.get_running_loop())

    # --- Initialize Components ---
    # The EventProcessor will be initialized after we create the connector
    # so we can pass the connector reference to it
    vex_tm_connector = None
    
    # API Client
    if not disable_vex_tm:
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
    else:
        logger.info("VEX TM integration disabled via environment variable.")
        api_client = None
        vex_tm_connector = None
        schedule_fetcher = None
    
    # Now create EventProcessor with connector reference (if available)
    event_processor = EventProcessor(event_queue, tm_connector=vex_tm_connector)
    config = event_processor.config  # Use the config from event processor as source of truth
    
    # Expose spotify controller globally
    spotify_controller = event_processor.spotify_controller

    # Thread 4: Match Scheduler
    match_scheduler = MatchScheduler(event_queue)

    # Timer tick worker
    timer_worker = TimerTickWorker(event_queue)

    # Thread 1: Flask Frontend
    # The Flask app will run in its own thread so it doesn't block asyncio
    flask_thread = threading.Thread(target=run_flask, args=('0.0.0.0', 5000), daemon=True)

    # --- Start Services ---
    try:
        logger.info("Starting services...")
        flask_thread.start()

        # Create asyncio tasks for our async components
        tasks = []
        if vex_tm_connector:
            tasks.append(asyncio.create_task(vex_tm_connector.connect()))
        tasks.append(asyncio.create_task(event_processor.process_events()))
        if schedule_fetcher:
            tasks.append(asyncio.create_task(schedule_fetcher.run()))
        tasks.append(asyncio.create_task(match_scheduler.run()))
        tasks.append(asyncio.create_task(timer_worker.run()))
        
        # Keep track of tasks for cleanup
        active_tasks = tasks

        # Run forever
        await asyncio.gather(*tasks)

    except asyncio.CancelledError:
        logger.info("Main task cancelled.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in main: {e}", exc_info=True)
    finally:
        logger.info("Shutting down services.")
        # Cancel all active tasks
        if 'active_tasks' in locals():
            for task in active_tasks:
                if not task.done():
                    task.cancel()
        
        # The Flask thread is a daemon, so it will exit when the main thread does.

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")