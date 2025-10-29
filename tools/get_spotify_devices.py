
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os

def get_spotify_devices():
    """
    Connects to the Spotify API using credentials from storage/config.json
    and lists all available playback devices.
    """
    config_path = os.path.join(os.path.dirname(__file__), '..', 'storage', 'config.json')
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        spotify_creds = config.get("device_ips", {}).get("spotify", {})
        client_id = spotify_creds.get("client_id")
        client_secret = spotify_creds.get("client_secret")
        redirect_uri = spotify_creds.get("redirect_uri")

        if not all([client_id, client_secret, redirect_uri]):
            print("Error: Spotify credentials (client_id, client_secret, redirect_uri) not found in storage/config.json")
            return

    except FileNotFoundError:
        print(f"Error: Config file not found at {config_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {config_path}")
        return

    try:
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-read-playback-state"
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        devices = sp.devices()
        
        if devices and devices['devices']:
            print("Found the following Spotify devices:")
            print("-" * 40)
            for device in devices['devices']:
                is_active = " (active)" if device['is_active'] else ""
                print(f"Name: {device['name']}{is_active}")
                print(f"  ID: {device['id']}")
                print(f"  Type: {device['type']}")
                print("-" * 40)
        else:
            print("No active Spotify devices found.")
            print("Please make sure Spotify is running on one of your devices.")

    except Exception as e:
        print(f"An error occurred: {e}")
        print("Please ensure you have authenticated correctly.")
        print(f"You might need to open a URL in your browser and paste the redirect URL here if prompted.")

if __name__ == '__main__':
    get_spotify_devices()
