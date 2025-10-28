from .base import BaseModel
from datetime import datetime

class AuditEntry(BaseModel):
    def __init__(self, event_id, timestamp=None, status=None, action_id=None, outcome=None):
        self.event_id = event_id
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.status = status # e.g., "received", "processed", "failed"
        self.action_id = action_id
        self.outcome = outcome # e.g., "success", "failure"
