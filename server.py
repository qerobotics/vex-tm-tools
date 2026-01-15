import asyncio
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, g
import os
import json
import logging
import tempfile
from functools import wraps
import uuid
import queue
from flask import Response
import time
import requests
import traceback

from models.fields import FieldState
from models.config import Config
from models.events import Event
from models.timer import Timer, TimerMilestone, TimerState
from userManager import UserManager
from modules.tm_manager.api_client import VexTmApiClient

# This is a placeholder for where the event queue would be shared
# In a real app, this would be managed more robustly (e.g., via a global context or passed in)
event_queue = None
loop = None

# Storage paths used throughout the server. Define these early so functions that
# run during module import (like logging configuration) can read the config file.
STORAGE_PATH = 'storage'
FIELDS_DIR = os.path.join(STORAGE_PATH, 'fields')
CONFIG_FILE = os.path.join(STORAGE_PATH, 'config.json')
SCHEDULED_MATCHES_FILE = os.path.join(STORAGE_PATH, 'scheduled_matches.json')
POPUPS_FILE = os.path.join(STORAGE_PATH, 'popups.json')
PRESETS_FILE = os.path.join(STORAGE_PATH, 'presets.json')

def _read_json(file_path, default=None):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def set_event_queue(queue, main_loop):
    global event_queue, loop
    event_queue = queue
    loop = main_loop

# Create a queue to hold log records
log_queue = queue.Queue()

class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

# Configure logging
# Keep the existing basicConfig, but also add our queue handler
queue_handler = QueueLogHandler(log_queue)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
queue_handler.setFormatter(formatter)
logging.getLogger().addHandler(queue_handler)

def send_ntfy_notification(title, message, priority="high", tags="rotating_light"):
    """Helper function to send a notification to the configured ntfy endpoint."""
    # ntfy notifications have been disabled per user request.
    # Keep the function as a no-op so callers don't need to be changed.
    logging.getLogger(__name__).debug("ntfy notifications disabled; skipping send_ntfy_notification.")
    return

class NtfyLogHandler(logging.Handler):
    """
    A logging handler that sends notifications for ERROR and CRITICAL logs
    to a configured ntfy endpoint.
    """
    def __init__(self):
        super().__init__()

    def emit(self, record):
        """
        Formats and sends the log record as a notification.
        """
        # ntfy notifications via logging handler are disabled.
        # We leave this handler as a no-op to avoid changing places that may instantiate it.
        logging.getLogger(__name__).debug("NtfyLogHandler.emit called but notifications are disabled.")
        return

# Configure logging
# Keep the existing basicConfig, but also add our queue handler
queue_handler = QueueLogHandler(log_queue)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
queue_handler.setFormatter(formatter)
logging.getLogger().addHandler(queue_handler)

# Add the ntfy handler to the root logger if configured
# ntfy log handler is intentionally disabled. If you want to re-enable ntfy
# notifications, restore the lines above that add NtfyLogHandler when a
# ntfy_error_endpoint is configured.

logging.getLogger().setLevel(logging.ERROR) # Log only errors and above

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_insecure_default_secret_key")

# S2: Warn if using default secret key
if app.secret_key == "a_very_insecure_default_secret_key":
    logger.warning("⚠️  SECURITY WARNING: Using default Flask secret key! Set FLASK_SECRET_KEY environment variable in production!")

userManager = UserManager()

STORAGE_PATH = 'storage'
FIELDS_DIR = os.path.join(STORAGE_PATH, 'fields')
CONFIG_FILE = os.path.join(STORAGE_PATH, 'config.json')
SCHEDULED_MATCHES_FILE = os.path.join(STORAGE_PATH, 'scheduled_matches.json')
POPUPS_FILE = os.path.join(STORAGE_PATH, 'popups.json')
PRESETS_FILE = os.path.join(STORAGE_PATH, 'presets.json')
TIMERS_SAVED_FILE = os.path.join(STORAGE_PATH, 'timers_saved.json')
TIMER_STATE_FILE = os.path.join(STORAGE_PATH, 'timer_state.json')

def _atomic_write(file_path, data):
    try:
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
        with os.fdopen(temp_fd, 'w') as temp_f:
            json.dump(data, temp_f, indent=4)
        os.replace(temp_path, file_path)
        logger.info(f"Successfully wrote to {file_path}")
    except Exception as e:
        logger.error(f"Failed to atomically write to {file_path}: {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

def login_required(roles=None):
    if roles is None:
        roles = ["ANY"]
    if isinstance(roles, str):
        roles = [roles]

    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if 'user' not in session:
                flash("You must be logged in to view this page.", "danger")
                return redirect(url_for('login', next=request.url))
            
            user_role = session.get('user', {}).get('role')

            # Owners and admins have universal access
            if user_role in ['owner', 'admin']:
                return fn(*args, **kwargs)

            # Allow any logged-in user if "ANY" is in roles
            if "ANY" in roles:
                return fn(*args, **kwargs)

            # Check if the user's role is in the allowed list
            if user_role not in roles:
                flash("You do not have permission to view this page.", "danger")
                return redirect(url_for('index'))
            
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def get_field_statuses():
    """
    Scans the fields directory and returns a list of field states.
    """
    statuses = []
    if not os.path.exists(FIELDS_DIR):
        return statuses

    for filename in sorted(os.listdir(FIELDS_DIR)):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(FIELDS_DIR, filename), 'r') as f:
                    data = json.load(f)
                    # Basic validation
                    if 'field_id' in data and 'state' in data:
                        statuses.append(FieldState.from_dict(data))
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error reading or parsing {filename}: {e}")
    return statuses

@app.before_request
def before_request():
    g.user = None
    if 'user' in session:
        g.user = session['user']

@app.route('/')
def index():
    """
    Serves the main dashboard page.
    """
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """
    API endpoint to get the current status of all fields.
    """
    field_statuses = get_field_statuses()
    return jsonify([status.to_dict() for status in field_statuses])

@app.route('/api/health')
@login_required(roles=["admin", "owner"])
def api_health():
    """
    D3: System health metrics endpoint (admin only).
    Returns CPU usage, memory, uptime, event queue size, connection status, etc.
    """
    import psutil
    from main import event_processor
    
    # Get process info
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    
    # Calculate uptime
    create_time = process.create_time()
    uptime_seconds = time.time() - create_time
    
    # Get event processor stats
    websocket_events_count = 0
    if event_processor:
        websocket_events_count = len(event_processor.websocket_events)
    
    # Get field connection status
    field_statuses = get_field_statuses()
    connected_fields = sum(1 for fs in field_statuses if getattr(fs, 'websocket_connected', True))
    total_fields = len(field_statuses)
    
    health_data = {
        'uptime_seconds': int(uptime_seconds),
        'uptime_formatted': format_uptime(uptime_seconds),
        'memory': {
            'rss_mb': round(memory_info.rss / (1024 * 1024), 2),
            'vms_mb': round(memory_info.vms / (1024 * 1024), 2),
            'percent': round(process.memory_percent(), 2)
        },
        'cpu_percent': round(process.cpu_percent(interval=0.1), 2),
        'threads': process.num_threads(),
        'fields': {
            'total': total_fields,
            'connected': connected_fields,
            'disconnected': total_fields - connected_fields
        },
        'events': {
            'websocket_buffer': websocket_events_count
        },
        'timestamp': int(time.time())
    }
    
    return jsonify(health_data)

def format_uptime(seconds):
    """Format uptime in human-readable format."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

@app.route('/api/rankings')
@login_required()
def api_rankings():
    """
    API endpoint to get rankings. Returns empty rankings if not available.
    """
    return jsonify({"rankings": []})

@app.route('/api/recent_actions')
@login_required(roles=["admin", "owner"])
def api_recent_actions():
    """
    D4: Recent actions feed endpoint (admin only).
    Returns a list of recent timer actions that have been executed.
    """
    try:
        # Read actions from storage/actions.json
        actions_file = os.path.join(STORAGE_PATH, 'actions.json')
        actions = _read_json(actions_file, [])
        
        # Ensure it's a list
        if not isinstance(actions, list):
            actions = []
        
        # Return most recent 50 actions
        recent = actions[-50:] if len(actions) > 50 else actions[:]
        recent.reverse()  # Most recent first
        
        return jsonify({"status": "ok", "actions": recent})
    except Exception as e:
        logging.error(f"Error fetching recent actions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        logging.debug(f"Login attempt for user: {username}")
        auth_result = userManager.Auth(username, password)
        
        if auth_result['user']:
            user_dict = auth_result['user'].__dict__
            session['user'] = user_dict
            logging.debug(f"User '{username}' logged in, session set to: {user_dict}")
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            logging.warning(f"Login failed for user '{username}': {auth_result['message']}")
            flash(auth_result['message'], 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/config_editor')
@login_required(roles=["admin"])
def config_editor_page():
    """
    Serves the configuration editor page.
    """
    return render_template('config_editor.html')

@app.route('/api/storage_files')
@login_required(roles=["admin"])
def list_storage_files():
    """
    API endpoint to list all .json files in the storage directory.
    """
    try:
        files = [f for f in os.listdir(STORAGE_PATH) if f.endswith('.json')]
        return jsonify(files)
    except FileNotFoundError:
        return jsonify([])

@app.route('/api/storage_file_content')
@login_required(roles=["admin"])
def get_storage_file_content():
    """
    API endpoint to get the content of a specific file in the storage directory.
    """
    file_name = request.args.get('file')
    if not file_name or not file_name.endswith('.json'):
        return "Invalid file name", 400

    # Security check: ensure the file is directly within the STORAGE_PATH
    file_path = os.path.join(STORAGE_PATH, os.path.basename(file_name))
    if not os.path.abspath(file_path).startswith(os.path.abspath(STORAGE_PATH)):
        return "Directory traversal attempt detected", 403

    try:
        with open(file_path, 'r') as f:
            # We return as plain text to preserve formatting in the textarea
            return f.read()
    except FileNotFoundError:
        return "File not found", 404
    except Exception as e:
        logger.error(f"Error reading file {file_name}: {e}")
        return "Error reading file", 500

@app.route('/api/save_storage_file', methods=['POST'])
@login_required(roles=["admin"])
def save_storage_file():
    """
    API endpoint to save content to a specific file in the storage directory.
    """
    data = request.get_json()
    file_name = data.get('file')
    content = data.get('content')

    if not file_name or not file_name.endswith('.json') or content is None:
        return jsonify({"error": "Invalid request. 'file' and 'content' are required."}), 400

    # Security check
    file_path = os.path.join(STORAGE_PATH, os.path.basename(file_name))
    if not os.path.abspath(file_path).startswith(os.path.abspath(STORAGE_PATH)):
        return jsonify({"error": "Directory traversal attempt detected"}), 403

    try:
        # Validate that the content is valid JSON before writing
        json.loads(content)
        # Use _atomic_write with the raw string content
        # We need to modify _atomic_write to handle string data or do it here
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
        with os.fdopen(temp_fd, 'w') as temp_f:
            temp_f.write(content)
        os.rename(temp_path, file_path)
        logger.info(f"Successfully wrote to {file_path}")
        
        return jsonify({"status": "ok"})
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format. Please correct it and try again."}), 400
    except Exception as e:
        logger.error(f"Failed to save file {file_name}: {e}")
        return jsonify({"error": "An internal error occurred while saving the file."}), 500


@app.route('/pause', methods=['GET', 'POST'])
@login_required(roles=["admin"])
def pause_controls():
    """
    Page for pausing/resuming action categories.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    config = Config.from_dict(config_data)

    if request.method == 'POST':
        # Update paused state from form data
        config.paused['audio'] = 'audio' in request.form
        config.paused['video'] = 'video' in request.form
        config.paused['lighting'] = 'lighting' in request.form
        
        _atomic_write(CONFIG_FILE, config.to_dict())
        return redirect(url_for('pause_controls'))

    return render_template('pause.html', paused=config.paused)

@app.route('/admin/users')
@login_required(roles=["admin"])
def manage_users_page():
    """
    Serves the user management page.
    """
    return render_template('manage_users.html')

@app.route('/api/users', methods=['GET'])
@login_required(roles=["admin"])
def get_users():
    """
    API endpoint to get all users.
    """
    users = userManager.list_users()
    return jsonify([user.__dict__ for user in users])

@app.route('/api/users/<username>', methods=['GET'])
@login_required(roles=["admin"])
def get_user(username):
    """
    API endpoint to get a single user's details.
    """
    user_data = userManager.getDetails(username)
    if user_data:
        role = user_data[2]
        email = user_data[3] if len(user_data) > 3 else None
        return jsonify({"userName": username, "role": role, "email": email})
    return jsonify({"error": "User not found"}), 404

@app.route('/api/users/add', methods=['POST'])
@login_required(roles=["admin"])
def add_user_api():
    """
    API endpoint to add a new user.
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    email = data.get('email')

    if not all([username, password, role]):
        return jsonify({"error": "Username, password, and role are required."}), 400
    
    if role == 'owner':
        return jsonify({"error": "The 'owner' role cannot be assigned via the API."}), 403

    try:
        userManager.Signup(username, password, role, email)
        return jsonify({"status": "ok"})
    except FileExistsError:
        return jsonify({"error": "User already exists."}), 409
    except Exception as e:
        logger.error(f"Error adding user {username}: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

@app.route('/api/users/update/<username>', methods=['POST'])
@login_required(roles=["admin"])
def update_user_api(username):
    """
    API endpoint to update a user.
    """
    data = request.get_json()
    role = data.get('role')
    email = data.get('email')
    new_password = data.get('new_password')

    if role == 'owner':
        return jsonify({"error": "The 'owner' role cannot be assigned via the API."}), 403

    try:
        # Update role and email
        userManager.update_user(username, role, email)

        # If a new password is provided, change it
        if new_password:
            userManager.changePassword(username, new_password)
            
        return jsonify({"status": "ok"})
    except FileNotFoundError:
        return jsonify({"error": "User not found."}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        logger.error(f"Error updating user {username}: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

@app.route('/api/users/delete/<username>', methods=['POST'])
@login_required(roles=["admin"])
def delete_user_api(username):
    """
    API endpoint to delete a user.
    """
    # Prevent users from deleting themselves
    if 'user' in session and session['user']['userName'] == username:
        return jsonify({"error": "You cannot delete your own account."}), 403

    try:
        if userManager.delete_user(username):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"error": "User not found."}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        logger.error(f"Error deleting user {username}: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

@app.route('/admin/rooms', methods=['GET'])
@login_required(roles=["admin"])
def room_management():
    """
    Admin page for managing rooms.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    rooms = config_data.get("rooms", {})
    return render_template('room_management.html', rooms=rooms)

@app.route('/admin/rooms/add', methods=['POST'])
@login_required(roles=["admin"])
def add_room():
    """
    Adds a new room to the configuration.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    if "rooms" not in config_data:
        config_data["rooms"] = {}

    room_id = request.form['room_id']
    if room_id in config_data["rooms"]:
        # Handle error, room already exists
        return "Room ID already exists", 400

    teams = [team.strip() for team in request.form.get('teams', '').split(',') if team.strip()]
    config_data["rooms"][room_id] = {
        "youtube_stream_url": request.form['youtube_stream_url'],
        "teams": teams
    }
    
    _atomic_write(CONFIG_FILE, config_data)
    return redirect(url_for('room_management'))

@app.route('/admin/rooms/edit/<room_id>', methods=['GET', 'POST'])
@login_required(roles=["admin"])
def edit_room(room_id):
    """
    Edits an existing room.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    room = config_data.get("rooms", {}).get(room_id)
    if not room:
        return "Room not found", 404

    if request.method == 'POST':
        teams = [team.strip() for team in request.form.get('teams', '').split(',') if team.strip()]
        config_data["rooms"][room_id]['youtube_stream_url'] = request.form['youtube_stream_url']
        config_data["rooms"][room_id]['teams'] = teams
        _atomic_write(CONFIG_FILE, config_data)
        return redirect(url_for('room_management'))

    return render_template('edit_room.html', room_id=room_id, room=room)

@app.route('/admin/rooms/delete/<room_id>', methods=['POST'])
@login_required(roles=["admin"])
def delete_room(room_id):
    """
    Deletes a room.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    if "rooms" in config_data and room_id in config_data["rooms"]:
        del config_data["rooms"][room_id]
        _atomic_write(CONFIG_FILE, config_data)
    
    return redirect(url_for('room_management'))

@app.route('/controls')
@login_required(roles=["admin", "av"])
def controls_page():
    """
    Page for manual controls.
    """
    return render_template('controls.html')

@app.route('/room/<room_id>')
def room_page(room_id):
    """
    Public page for a specific room.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    room_info = config_data.get("rooms", {}).get(room_id)
    if not room_info:
        return "Room not found", 404
    return render_template('room.html', room_id=room_id, room_info=room_info)

@app.route('/api/scheduled_matches')
def api_scheduled_matches():
    """
    API endpoint to get scheduled matches from schedule.json in frontend-friendly format.
    Transforms nested schedule structure into flat array with match details.
    """
    try:
        schedule_file = os.path.join(STORAGE_PATH, 'schedule.json')
        logger.info(f"Reading schedule from: {schedule_file}")
        logger.info(f"File exists: {os.path.exists(schedule_file)}")
        
        schedule_data = _read_json(schedule_file, default={})
        logger.info(f"Schedule data loaded. Keys: {list(schedule_data.keys())}")
        
        matches = []
        divisions = schedule_data.get('divisions', [])
        logger.info(f"Found {len(divisions)} divisions")
        
        for div_idx, division in enumerate(divisions):
            div_matches = division.get('matches', [])
            logger.info(f"Division {div_idx}: {len(div_matches)} matches")
            
            for match_idx, match in enumerate(div_matches):
                match_info = match.get('matchInfo', {})
                match_tuple = match_info.get('matchTuple', {})
                alliances = match_info.get('alliances', [])
                
                logger.debug(f"  Match {match_idx}: tuple={match_tuple}, alliances={len(alliances)}")
                
                # Extract team numbers for each alliance
                red_teams = []
                blue_teams = []
                
                if len(alliances) > 0:
                    red_alliance = alliances[0]
                    red_teams = [str(t.get('number', '')) for t in red_alliance.get('teams', [])]
                
                if len(alliances) > 1:
                    blue_alliance = alliances[1]
                    blue_teams = [str(t.get('number', '')) for t in blue_alliance.get('teams', [])]
                
                # Convert timestamp to ISO format for frontend
                scheduled_time = match_info.get('timeScheduled', 0)
                start_time = None
                if scheduled_time:
                    try:
                        from datetime import datetime
                        start_time = datetime.fromtimestamp(scheduled_time).isoformat()
                    except Exception as e:
                        logger.error(f"Error converting timestamp {scheduled_time}: {e}")
                        start_time = None
                
                match_obj = {
                    'match': match_tuple.get('match', 0),
                    'round': match_tuple.get('round', 'QUAL'),
                    'division': division.get('id', 0),
                    'instance': match_tuple.get('instance', 1),
                    'startTime': start_time or match_info.get('timeScheduled', 0),
                    'field': 1,  # Default field - can be mapped if needed
                    'teams': {
                        'red': red_teams,
                        'blue': blue_teams
                    },
                    'state': match_info.get('state', 'UNPLAYED')
                }
                matches.append(match_obj)
        
        logger.info(f"Built {len(matches)} total matches for response")
        if matches:
            logger.debug(f"First match: {matches[0]}")
        
        return jsonify(matches)
    except Exception as e:
        logger.error(f"Error in api_scheduled_matches: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    
    return jsonify(matches)

@app.route('/api/match_stats/schedule')
@login_required(roles=["ANY"])
def api_match_stats_schedule():
    """
    Get full match schedule with team data for match stats page.
    """
    try:
        logger.info("api_match_stats_schedule called")
        
        config_data = _read_json(CONFIG_FILE, default={})
        logger.info(f"Config loaded. Keys: {list(config_data.keys())}")
        
        config = Config.from_dict(config_data)
        vex_tm_api = config.vex_tm_api or {}
        logger.info(f"VEX TM API config: {vex_tm_api}")
        
        # Check if vex_tm_api has credentials (not just enabled flag)
        has_credentials = vex_tm_api.get('client_id') and vex_tm_api.get('api_key')
        vex_tm_enabled = vex_tm_api.get('enabled', has_credentials)  # Default to True if credentials exist
        logger.info(f"VEX TM API has_credentials: {has_credentials}, enabled: {vex_tm_enabled}")
        
        if not vex_tm_enabled:
            logger.warning("VEX TM API not enabled, returning 503")
            return jsonify({"status": "error", "message": "VEX TM not enabled"}), 503
        
        # Read schedule from file
        schedule_file = os.path.join(STORAGE_PATH, 'schedule.json')
        logger.info(f"Reading schedule from: {schedule_file}")
        schedule_data = _read_json(schedule_file, {})
        logger.info(f"Schedule loaded. Divisions: {len(schedule_data.get('divisions', []))}")
        
        # Get field states to determine current match
        field_statuses = get_field_statuses()
        logger.info(f"Found {len(field_statuses)} field statuses")
        
        current_match = None
        for field_state in field_statuses:
            if hasattr(field_state, 'match_name') and field_state.match_name:
                match_name = field_state.match_name
                
                if field_state.state == 'active':
                    # Field is currently playing this match
                    logger.info(f"Field {field_state.field_id} active with match: {match_name}")
                    current_match = _find_match_tuple_by_name(schedule_data, match_name)
                    if current_match:
                        logger.info(f"Found current match tuple: {current_match}")
                        break
                elif field_state.state == 'finish':
                    # Field just finished a match, show the next match
                    logger.info(f"Field {field_state.field_id} finished with match: {match_name}, finding next match")
                    current_match = _find_next_match_tuple(schedule_data, match_name)
                    if current_match:
                        logger.info(f"Found next match tuple: {current_match}")
                        break
        
        logger.info(f"Returning schedule with current_match={current_match}")
        return jsonify({
            "status": "ok",
            "schedule": schedule_data,
            "current_match": current_match
        })
        
    except Exception as e:
        logger.error(f"Error fetching match schedule: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


def _find_match_tuple_by_name(schedule_data, match_name):
    """
    Find a matchTuple in the schedule by its display name (e.g., 'Q1', 'F2').
    Returns the full matchTuple dict or None if not found.
    """
    if not schedule_data or not schedule_data.get('divisions'):
        return None
    
    # Parse match_name: first character is round prefix, rest is match number
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
        logger.debug(f"Unknown round prefix: {round_prefix}")
        return None
    
    # Search all divisions for matching matchTuple
    for division in schedule_data.get('divisions', []):
        for match in division.get('matches', []):
            match_tuple = match.get('matchInfo', {}).get('matchTuple')
            if match_tuple and match_tuple.get('round') == round_value and match_tuple.get('match') == match_num:
                return match_tuple
    
    logger.debug(f"No matching tuple found for {match_name} (round={round_value}, match={match_num})")
    return None


def _find_next_match_tuple(schedule_data, current_match_name):
    """
    Find the next match in sequence after the current match.
    If at end of qualifications, looks for finals (TOP_N).
    """
    if not schedule_data or not schedule_data.get('divisions'):
        return None
    
    if len(current_match_name) < 2:
        return None
    
    round_prefix = current_match_name[0].upper()
    try:
        match_num = int(current_match_name[1:])
    except ValueError:
        return None
    
    # Map prefix to round value
    round_map = {
        'Q': 'QUAL',
        'F': 'TOP_N',
    }
    round_value = round_map.get(round_prefix)
    if not round_value:
        logger.debug(f"Unknown round prefix: {round_prefix}")
        return None
    
    # Try to find next match in same round
    next_match_num = match_num + 1
    for division in schedule_data.get('divisions', []):
        for match in division.get('matches', []):
            match_tuple = match.get('matchInfo', {}).get('matchTuple')
            if match_tuple and match_tuple.get('round') == round_value and match_tuple.get('match') == next_match_num:
                logger.info(f"Found next match in same round: {round_value} #{next_match_num}")
                return match_tuple
    
    # If in qualifications and no next qual match, look for first finals match
    if round_value == 'QUAL':
        logger.info("No next qual match found, looking for first finals (TOP_N) match")
        for division in schedule_data.get('divisions', []):
            for match in division.get('matches', []):
                match_tuple = match.get('matchInfo', {}).get('matchTuple')
                if match_tuple and match_tuple.get('round') == 'TOP_N' and match_tuple.get('match') == 1:
                    logger.info("Found first finals match")
                    return match_tuple
    
    logger.debug(f"No next match found after {current_match_name}")
    return None

@app.route('/api/match_stats/rankings/<int:division_id>')
@login_required(roles=["ANY"])
def api_match_stats_rankings(division_id):
    """
    Get rankings for a specific division.
    """
    try:
        config_data = _read_json(CONFIG_FILE, default={})
        config = Config.from_dict(config_data)
        vex_tm_api = config.vex_tm_api or {}
        
        # Check if vex_tm_api has credentials (not just enabled flag)
        has_credentials = vex_tm_api.get('client_id') and vex_tm_api.get('api_key')
        vex_tm_enabled = vex_tm_api.get('enabled', has_credentials)  # Default to True if credentials exist
        
        if not vex_tm_enabled:
            logger.warning(f"VEX TM API not enabled for rankings/{division_id}")
            return jsonify({"status": "error", "message": "VEX TM not enabled"}), 503
        
        api_client = VexTmApiClient(
            vex_tm_api.get('client_id'),
            vex_tm_api.get('client_secret'),
            vex_tm_api.get('api_key'),
            vex_tm_api.get('base_url', 'http://localhost:8080')
        )
        
        rankings_data = api_client.get(f"/api/rankings/{division_id}/QUAL")
        
        if not rankings_data:
            return jsonify({"status": "error", "message": "Failed to fetch rankings"}), 500
        
        return jsonify({
            "status": "ok",
            "rankings": rankings_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching rankings: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/match_stats/teams/<int:division_id>')
@login_required(roles=["ANY"])
def api_match_stats_teams(division_id):
    """
    Get team details for a specific division.
    """
    try:
        config_data = _read_json(CONFIG_FILE, default={})
        config = Config.from_dict(config_data)
        vex_tm_api = config.vex_tm_api or {}
        
        # Check if vex_tm_api has credentials (not just enabled flag)
        has_credentials = vex_tm_api.get('client_id') and vex_tm_api.get('api_key')
        vex_tm_enabled = vex_tm_api.get('enabled', has_credentials)  # Default to True if credentials exist
        
        if not vex_tm_enabled:
            logger.warning(f"VEX TM API not enabled for teams/{division_id}")
            return jsonify({"status": "error", "message": "VEX TM not enabled"}), 503
        
        api_client = VexTmApiClient(
            vex_tm_api.get('client_id'),
            vex_tm_api.get('client_secret'),
            vex_tm_api.get('api_key'),
            vex_tm_api.get('base_url', 'http://localhost:8080')
        )
        
        teams_data = api_client.get(f"/api/teams/{division_id}")
        
        if not teams_data:
            return jsonify({"status": "error", "message": "Failed to fetch teams"}), 500
        
        return jsonify({
            "status": "ok",
            "teams": teams_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching teams: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/popups')
def api_popups():
    return jsonify(_read_json(POPUPS_FILE, default=[]))

@app.route('/api/popups/dismiss', methods=['POST'])
def dismiss_popup():
    data = request.get_json()
    logger.debug(f"Received dismiss request: {data}")

    popup_id = data.get('popup_id')
    if not popup_id:
        logger.warning("Dismiss request failed: popup_id is missing")
        return jsonify({"error": "popup_id is required"}), 400

    logger.debug(f"Attempting to dismiss popup_id: {popup_id}")

    popups = _read_json(POPUPS_FILE, default=[])
    logger.debug(f"Popups before dismissal: {popups}")
    
    # Filter out the popup with the given ID
    new_popups = [p for p in popups if p.get('id') != popup_id]

    if len(new_popups) < len(popups):
        logger.debug(f"Found and removed popup_id: {popup_id}. Writing new popups: {new_popups}")
        _atomic_write(POPUPS_FILE, new_popups)
        return jsonify({"status": "ok"}), 200
    else:
        logger.warning(f"popup_id not found: {popup_id}")
        return jsonify({"error": "popup_id not found"}), 404


@app.route('/api/config')
@login_required()
def api_config():
    """
    API endpoint to get the current config.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    return jsonify(config_data)


@app.route('/api/presets', methods=['GET', 'POST'])
@login_required(roles=["admin", "av"])
def presets_api():
    """
    API for managing presets.
    """
    if request.method == 'POST':
        try:
            new_presets_data = request.get_json()
            _atomic_write(PRESETS_FILE, new_presets_data)
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error(f"Error saving presets: {e}")
            return "Error saving presets", 500

    presets_data = _read_json(PRESETS_FILE, default={"lighting": []})
    return jsonify(presets_data)


@app.route('/api/active_popups')
def api_active_popups():
    """
    API endpoint to get the list of active popups.
    """
    return jsonify(_read_json(POPUPS_FILE, default=[]))

@app.route('/api/remove_popup/<popup_id>', methods=['POST'])
def remove_popup(popup_id):
    """
    Removes a popup from the active list.
    """
    popups = _read_json(POPUPS_FILE, default=[])
    new_popups = [p for p in popups if p.get('id') != popup_id]
    
    if len(new_popups) < len(popups):
        _atomic_write(POPUPS_FILE, new_popups)
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"error": "popup_id not found"}), 404

@app.route('/api/send_popup', methods=['POST'])
@login_required(roles=["admin"])
def api_send_popup():
    if not event_queue or not loop:
        return jsonify({"error": "Event queue not available"}), 500
    
    data = request.json
    room_ids = data.get("room_ids", [])
    if not room_ids:
        return jsonify({"error": "room_ids is required"}), 400

    popup_payload = {
        "id": str(uuid.uuid4()),
        "room_ids": room_ids,
        "title": data.get("title", "Notification"),
        "message": data.get("message"),
        "duration": data.get("duration", 15),
        "type": data.get("type", "modal")
    }
    popup_event = Event(type="manual_popup", payload=popup_payload)
    asyncio.run_coroutine_threadsafe(event_queue.put(popup_event), loop)

    return jsonify({"status": "ok"})

@app.route('/api/trigger_action', methods=['POST'])
@login_required(roles=["admin", "av"])
def api_trigger_action():
    if not event_queue or not loop:
        return jsonify({"error": "Event queue not available"}), 500
        
    data = request.json
    action_type = data.get("type")

    # AV role restriction
    user_role = session.get('user', {}).get('role')
    if user_role == 'av':
        if not action_type or not any(action_type.startswith(cat) for cat in ['lighting', 'video', 'audio']):
            return jsonify({"error": "You are not authorized to trigger this type of action."}), 403

    action_event = Event(type="manual_action", payload=data)
    
    # Use run_coroutine_threadsafe to safely put an item into the asyncio queue
    # from this synchronous Flask thread.
    asyncio.run_coroutine_threadsafe(event_queue.put(action_event), loop)
    return jsonify({"status": "ok"})

@app.route('/api/system/reset', methods=['POST'])
@login_required(roles=["admin"])
def reset_system():
    """
    Resets the system by clearing schedule, notified matches, and popups.
    """
    schedule_file = os.path.join(STORAGE_PATH, 'schedule.json')
    notified_matches_file = os.path.join(STORAGE_PATH, 'notified_matches.json')
    popups_file = os.path.join(STORAGE_PATH, 'popups.json')

    try:
        # Delete schedule.json if it exists
        if os.path.exists(schedule_file):
            os.remove(schedule_file)
            logger.info("Deleted schedule.json")

        # Delete notified_matches.json if it exists
        if os.path.exists(notified_matches_file):
            os.remove(notified_matches_file)
            logger.info("Deleted notified_matches.json")

        # Clear popups.json by writing an empty list
        _atomic_write(popups_file, [])
        logger.info("Cleared popups.json")

        return jsonify({"status": "ok", "message": "System reset successfully."})

    except Exception as e:
        logger.error(f"Failed to reset system: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/simulator')
@login_required(roles=["admin"])
def event_simulator_page():
    """
    Serves the event simulator page.
    """
    return render_template('event_simulator.html')

@app.route('/api/simulate_event_from_web', methods=['POST'])
@login_required(roles=["admin"])
def api_simulate_event_from_web():
    """
    Endpoint to receive simulation requests from the web UI.
    This is kept separate from the main `simulate_event` to allow for different auth/validation.
    """
    if not event_queue or not loop:
        return jsonify({"error": "Event queue not available"}), 500
        
    data = request.json
    event_type = data.get('event_type')
    field = data.get('field')
    match_name = data.get('match')
    round_val = data.get('round')
    display = data.get('display')

    if not event_type:
        return jsonify({"error": "event_type is required"}), 400

    # This logic is adapted from tools/simulate_event.py
    # If we are starting a match, we should first assign it to the field
    if event_type == "matchStarted" and match_name and field:
        assign_payload = {
            "type": "fieldMatchAssigned",
            "field": int(field),
            "payload": {
                "match": {
                    "division": 1,
                    "session": 0,
                    "round": round_val or "QUAL",
                    "match": int(''.join(filter(str.isdigit, match_name))),
                    "instance": 1
                }
            }
        }
        assign_event = Event.from_dict(assign_payload)
        asyncio.run_coroutine_threadsafe(event_queue.put(assign_event), loop)

    # Construct the payload for the main event
    main_payload = {
        "type": event_type,
        "payload": {}
    }

    if field:
        main_payload["field"] = int(field)

    if (event_type == "fieldMatchAssigned" or event_type == "fieldAssigned") and match_name:
        main_payload["type"] = "fieldMatchAssigned"
        main_payload["payload"]["match"] = {
            "division": 1,
            "session": 0,
            "round": round_val or "QUAL",
            "match": int(''.join(filter(str.isdigit, match_name))),
            "instance": 1
        }
    elif event_type == "audienceDisplayChanged" and display:
        main_payload["payload"]["display"] = display
    elif match_name and event_type not in ["matchStarted", "fieldMatchAssigned", "audienceDisplayChanged"]:
        main_payload["payload"]["match"] = match_name

    main_event = Event.from_dict(main_payload)
    asyncio.run_coroutine_threadsafe(event_queue.put(main_event), loop)
    
    logger.info(f"Successfully queued simulated event from web: {main_event.to_json()}")
    return jsonify({"status": "ok", "event_sent": main_event.to_dict()})

@app.route('/profile', methods=['GET', 'POST'])
@login_required()
def profile():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('profile'))

        username = session['user']['userName']
        
        # Verify current password
        auth_result = userManager.Auth(username, current_password)
        if not auth_result['user']:
            flash('Incorrect current password.', 'danger')
            return redirect(url_for('profile'))

        # Change password
        try:
            userManager.changePassword(username, new_password)
            flash('Password updated successfully.', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')

    email = session['user'].get('email')
    return render_template('profile.html', email=email)

@app.route('/profile/email', methods=['POST'])
@login_required()
def profile_email():
    new_email = request.form['new_email']
    username = session['user']['userName']
    try:
        userManager.changeEmail(username, new_email)
        # Update email in session
        user_data = session['user']
        user_data['email'] = new_email
        session['user'] = user_data
        flash('Email updated successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {e}', 'danger')
    return redirect(url_for('profile'))

@app.route('/logs')
@login_required(roles=["admin", "owner"])
def logs_page():
    """
    Serves the live logs page.
    """
    return render_template('logs.html')

@app.route('/stream-logs')
@login_required(roles=["admin", "owner"])
def stream_logs():
    def generate():
        while True:
            try:
                log_record = log_queue.get(timeout=10)
                yield f"data: {log_record}\n\n"
            except queue.Empty:
                # Send a comment to keep the connection alive
                yield ": keep-alive\n\n"
            time.sleep(0.1) # Prevent tight loop
    return Response(generate(), mimetype='text/event-stream')

# ============================================================================
# Timer Management Routes
# ============================================================================

@app.route('/timer_admin')
@login_required(roles=["admin"])
def timer_admin():
    """Timer administration page for creating and managing timers"""
    return render_template('timer_admin.html')

@app.route('/timer_admin/<timer_id>/expand')
@login_required(roles=["admin"])
def timer_admin_expanded(timer_id):
    """Expanded fullscreen timer control interface"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return render_template('error.html', error_code=404, error_message="Timer not found"), 404
    return render_template('timer_admin_expanded.html', timer_id=timer_id, timer_name=timers[timer_id]['name'])

@app.route('/match_control')
@login_required(roles=["admin", "av"])
def match_control():
    """Match control page for sending VEX TM commands"""
    return render_template('match_control.html')

@app.route('/match_stats')
@login_required(roles=["emcee", "av", "admin", "owner"])
def match_stats():
    """Match statistics page showing match schedule and team info"""
    return render_template('match_stats.html')

@app.route('/timers')
@login_required(roles=["emcee", "av", "admin", "owner"])
def timers_overview():
    """Timers overview page showing all created timers"""
    return render_template('timers_overview.html')

@app.route('/timer/<timer_id>')
def timer_view(timer_id):
    """Public timer viewer page - no authentication required"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return render_template('error.html', error_code=404, error_message="Timer not found"), 404
    return render_template('timer.html', timer_id=timer_id)

@app.route('/api/timers', methods=['GET'])
@login_required(roles=["admin"])
def api_timers_list():
    """Get all saved timers"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    return jsonify(timers)

@app.route('/api/timers/status', methods=['GET'])
@login_required(roles=["admin"])
def api_timers_status():
    """Get status of all timers"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    timer_states = _read_json(TIMER_STATE_FILE, {})
    current_time = time.time()
    
    results = {}
    for timer_id, timer_data in timers.items():
        state = timer_states.get(timer_id, {})
        is_running = state.get('is_running', False)
        end_timestamp = state.get('end_timestamp', current_time)
        
        if is_running:
            remaining = max(0, end_timestamp - current_time)
            elapsed = state.get('duration', 0) - remaining
        else:
            # Timer has finished or stopped
            if end_timestamp <= current_time and state.get('start_timestamp'):
                # Show elapsed time since finish
                elapsed = current_time - end_timestamp
                remaining = -elapsed  # Negative to indicate overtime
            else:
                # Timer was stopped before completion or never started
                start_ts = state.get('start_timestamp')
                if start_ts:
                     elapsed = current_time - start_ts
                else:
                    elapsed = 0
                remaining = timer_data['duration'] # Reset to duration if stopped/reset
        
        results[timer_id] = {
            "is_running": is_running,
            "remaining": remaining,
            "elapsed": elapsed,
            "duration": timer_data['duration']
        }
    return jsonify(results)

@app.route('/api/timers', methods=['POST'])
@login_required(roles=["admin"])
def api_timers_create():
    """Create a new timer"""
    try:
        data = request.json
        timer_id = data.get('timer_id')
        if not timer_id:
            timer_id = str(uuid.uuid4())
        
        name = data.get('name')
        if not name:
             name = "Untitled Timer"

        # Parse milestones
        milestones = []
        for m_data in data.get('milestones', []):
            milestone = TimerMilestone(
                time_remaining=m_data['time_remaining'],
                action_type=m_data['action_type'],
                action_payload=m_data['action_payload'],
                message=m_data.get('message')
            )
            milestones.append(milestone)
        
        # Create timer object
        timer = Timer(
            timer_id=timer_id,
            name=name,
            duration=data['duration'],
            milestones=milestones,
            field_id=data.get('field_id'),
            ready_states=data.get('ready_states', {}),
            auto_start_tm=data.get('auto_start_tm', False),
            match_number=data.get('match_number')
        )
        
        # Save to storage
        timers = _read_json(TIMERS_SAVED_FILE, {})
        timers[timer_id] = timer.to_dict()
        _atomic_write(TIMERS_SAVED_FILE, timers)
        
        return jsonify({"status": "ok", "timer_id": timer_id, "timer": timer.to_dict()})
    except Exception as e:
        logger.error(f"Error creating timer: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/timer/<timer_id>', methods=['GET'])
@login_required(roles=["admin"])
def api_timer_get(timer_id):
    """Get a specific timer configuration"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    return jsonify(timers[timer_id])

@app.route('/api/timer/<timer_id>', methods=['PUT'])
@login_required(roles=["admin"])
def api_timer_update(timer_id):
    """Update a timer configuration"""
    try:
        data = request.json
        
        name = data.get('name')
        if not name:
             name = "Untitled Timer"

        # Parse milestones
        milestones = []
        for m_data in data.get('milestones', []):
            milestone = TimerMilestone(
                time_remaining=m_data['time_remaining'],
                action_type=m_data['action_type'],
                action_payload=m_data['action_payload'],
                message=m_data.get('message')
            )
            milestones.append(milestone)
        
        # Create timer object
        timer = Timer(
            timer_id=timer_id,
            name=name,
            duration=data['duration'],
            milestones=milestones,
            field_id=data.get('field_id'),
            created_at=data.get('created_at'),
            ready_states=data.get('ready_states', {}),
            auto_start_tm=data.get('auto_start_tm', False),
            match_number=data.get('match_number')
        )
        
        # Save to storage
        timers = _read_json(TIMERS_SAVED_FILE, {})
        timers[timer_id] = timer.to_dict()
        _atomic_write(TIMERS_SAVED_FILE, timers)
        
        return jsonify({"status": "ok", "timer": timer.to_dict()})
    except Exception as e:
        logger.error(f"Error updating timer: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/timer/<timer_id>', methods=['DELETE'])
@login_required(roles=["admin"])
def api_timer_delete(timer_id):
    """Delete a timer"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    del timers[timer_id]
    _atomic_write(TIMERS_SAVED_FILE, timers)
    
    # Also remove from active state
    timer_states = _read_json(TIMER_STATE_FILE, {})
    if timer_id in timer_states:
        del timer_states[timer_id]
        _atomic_write(TIMER_STATE_FILE, timer_states)
    
    return jsonify({"status": "ok"})

@app.route('/api/timer/<timer_id>/start', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_start(timer_id):
    """Start a timer"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    timer_data = timers[timer_id]
    duration = timer_data['duration']
    
    current_time = time.time()
    end_time = current_time + duration
    
    # Enqueue timer_started event
    event = Event(
        type="timer_started",
        field=None,
        payload={
            "timer_id": timer_id,
            "start_timestamp": current_time,
            "end_timestamp": end_time,
            "duration": duration
        }
    )
    asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
    
    return jsonify({
        "status": "ok",
        "start_timestamp": current_time,
        "end_timestamp": end_time
    })

@app.route('/api/timer/<timer_id>/stop', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_stop(timer_id):
    """Stop a timer"""
    if not event_queue or not loop:
        logging.getLogger(__name__).error("Event queue or loop not initialized")
        return jsonify({"status": "error", "message": "Service not ready"}), 500
    
    # Verify timer exists
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    # Verify timer is in states (it should be if it's running)
    timer_states = _read_json(TIMER_STATE_FILE, {})
    if timer_id not in timer_states:
        logging.getLogger(__name__).warning(f"Timer {timer_id} not in states, but attempting to stop anyway")
    
    # Enqueue timer_stopped event
    event = Event(
        type="timer_stopped",
        field=None,
        payload={"timer_id": timer_id}
    )
    logging.getLogger(__name__).info(f"Stopping timer {timer_id}")
    asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
    
    return jsonify({"status": "ok"})

@app.route('/api/timer/<timer_id>/reset', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_reset(timer_id):
    """Reset a timer (stop it and clear state)"""
    timer_states = _read_json(TIMER_STATE_FILE, {})
    if timer_id in timer_states:
        del timer_states[timer_id]
        _atomic_write(TIMER_STATE_FILE, timer_states)
    
    return jsonify({"status": "ok"})

@app.route('/api/timer/<timer_id>/state', methods=['GET'])
def api_timer_state(timer_id):
    """Get current timer state - public endpoint for viewer"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    timer_data = timers[timer_id]
    timer_states = _read_json(TIMER_STATE_FILE, {})
    
    current_time = time.time()
    
    if timer_id in timer_states:
        state = timer_states[timer_id]
        is_running = state.get('is_running', False)
        end_timestamp = state.get('end_timestamp', current_time)
        
        if is_running:
            remaining = max(0, end_timestamp - current_time)
            elapsed = state.get('duration', 0) - remaining
        else:
            # Timer has finished or stopped
            if end_timestamp <= current_time:
                # Show elapsed time since finish
                elapsed = current_time - end_timestamp
                remaining = -elapsed  # Negative to indicate overtime
            else:
                # Timer was stopped before completion
                elapsed = current_time - state.get('start_timestamp', current_time)
                remaining = 0
        
        # Get current message if any
        current_message = None
        if is_running and remaining >= 0:
            for milestone in timer_data.get('milestones', []):
                if milestone.get('message') and remaining <= milestone['time_remaining']:
                    current_message = milestone['message']
                    break
        
        # Get display message if any
        display_message = timer_states[timer_id].get('current_display_message', '')
        
        return jsonify({
            "status": "ok",
            "timer_id": timer_id,
            "timer_name": timer_data['name'],
            "is_running": is_running,
            "remaining": remaining,
            "elapsed": elapsed,
            "end_timestamp": end_timestamp,
            "server_time": current_time,
            "current_message": current_message,
            "display_message": display_message,
            "field_id": timer_data.get('field_id')
        })
    else:
        # Timer not started yet
        display_message = ''
        if timer_id in timer_states:
            display_message = timer_states[timer_id].get('current_display_message', '')
        
        return jsonify({
            "status": "ok",
            "timer_id": timer_id,
            "timer_name": timer_data['name'],
            "is_running": False,
            "remaining": timer_data['duration'],
            "elapsed": 0,
            "end_timestamp": None,
            "server_time": current_time,
            "current_message": None,
            "display_message": display_message,
            "field_id": timer_data.get('field_id')
        })

@app.route('/api/timer/<timer_id>/ready', methods=['POST'])
def api_timer_ready(timer_id):
    """Mark a user as ready for this timer"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    data = request.json or {}
    user_id = data.get('user_id', 'anonymous')
    
    timer = Timer.from_dict(timers[timer_id])
    timer.ready_states[user_id] = True
    
    timers[timer_id] = timer.to_dict()
    _atomic_write(TIMERS_SAVED_FILE, timers)
    
    return jsonify({"status": "ok", "ready_states": timer.ready_states})

@app.route('/api/timer/<timer_id>/ready/clear', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_ready_clear(timer_id):
    """Clear all ready states for this timer"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    timer = Timer.from_dict(timers[timer_id])
    timer.ready_states = {}
    
    timers[timer_id] = timer.to_dict()
    _atomic_write(TIMERS_SAVED_FILE, timers)
    
    return jsonify({"status": "ok"})

@app.route('/api/timer/<timer_id>/team_info', methods=['GET'])
def api_timer_team_info(timer_id):
    """Get team information for timer's assigned field"""
    timers = _read_json(TIMERS_SAVED_FILE, {})
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    timer_data = timers[timer_id]
    field_id = timer_data.get('field_id')
    
    if not field_id:
        return jsonify({"status": "ok", "teams": [], "match": None, "message": "No field assigned"})
    
    # Try to get the TM API client from config
    config_data = _read_json(CONFIG_FILE, {})
    config = Config.from_dict(config_data)
    
    if not all([config.vex_tm_client_id, config.vex_tm_client_secret, config.vex_tm_api_key, config.vex_tm_base_url]):
        return jsonify({"status": "ok", "teams": [], "match": None, "message": "TM API not configured"})
    
    try:
        from modules.tm_manager.api_client import VexTmApiClient
        api_client = VexTmApiClient(
            config.vex_tm_client_id,
            config.vex_tm_client_secret,
            config.vex_tm_api_key,
            config.vex_tm_base_url
        )
        
        # Check if there's a field state with match assignment
        field_file = os.path.join(FIELDS_DIR, f"field{field_id}.json")
        match_info = None
        
        if os.path.exists(field_file):
            field_state_data = _read_json(field_file, {})
            match_id = field_state_data.get('match_id')
            
            if match_id:
                # Get full match schedule
                schedule_file = os.path.join(STORAGE_PATH, 'schedule.json')
                if os.path.exists(schedule_file):
                    schedule_data = _read_json(schedule_file, {})
                    
                    # Find the match in the schedule
                    for division in schedule_data.get('divisions', []):
                        if division['id'] == match_id.get('division'):
                            for match in division.get('matches', []):
                                match_tuple = match.get('matchInfo', {}).get('matchTuple', {})
                                if (match_tuple.get('match') == match_id.get('match') and
                                    match_tuple.get('round') == match_id.get('round', 'QUAL')):
                                    match_info = match
                                    break
                            break
        
        # Get team data for the match
        teams_data = []
        if match_info:
            alliances = match_info.get('matchInfo', {}).get('alliances', [])
            division_id = match_info.get('matchInfo', {}).get('matchTuple', {}).get('division', 1)
            
            # Fetch teams list
            teams_list_data = api_client.get(f"/api/teams/{division_id}")
            teams_dict = {}
            if teams_list_data and 'teams' in teams_list_data:
                for team in teams_list_data['teams']:
                    teams_dict[team['number']] = team
            
            # Fetch rankings
            rankings_data = api_client.get(f"/api/rankings/{division_id}/QUAL")
            rankings_dict = {}
            if rankings_data and 'rankings' in rankings_data:
                for ranking in rankings_data['rankings']:
                    team_nums = [t['number'] for t in ranking.get('alliance', {}).get('teams', [])]
                    for team_num in team_nums:
                        rankings_dict[team_num] = ranking
            
            # Build combined team data
            for alliance_idx, alliance in enumerate(alliances):
                for team_info in alliance.get('teams', []):
                    team_num = team_info['number']
                    team_details = teams_dict.get(team_num, {})
                    ranking = rankings_dict.get(team_num, {})
                    
                    teams_data.append({
                        'number': team_num,
                        'name': team_details.get('name', ''),
                        'school': team_details.get('school', ''),
                        'city': team_details.get('city', ''),
                        'state': team_details.get('state', ''),
                        'country': team_details.get('country', ''),
                        'rank': ranking.get('rank'),
                        'avgPoints': ranking.get('avgPoints'),
                        'wins': ranking.get('wins'),
                        'losses': ranking.get('losses'),
                        'ties': ranking.get('ties'),
                        'alliance': 'Red' if alliance_idx == 0 else 'Blue'
                    })
        
        return jsonify({
            "status": "ok",
            "teams": teams_data,
            "match": match_info,
            "field_id": field_id
        })
        
    except Exception as e:
        logger.error(f"Error fetching team info: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/tm/send_command', methods=['POST'])
@login_required(roles=["admin"])
def api_tm_send_command():
    """Send a command to TM via websocket"""
    data = request.json
    field_id = data.get('field_id')
    command = data.get('command')
    
    if not field_id or not command:
        return jsonify({"status": "error", "message": "field_id and command required"}), 400
    
    # Queue an event to send the command
    event = Event(
        type="tm_command",
        field=field_id,
        payload={"command": command, "params": data.get('params', {})}
    )
    
    if event_queue and loop:
        asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "error", "message": "Event queue not available"}), 500

@app.route('/api/timer/<timer_id>/message', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_send_message(timer_id):
    """Send a message to be displayed on timer view"""
    data = request.json
    message = data.get('message', '')
    
    # Store message in timer state for viewers to fetch
    timer_states = _read_json(TIMER_STATE_FILE, {})
    if timer_id not in timer_states:
        timer_states[timer_id] = {}
    
    timer_states[timer_id]['current_display_message'] = message
    _atomic_write(TIMER_STATE_FILE, timer_states)
    
    return jsonify({"status": "ok"})

@app.route('/api/timer/<timer_id>/presets', methods=['GET'])
@login_required(roles=["admin"])
def api_timer_get_presets(timer_id):
    """Get saved message presets (global)"""
    presets_file = os.path.join(STORAGE_PATH, 'message_presets.json')
    presets = _read_json(presets_file, [])
    return jsonify({"status": "ok", "presets": presets})

@app.route('/api/timer/<timer_id>/presets', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_save_preset(timer_id):
    """Save a message preset (global)"""
    data = request.json
    name = data.get('name', '').strip()
    message = data.get('message', '').strip()
    
    if not name or not message:
        return jsonify({"status": "error", "message": "Name and message required"}), 400
    
    presets_file = os.path.join(STORAGE_PATH, 'message_presets.json')
    presets = _read_json(presets_file, [])
    
    # Add new preset
    presets.append({"name": name, "message": message})
    _atomic_write(presets_file, presets)
    
    return jsonify({"status": "ok", "presets": presets})

@app.route('/api/timer/<timer_id>/presets/<int:preset_index>', methods=['DELETE'])
@login_required(roles=["admin"])
def api_timer_delete_preset(timer_id, preset_index):
    """Delete a message preset (global)"""
    presets_file = os.path.join(STORAGE_PATH, 'message_presets.json')
    presets = _read_json(presets_file, [])
    
    if 0 <= preset_index < len(presets):
        presets.pop(preset_index)
        _atomic_write(presets_file, presets)
        return jsonify({"status": "ok", "presets": presets})
    
    return jsonify({"status": "error", "message": "Invalid preset index"}), 400

# F1: Timer Templates
@app.route('/api/timer_templates', methods=['GET'])
@login_required(roles=["admin", "av"])
def api_timer_templates():
    """Get all timer templates"""
    templates_file = os.path.join(STORAGE_PATH, 'timer_templates.json')
    templates = _read_json(templates_file, [])
    return jsonify({"status": "ok", "templates": templates})

@app.route('/api/timer_templates', methods=['POST'])
@login_required(roles=["admin"])
def api_timer_templates_create():
    """Create a new timer template from existing timer"""
    data = request.json
    timer_id = data.get('timer_id')
    template_name = data.get('name')
    
    if not timer_id or not template_name:
        return jsonify({"status": "error", "message": "Missing timer_id or name"}), 400
    
    # Load the timer
    timer_file = os.path.join(STORAGE_PATH, f'timers_saved.json')
    timers = _read_json(timer_file, {})
    
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    # Create template
    timer_dict = timers[timer_id]
    template = {
        'id': str(uuid.uuid4()),
        'name': template_name,
        'description': data.get('description', ''),
        'duration': timer_dict.get('duration'),
        'milestones': timer_dict.get('milestones', []),
        'created_at': int(time.time())
    }
    
    # Save template
    templates_file = os.path.join(STORAGE_PATH, 'timer_templates.json')
    templates = _read_json(templates_file, [])
    templates.append(template)
    _atomic_write(templates_file, templates)
    
    return jsonify({"status": "ok", "template": template})

@app.route('/api/timer_templates/<template_id>', methods=['DELETE'])
@login_required(roles=["admin"])
def api_timer_templates_delete(template_id):
    """Delete a timer template"""
    templates_file = os.path.join(STORAGE_PATH, 'timer_templates.json')
    templates = _read_json(templates_file, [])
    
    templates = [t for t in templates if t.get('id') != template_id]
    _atomic_write(templates_file, templates)
    
    return jsonify({"status": "ok"})

@app.route('/api/timer_templates/<template_id>/apply/<timer_id>', methods=['POST'])
@login_required(roles=["admin", "av"])
def api_timer_templates_apply(template_id, timer_id):
    """Apply a template to a timer"""
    templates_file = os.path.join(STORAGE_PATH, 'timer_templates.json')
    templates = _read_json(templates_file, [])
    
    template = next((t for t in templates if t.get('id') == template_id), None)
    if not template:
        return jsonify({"status": "error", "message": "Template not found"}), 404
    
    # Load timer
    timer_file = os.path.join(STORAGE_PATH, 'timers_saved.json')
    timers = _read_json(timer_file, {})
    
    if timer_id not in timers:
        return jsonify({"status": "error", "message": "Timer not found"}), 404
    
    # Apply template
    timers[timer_id]['duration'] = template.get('duration')
    timers[timer_id]['milestones'] = template.get('milestones', [])
    
    _atomic_write(timer_file, timers)
    
    return jsonify({"status": "ok", "timer": timers[timer_id]})

# F2: Match History
@app.route('/api/match_history', methods=['GET'])
def api_match_history():
    """Get match history"""
    history_file = os.path.join(STORAGE_PATH, 'match_history.json')
    history = _read_json(history_file, [])
    
    # Return last 100 matches
    recent = history[-100:] if len(history) > 100 else history
    recent.reverse()  # Most recent first
    
    return jsonify({"status": "ok", "matches": recent})

@app.route('/api/match_history', methods=['POST'])
@login_required(roles=["admin", "av"])
def api_match_history_add():
    """Add a match to history"""
    data = request.json
    
    match_entry = {
        'id': str(uuid.uuid4()),
        'timestamp': int(time.time()),
        'match_name': data.get('match_name'),
        'field_id': data.get('field_id'),
        'red_alliance': data.get('red_alliance', []),
        'blue_alliance': data.get('blue_alliance', []),
        'red_score': data.get('red_score'),
        'blue_score': data.get('blue_score'),
        'winner': data.get('winner')
    }
    
    history_file = os.path.join(STORAGE_PATH, 'match_history.json')
    history = _read_json(history_file, [])
    history.append(match_entry)
    
    # Keep last 1000 matches
    if len(history) > 1000:
        history = history[-1000:]
    
    _atomic_write(history_file, history)
    
    return jsonify({"status": "ok", "match": match_entry})

@app.route('/api/spotify/playback', methods=['GET'])
def api_spotify_playback():
    """Get current Spotify playback state"""
    from main import spotify_controller
    
    if not spotify_controller:
        return jsonify({"status": "error", "message": "Spotify not configured"}), 200
    
    playback = spotify_controller.get_current_playback()
    if playback:
        return jsonify({"status": "ok", "playback": playback})
    else:
        return jsonify({"status": "ok", "playback": None, "message": "Nothing playing"})

@app.route('/api/spotify/control', methods=['POST'])
@login_required(roles=["admin", "av"])
def api_spotify_control():
    """Control Spotify playback"""
    from main import spotify_controller, event_queue, loop
    from models.actions import AudioAction
    
    if not spotify_controller:
        return jsonify({"status": "error", "message": "Spotify not configured"}), 503
    
    data = request.json
    command = data.get('command')
    
    if not command:
        return jsonify({"status": "error", "message": "command required"}), 400
    
    # Create and execute action
    try:
        metadata = data.get('metadata', {})
        action = AudioAction(command=command, metadata=metadata)
        spotify_controller.execute_action(action)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Error executing Spotify control: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error_code=404, error_message="The page you're looking for can't be found."), 404

@app.errorhandler(Exception)
def internal_error(error):
    # Log the error for debugging
    logger.error(f"An unhandled exception occurred: {error}", exc_info=True)

    # --- Send ntfy notification ---
    # ntfy notifications for errors are disabled. Previously a post to the
    # configured ntfy endpoint happened here; that behavior was removed to
    # stop sending error notifications.
    
    # For 5xx errors, we can be more generic
    error_code = getattr(error, 'code', 500)
    if not (isinstance(error_code, int) and 500 <= error_code < 600):
        error_code = 500

    return render_template('error.html', error_code=error_code, error_message="An unexpected error occurred. The team has been notified."), error_code


if __name__ == "__main__":
    # The app should be run with a production-ready WSGI server like Gunicorn
    # For development, we can use app.run, but let's make it listen on all interfaces
    # to be accessible from outside the container.
    app.run(host='0.0.0.0', port=5000, debug=True)
