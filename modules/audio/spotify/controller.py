import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import logging

logger = logging.getLogger(__name__)

class SpotifyController:
    def __init__(self, client_id, client_secret, redirect_uri, device_name=None):
        self.device_id = None
        self.device_name = device_name
        
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope="user-modify-playback-state user-read-playback-state"
            ))
            self._set_device_id()
        except Exception as e:
            logger.error(f"Failed to initialize Spotify client: {e}")
            self.sp = None

    def _set_device_id(self):
        if not self.sp:
            return
        try:
            devices = self.sp.devices()
            if devices and devices['devices']:
                if self.device_name:
                    for device in devices['devices']:
                        if device['name'].lower() == self.device_name.lower():
                            self.device_id = device['id']
                            logger.info(f"Found Spotify device '{self.device_name}' with ID: {self.device_id}")
                            break
                    if not self.device_id:
                        logger.warning(f"Could not find a device named '{self.device_name}'. Using the first available device.")
                        self.device_id = devices['devices'][0]['id']
                else:
                    self.device_id = devices['devices'][0]['id']
                    logger.info(f"No device name specified. Using first available device: {devices['devices'][0]['name']}")
            else:
                logger.warning("No active Spotify devices found.")
        except Exception as e:
            logger.error(f"Error getting Spotify devices: {e}")

    def execute_action(self, action):
        if not self.sp or not self.device_id:
            logger.error("Spotify client not initialized or no device selected. Cannot execute action.")
            return

        command = action.command
        metadata = action.metadata or {}
        
        logger.info(f"Executing Spotify action: {command} with metadata: {metadata}")

        try:
            if command == "play":
                self.sp.start_playback(device_id=self.device_id, context_uri=metadata.get("context_uri"))
            elif command == "pause":
                self.sp.pause_playback(device_id=self.device_id)
            elif command == "next":
                self.sp.next_track(device_id=self.device_id)
            elif command == "previous":
                self.sp.previous_track(device_id=self.device_id)
            elif command == "set_volume":
                volume = metadata.get("volume", 50)
                self.sp.volume(volume_percent=volume, device_id=self.device_id)
            else:
                logger.warning(f"Unknown Spotify command: {command}")
        except spotipy.exceptions.SpotifyException as e:
            logger.error(f"Spotify API error: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during Spotify action execution: {e}")

if __name__ == '__main__':
    # Example usage for testing
    # You need to set these environment variables
    CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
    CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
    REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
    DEVICE_NAME = os.environ.get("SPOTIFY_DEVICE_NAME", None)

    if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]):
        print("Please set SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI environment variables.")
    else:
        logging.basicConfig(level=logging.INFO)
        spotify_controller = SpotifyController(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, DEVICE_NAME)
        
        if spotify_controller.sp and spotify_controller.device_id:
            print("Spotify controller initialized.")
            # Example of creating a mock action and executing it
            from models.actions import AudioAction
            
            # To test, you'll need a playlist URI
            playlist_uri = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M" # Example: Today's Top Hits
            
            play_action = AudioAction(command="play", metadata={"context_uri": playlist_uri})
            spotify_controller.execute_action(play_action)
            
            import time
            time.sleep(5)
            
            pause_action = AudioAction(command="pause")
            spotify_controller.execute_action(pause_action)
