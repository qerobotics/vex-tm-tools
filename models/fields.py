from .base import BaseModel
from datetime import datetime

class FieldState(BaseModel):
    def __init__(self, field_id, state, match_name=None, match_id=None, last_updated=None):
        self.field_id = field_id
        self.state = state  # e.g., "queued", "countdown", "active", "finish", "standby"
        
        # Handle legacy match_id field
        if match_id and not match_name:
            if isinstance(match_id, dict):
                # Assuming match_id is an object like {"round": "QUAL", "match": 21}
                round_val = match_id.get("round")
                round_prefix = round_val[0].upper() if round_val else "M"
                self.match_name = f"{round_prefix}{match_id.get('match', '')}"
            else:
                # Fallback for older string format
                self.match_name = str(match_id)
        else:
            self.match_name = match_name
            
        self.last_updated = last_updated or datetime.utcnow().isoformat()