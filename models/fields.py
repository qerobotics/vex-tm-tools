from .base import BaseModel
from datetime import datetime

class FieldState(BaseModel):
    def __init__(self, field_id, state, match_id=None, last_updated=None):
        self.field_id = field_id
        self.state = state  # e.g., "queued", "countdown", "active", "finish", "standby"
        self.match_id = match_id
        self.last_updated = last_updated or datetime.utcnow().isoformat()