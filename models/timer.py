from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class TimerMilestone:
    """Represents an action or message triggered at a specific countdown time"""
    time_remaining: int  # seconds remaining when this milestone triggers
    action_type: str  # 'spotify', 'lighting', 'atem', 'message', 'custom'
    action_payload: Dict[str, Any]  # action-specific data
    message: Optional[str] = None  # optional message to display
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'time_remaining': self.time_remaining,
            'action_type': self.action_type,
            'action_payload': self.action_payload,
            'message': self.message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimerMilestone':
        return cls(
            time_remaining=data['time_remaining'],
            action_type=data['action_type'],
            action_payload=data['action_payload'],
            message=data.get('message')
        )

@dataclass
class Timer:
    """Represents a countdown timer configuration"""
    timer_id: str
    name: str
    duration: int  # total duration in seconds
    milestones: List[TimerMilestone] = field(default_factory=list)
    field_id: Optional[str] = None  # optional field assignment for match data display
    created_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
        if self.name is None:
            self.name = "Untitled Timer"
        self.name = str(self.name)

    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timer_id': self.timer_id,
            'name': self.name,
            'duration': self.duration,
            'milestones': [m.to_dict() for m in self.milestones],
            'field_id': self.field_id,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Timer':
        milestones = [TimerMilestone.from_dict(m) for m in data.get('milestones', [])]
        return cls(
            timer_id=data['timer_id'],
            name=data['name'],
            duration=data['duration'],
            milestones=milestones,
            field_id=data.get('field_id'),
            created_at=data.get('created_at')
        )

@dataclass
class TimerState:
    """Represents the runtime state of an active timer"""
    timer_id: str
    start_timestamp: float  # Unix timestamp when timer started
    end_timestamp: float  # Unix timestamp when timer should finish
    is_running: bool
    duration: int  # original duration in seconds
    paused_at: Optional[float] = None  # Unix timestamp when paused
    last_milestone_triggered: Optional[int] = None  # last milestone time_remaining value triggered
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timer_id': self.timer_id,
            'start_timestamp': self.start_timestamp,
            'end_timestamp': self.end_timestamp,
            'is_running': self.is_running,
            'duration': self.duration,
            'paused_at': self.paused_at,
            'last_milestone_triggered': self.last_milestone_triggered
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimerState':
        return cls(
            timer_id=data['timer_id'],
            start_timestamp=data['start_timestamp'],
            end_timestamp=data['end_timestamp'],
            is_running=data['is_running'],
            duration=data['duration'],
            paused_at=data.get('paused_at'),
            last_milestone_triggered=data.get('last_milestone_triggered')
        )
