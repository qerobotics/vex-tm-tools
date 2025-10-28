from .base import BaseModel

class Config(BaseModel):
    def __init__(self, device_ips=None, field_to_camera=None, spotify_device_id=None, websocket_endpoints=None, schedule_lead_matches=5, match_queue_pause=None, paused=None, rooms=None):
        self.device_ips = device_ips or {}
        self.field_to_camera = field_to_camera or {}
        self.spotify_device_id = spotify_device_id
        self.websocket_endpoints = websocket_endpoints or {}
        self.schedule_lead_matches = schedule_lead_matches
        self.match_queue_pause = match_queue_pause or {"start": None, "end": None}
        self.paused = paused or {"video": False, "audio": False, "lighting": False}
        self.rooms = rooms or {}
