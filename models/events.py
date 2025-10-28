from .base import BaseModel
import uuid
from datetime import datetime

class Event(BaseModel):
    def __init__(self, type, timestamp=None, field=None, payload=None, id=None):
        self.id = id or str(uuid.uuid4())
        self.type = type
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.field = field
        self.payload = payload or {}
