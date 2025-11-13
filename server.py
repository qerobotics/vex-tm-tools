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
from userManager import UserManager

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

logging.getLogger().setLevel(logging.INFO) # Ensure root logger captures all levels

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_insecure_default_secret_key")

userManager = UserManager()

STORAGE_PATH = 'storage'
FIELDS_DIR = os.path.join(STORAGE_PATH, 'fields')
CONFIG_FILE = os.path.join(STORAGE_PATH, 'config.json')
SCHEDULED_MATCHES_FILE = os.path.join(STORAGE_PATH, 'scheduled_matches.json')
POPUPS_FILE = os.path.join(STORAGE_PATH, 'popups.json')
PRESETS_FILE = os.path.join(STORAGE_PATH, 'presets.json')

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
    return jsonify(_read_json(SCHEDULED_MATCHES_FILE, default={}))

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
