# How to Run VEX TM Manager Tools

This guide provides step-by-step instructions for setting up and running the VEX TM Manager Tools application.

## Prerequisites

- Python 3.8+ and `pip` installed on your system.
- Access to the VEX Tournament Manager API.
- API credentials for any connected services (Spotify, etc.).

## 1. Installation

First, clone the repository and install the required Python dependencies.

```bash
# Clone the repository (if you haven't already)
git clone https://github.com/vmd1/vex-tm-manager-spotify-sync.git
cd vex-tm-manager-spotify-sync

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 2. Configuration

The application's behavior is controlled by a central configuration file located at `storage/config.json`. You must configure it before the first run.

A sample `config.json` might look like this:

```json
{
    "device_ips": {
        "atem": "192.168.1.100",
        "zeros": {
            "ip": "192.168.1.101",
            "port": 8000
        },
        "spotify": {
            "client_id": "YOUR_SPOTIFY_CLIENT_ID",
            "client_secret": "YOUR_SPOTIFY_CLIENT_SECRET",
            "redirect_uri": "http://localhost:5000/callback"
        }
    },
    "spotify_device_id": "YOUR_SPOTIFY_DEVICE_NAME_OR_ID",
    "schedule_lead_matches": 3,
    "rooms": {
        "101": {
            "youtube_stream_url": "https://www.youtube.com/watch?v=your_stream_1",
            "teams": ["123A", "456B"]
        },
        "102": {
            "youtube_stream_url": "https://www.youtube.com/watch?v=your_stream_2",
            "teams": ["789C"]
        }
    },
    "paused": {
        "audio": false,
        "video": false,
        "lighting": false
    }
}
```

### Configuration Steps:

1.  **Create `storage/config.json`**: If it doesn't exist, create this file inside the `storage/` directory.
2.  **Device IPs**:
    *   Update `atem`, `zeros`, and `spotify` with the correct IP addresses and credentials for your hardware and services.
    *   For Spotify, you will need to create an application in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) to get a Client ID and Client Secret. Ensure the `redirect_uri` is authorized in your Spotify app settings.
3.  **Rooms**:
    *   Use the **Room Management** page in the web UI (at `/admin/rooms`) to add, edit, and delete rooms.
    *   Assign a YouTube stream URL and a list of teams to each room. This is used for displaying match notifications on the public room pages.
4.  **Pause Controls**:
    *   The `paused` section allows you to disable categories of automated actions. You can control this from the **Pause Controls** page in the web UI.

## 3. Running the Application

Once the configuration is complete, you can start the application by running the `main.py` script. This will launch the Flask web server and all the background worker processes.

```bash
python3 main.py
```

The application will start, and you will see log output in your terminal indicating that the different services (Event Processor, Schedulers, etc.) are running.

## 4. Accessing the Web UI

The web interface is the primary way to monitor and control the system.

-   **Main Dashboard**: [http://localhost:5000/](http://localhost:5000/)
-   **Room Management**: [http://localhost:5000/admin/rooms](http://localhost:5000/admin/rooms)
-   **Pause Controls**: [http://localhost:5000/pause](http://localhost:5000/pause)

From the UI, you can view field statuses, manage rooms, and pause automated actions.

## 5. Running in a Production Environment

The default Flask development server is not suitable for production use. For a production deployment, it is recommended to use a production-ready WSGI server like **Gunicorn** or **uWSGI**.

Example of running the app with Gunicorn:

```bash
# Make sure Gunicorn is installed
pip install gunicorn

# Run the server
gunicorn --workers 4 --bind 0.0.0.0:5000 "server:app"
```

You would still need to run the `main.py` script to start the backend services, but you would modify `main.py` to *not* run the Flask development server in this case. An advanced setup might involve running the backend services and the web server as separate systemd services.
