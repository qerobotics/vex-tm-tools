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

    def get_actions(self, category, key, field_id=None):
        """
        Retrieves actions for a given category (e.g., 'on_event'), key (e.g., 'matchStarted'),
        and optional field_id.
        
        It aggregates actions for 'all' fields and the specific field_id.
        """
        actions = []
        
        # Get the dictionary of actions for the specific event or state change
        action_group = category.get(key, {})
        
        # If the action group is a list, it's the old format.
        # Treat it as actions for "all" fields for backward compatibility.
        if isinstance(action_group, list):
            return action_group

        # New format: action_group is a dict with keys like "all", "1", "2", etc.
        # Get actions that apply to all fields
        actions.extend(action_group.get("all", []))
        
        # Get actions for the specific field if a field_id is provided
        if field_id:
            actions.extend(action_group.get(str(field_id), []))
            
        return actions