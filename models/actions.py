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
    target_type: Optional[str] = "cue"  # 'cue' or 'playback'
    command: Optional[str] = "fire"  # 'fire', 'go', 'pause', 'next'
    type: str = "lighting"

import fnmatch

# ... existing code ...

class ActionMapping(BaseModel):
    def __init__(self, on_event=None, on_state_change=None):
        self.on_event = on_event or {}
        self.on_state_change = on_state_change or {}

    def get_actions(self, category, key, field_id=None, match_name=None):
        """
        Retrieves actions for a given category (e.g., 'on_event'), key (e.g., 'matchStarted'),
        and optional field_id and match_name.
        
        It aggregates actions based on match name patterns ('*') and field IDs,
        then filters for the highest priority action per type.
        """
        logger.debug(f"Getting actions for category='{key}', field_id='{field_id}', match_name='{match_name}'")
        all_actions = []
        
        action_groups = category.get(key, [])
        logger.debug(f"Found action groups: {action_groups}")

        # For backward compatibility with the old format (dict or list)
        if isinstance(action_groups, dict):
            # It's the format with "all" and field numbers
            all_actions.extend(action_groups.get("all", []))
            if field_id:
                all_actions.extend(action_groups.get(str(field_id), []))
            return all_actions
        if not isinstance(action_groups, list):
            # If it's not a dict or list, it's an unknown format.
            return []

        # New format: list of {"match_name": "...", "fields": {...}}
        for group in action_groups:
            group_match_name = group.get("match_name", "*")
            logger.debug(f"Evaluating group with match_name pattern: '{group_match_name}'")
            
            # Check if the match name pattern matches
            if match_name and fnmatch.fnmatch(match_name, group_match_name):
                logger.debug(f"Match! Current match_name '{match_name}' matches pattern '{group_match_name}'.")
                fields = group.get("fields", {})
                
                # Combine actions from "all" and the specific field
                potential_actions = fields.get("all", []) + (fields.get(str(field_id), []) if field_id else [])
                
                for action_data in potential_actions:
                    # Add the matched pattern's priority to the action for ranking
                    action_data_copy = action_data.copy()
                    action_data_copy['priority'] = action_data.get('priority', 0)
                    all_actions.append(action_data_copy)

            else:
                logger.debug(f"No match. Current match_name '{match_name}' does not match pattern '{group_match_name}'.")
        
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
            
            # Find the highest priority in this group
            max_priority = max(a.get('priority', 0) for a in typed_actions)

            # Collect all actions with that highest priority
            for action in typed_actions:
                if action.get('priority', 0) == max_priority:
                    final_actions.append(action)

        logger.debug(f"Returning {len(final_actions)} prioritized actions: {final_actions}")
        return final_actions
