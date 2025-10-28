from .base import BaseModel

class Action(BaseModel):
    def __init__(self, id, type, target_device=None, metadata=None, retry_policy=None):
        self.id = id
        self.type = type
        self.target_device = target_device
        self.metadata = metadata or {}
        self.retry_policy = retry_policy or {"retries": 0, "delay": 0}

class LightingAction(Action):
    def __init__(self, preset_id, **kwargs):
        super().__init__(type="lighting", **kwargs)
        self.preset_id = preset_id

class VideoAction(Action):
    def __init__(self, camera_id, **kwargs):
        super().__init__(type="video", **kwargs)
        self.camera_id = camera_id

class AudioAction(Action):
    def __init__(self, command, **kwargs):
        super().__init__(type="audio", **kwargs)
        self.command = command # e.g., "play", "pause", "next"

class ActionMapping(BaseModel):
    def __init__(self, on_event=None, on_state_change=None):
        self.on_event = on_event or {}
        self.on_state_change = on_state_change or {}
