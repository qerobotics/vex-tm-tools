import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import re
import logging
import random
import time

logger = logging.getLogger(__name__)

def _extract_match_number(match_name):
    if not match_name:
        return None
    
    numbers = re.findall(r'\d+', match_name)
    if numbers:
        return int(numbers[-1])
    return None

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

        for attempt in range(2): # Try once, then retry once
            try:
                if command == "play":
                    self.sp.start_playback(device_id=self.device_id, context_uri=metadata.get("context_uri"))
                elif command == "play_playlist_track":
                    playlist_uri = metadata.get("playlist_uri")
                    track_number = metadata.get("track_number") # 1-based index
                    
                    if not playlist_uri:
                        logger.error("play_playlist_track command requires 'playlist_uri' in metadata.")
                        return

                    if track_number is not None:
                        logger.info(f"Playing track {track_number} from playlist {playlist_uri}")
                        # Spotify API is 0-indexed for tracks
                        self.sp.start_playback(device_id=self.device_id, context_uri=playlist_uri, offset={"position": track_number - 1})
                    else:
                        logger.info(f"No track number provided. Playing a random track from playlist {playlist_uri}")
                        try:
                            # Get the total number of tracks in the playlist
                            playlist_items = self.sp.playlist_items(playlist_uri, fields='total')
                            if not playlist_items:
                                logger.warning(f"Could not retrieve items for playlist {playlist_uri}.")
                                return

                            total_tracks = playlist_items.get('total', 0)
                            
                            if total_tracks > 0:
                                # Pick a random track
                                random_track_index = random.randint(0, total_tracks - 1)
                                logger.info(f"Selected random track number {random_track_index + 1} out of {total_tracks}")
                                self.sp.start_playback(device_id=self.device_id, context_uri=playlist_uri, offset={"position": random_track_index})
                            else:
                                logger.warning(f"Playlist {playlist_uri} is empty. Cannot play a random track.")
                        except spotipy.exceptions.SpotifyException as e:
                            logger.error(f"Could not fetch playlist details to play random track: {e}")

                elif command == "play_track":
                    track_uri = metadata.get("track_uri")
                    start_time_s = metadata.get("start_time_s", 0)

                    if not track_uri:
                        logger.error("play_track command requires 'track_uri' in metadata.")
                        return
                    
                    # Ensure track_uri is in the correct format
                    if not track_uri.startswith("spotify:track:"):
                        track_uri = f"spotify:track:{track_uri}"

                    start_time_ms = int(start_time_s) * 1000
                    
                    logger.info(f"Playing track {track_uri} starting at {start_time_s}s ({start_time_ms}ms)")
                    self.sp.start_playback(device_id=self.device_id, uris=[track_uri], position_ms=start_time_ms)

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
                
                break # If successful, exit the loop
            except spotipy.exceptions.SpotifyException as e:
                logger.error(f"Spotify API error on attempt {attempt + 1}: {e}")
                if attempt == 1: # Last attempt failed
                    logger.error("Spotify command failed after multiple retries.")
                else:
                    time.sleep(1) # Wait 1 second before retrying
            except Exception as e:
                logger.error(f"An unexpected error occurred during Spotify action execution: {e}")
                break # Don't retry on unexpected errors

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
