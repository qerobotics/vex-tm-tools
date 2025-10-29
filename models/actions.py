from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime
from .base import BaseModel

@dataclass
class Action(BaseModel):
    command: str
    metadata: Optional[dict] = None
    type: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class AudioAction(Action):
    type: str = "audio"

@dataclass
class VideoAction(Action):
    type: str = "video"

@dataclass
class LightingAction(Action):
    type: str = "lighting"

class ActionMapping(BaseModel):
    def __init__(self, on_event=None, on_state_change=None):
        self.on_event = on_event or {}
        self.on_state_change = on_state_change or {}
