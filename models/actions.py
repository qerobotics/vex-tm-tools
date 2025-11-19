from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime
from .base import BaseModel
import logging

logger = logging.getLogger(__name__)

@dataclass
class Action(BaseModel):
    command: str
    metadata: Optional[dict] = None
    type: Optional[str] = None
    priority: int = 0
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
    preset_id: Optional[str] = None
    release_id: Optional[str] = None
    target_type: Optional[str] = "playback"  # 'cue' or 'playback'
    command: Optional[str] = "go"  # 'release', 'go', 'pause', 'next'
    osc_address: Optional[str] = None
    osc_value: Optional[float] = None
    delay_s: Optional[int] = None
    type: str = "lighting"

import fnmatch

# ... existing code ...

class ActionMapping(BaseModel):
    def __init__(self, on_event=None, on_state_change=None):
        self.on_event = on_event or {}
        self.on_state_change = on_state_change or {}

    def get_actions(self, category, key, field_id=None, match_name=None, event_payload=None):
        """
        Retrieves actions for a given category (e.g., 'on_event'), key (e.g., 'matchStarted'),
        and optional field_id, match_name, and event_payload.
        
        It aggregates actions based on match name patterns, payload filters, and field IDs,
        then filters for the highest priority action per type.
        """
        logger.debug(f"Getting actions for category='{key}', field_id='{field_id}', match_name='{match_name}', payload='{event_payload}'")
        all_actions = []
        
        action_groups = category.get(key, [])
        logger.debug(f"Found action groups: {action_groups}")

        if not isinstance(action_groups, list):
            return []

        for group in action_groups:
            group_match_name = group.get("match_name", "*")
            
            # 1. Check payload filter
            payload_filter = group.get("payload_filter")
            if payload_filter:
                if not event_payload:
                    logger.debug("Group has payload_filter but event has no payload. Skipping.")
                    continue
                
                payload_match = all(event_payload.get(k) == v for k, v in payload_filter.items())
                
                if not payload_match:
                    logger.debug(f"Payload filter mismatch. Event: {event_payload}, Filter: {payload_filter}. Skipping.")
                    continue
                logger.debug("Payload filter matched.")

            # 2. Check match name pattern
            # If match_name is None (e.g. for non-match events), it should only match '*'
            if match_name is None:
                if group_match_name != "*":
                    logger.debug(f"No match_name in event, but group requires '{group_match_name}'. Skipping.")
                    continue
            elif not fnmatch.fnmatch(match_name, group_match_name):
                logger.debug(f"Match name '{match_name}' does not match pattern '{group_match_name}'. Skipping.")
                continue
            
            logger.debug(f"Match! Name:'{match_name}' vs Pattern:'{group_match_name}'.")
            
            # 3. Collect actions if filters passed
            fields = group.get("fields", {})
            potential_actions = fields.get("all", []) + (fields.get(str(field_id), []) if field_id else [])
            
            for action_data in potential_actions:
                action_data_copy = action_data.copy()
                action_data_copy['priority'] = action_data.get('priority', 0)
                all_actions.append(action_data_copy)
        
        # Prioritize and filter actions
        actions_by_type = {}
        for action in all_actions:
            action_type = action.get("type")
            if not action_type:
                continue
            if action_type not in actions_by_type:
                actions_by_type[action_type] = []
            actions_by_type[action_type].append(action)

        final_actions = []
        for action_type, typed_actions in actions_by_type.items():
            if not typed_actions:
                continue
            
            max_priority = max(a.get('priority', 0) for a in typed_actions)

            for action in typed_actions:
                if action.get('priority', 0) == max_priority:
                    final_actions.append(action)

        logger.debug(f"Returning {len(final_actions)} prioritized actions: {final_actions}")
        return final_actions
