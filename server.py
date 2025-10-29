import asyncio
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, g
import os
import json
import logging
import tempfile
from functools import wraps
import uuid

from models.fields import FieldState
from models.config import Config
from models.events import Event
from userManager import UserManager

# This is a placeholder for where the event queue would be shared
# In a real app, this would be managed more robustly (e.g., via a global context or passed in)
event_queue = None
loop = None

def set_event_queue(queue, main_loop):
    global event_queue, loop
    event_queue = queue
    loop = main_loop

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_insecure_default_secret_key")

userManager = UserManager()

STORAGE_PATH = 'storage'
FIELDS_DIR = os.path.join(STORAGE_PATH, 'fields')
CONFIG_FILE = os.path.join(STORAGE_PATH, 'config.json')
SCHEDULED_MATCHES_FILE = os.path.join(STORAGE_PATH, 'scheduled_matches.json')
POPUPS_FILE = os.path.join(STORAGE_PATH, 'popups.json')

def _atomic_write(file_path, data):
    try:
        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
        with os.fdopen(temp_fd, 'w') as temp_f:
            json.dump(data, temp_f, indent=4)
        os.rename(temp_path, file_path)
        logger.info(f"Successfully wrote to {file_path}")
    except Exception as e:
        logger.error(f"Failed to atomically write to {file_path}: {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

def login_required(role="ANY"):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if 'user' not in session:
                flash("You must be logged in to view this page.", "danger")
                return redirect(url_for('login', next=request.url))
            
            user_role = session.get('user', {}).get('role')
            if role != "ANY" and user_role != role:
                flash("You do not have permission to view this page.", "danger")
                return redirect(url_for('index'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def _read_json(file_path, default=None):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

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
        auth_result = userManager.Auth(username, password)
        
        if auth_result['user']:
            session['user'] = auth_result['user'].__dict__
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash(auth_result['message'], 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/config', methods=['GET', 'POST'])
@login_required(role="admin")
def config_page():
    """
    Page for viewing and editing config.json.
    """
    if request.method == 'POST':
        try:
            new_config_str = request.form['config']
            new_config_data = json.loads(new_config_str)
            _atomic_write(CONFIG_FILE, new_config_data)
            return redirect(url_for('config_page'))
        except json.JSONDecodeError:
            return "Invalid JSON provided", 400
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return "Error saving configuration", 500

    config_data = _read_json(CONFIG_FILE, default={})
    return render_template('config.html', config=json.dumps(config_data, indent=4))

@app.route('/pause', methods=['GET', 'POST'])
@login_required(role="admin")
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

@app.route('/admin/rooms', methods=['GET'])
@login_required(role="admin")
def room_management():
    """
    Admin page for managing rooms.
    """
    config_data = _read_json(CONFIG_FILE, default={})
    rooms = config_data.get("rooms", {})
    return render_template('room_management.html', rooms=rooms)

@app.route('/admin/rooms/add', methods=['POST'])
@login_required(role="admin")
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
@login_required(role="admin")
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
@login_required(role="admin")
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
@login_required()
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
    new_popups = [p for p in popups if p.get('popup_id') != popup_id]

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

@app.route('/api/active_popups')
def api_active_popups():
    """
    API endpoint to get the list of active popups.
    """
    return jsonify(_read_json(POPUPS_FILE, default=[]))

@app.route('/api/remove_popup/<popup_id>', methods=['POST'])
@login_required()
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
@login_required()
def api_send_popup():
    if not event_queue or not loop:
        return jsonify({"error": "Event queue not available"}), 500
    
    data = request.json
    room_ids = data.get("room_ids", [])
    if not room_ids:
        return jsonify({"error": "room_ids must be a non-empty list"}), 400

    # Generate one event per room to keep logic simple downstream
    for room_id in room_ids:
        popup_payload = {
            "id": str(uuid.uuid4()),
            "room_id": room_id,
            "message": data.get("message"),
            "duration": data.get("duration", 15)
        }
        popup_event = Event(type="manual_popup", payload=popup_payload)
        asyncio.run_coroutine_threadsafe(event_queue.put(popup_event), loop)

    return jsonify({"status": "ok"})

@app.route('/api/trigger_action', methods=['POST'])
@login_required()
def api_trigger_action():
    if not event_queue or not loop:
        return jsonify({"error": "Event queue not available"}), 500
        
    data = request.json
    action_event = Event(type="manual_action", payload=data)
    
    # Use run_coroutine_threadsafe to safely put an item into the asyncio queue
    # from this synchronous Flask thread.
    asyncio.run_coroutine_threadsafe(event_queue.put(action_event), loop)
    return jsonify({"status": "ok"})

@app.route('/api/simulate_event', methods=['POST'])
def api_simulate_event():
    if not event_queue or not loop:
        return jsonify({"error": "Event queue not available"}), 500
        
    data = request.json
    # Basic validation
    if 'type' not in data or 'field' not in data:
        return jsonify({"error": "Request must include 'type' and 'field'"}), 400

    event = Event(
        type=data['type'],
        field=data['field'],
        payload=data.get('payload', {})
    )
    
    asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
    logger.info(f"Successfully queued simulated event: {event.to_json()}")
    return jsonify({"status": "ok", "event": event.to_dict()})

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
            userManager.ChangePassword(username, new_password)
            flash('Password updated successfully.', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')

    return render_template('profile.html')


if __name__ == "__main__":
    # The app should be run with a production-ready WSGI server like Gunicorn
    # For development, we can use app.run, but let's make it listen on all interfaces
    # to be accessible from outside the container.
    app.run(host='0.0.0.0', port=5000, debug=True)