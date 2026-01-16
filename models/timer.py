from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import time

@dataclass
class ActionList:
    """Represents a reusable list of timed actions"""
    id: str
    name: str
    description: Optional[str] = None
    milestones: List['TimerMilestone'] = field(default_factory=list)
    created_at: Optional[str] = None
    # Match linking fields - automatically determines field from match
    division_id: Optional[int] = None
    round: Optional[str] = None  # 'QUAL', 'TOP_N', etc.
    instance: Optional[int] = None
    match_number: Optional[int] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'milestones': [m.to_dict() for m in self.milestones],
            'created_at': self.created_at,
            'division_id': self.division_id,
            'round': self.round,
            'instance': self.instance,
            'match_number': self.match_number
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActionList':
        milestones = [TimerMilestone.from_dict(m) for m in data.get('milestones', [])]
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description'),
            milestones=milestones,
            created_at=data.get('created_at'),
            division_id=data.get('division_id'),
            round=data.get('round'),
            instance=data.get('instance'),
            match_number=data.get('match_number')
        )

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
    milestones: List[TimerMilestone] = field(default_factory=list)  # Legacy support
    action_list_id: Optional[str] = None  # Reference to action list
    field_id: Optional[str] = None  # optional field assignment for match data display
    created_at: Optional[str] = None
    ready_states: Dict[str, bool] = field(default_factory=dict)  # Track which users pressed ready
    auto_start_tm: bool = False  # Auto-start TM countdown at 3 seconds
    match_number: Optional[str] = None  # Linked match number from schedule
    auto_detect_action_list: bool = True  # Auto-detect action list from current match
    
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
            'action_list_id': self.action_list_id,
            'field_id': self.field_id,
            'created_at': self.created_at,
            'ready_states': self.ready_states,
            'auto_start_tm': self.auto_start_tm,
            'match_number': self.match_number,
            'auto_detect_action_list': self.auto_detect_action_list
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Timer':
        milestones = [TimerMilestone.from_dict(m) for m in data.get('milestones', [])]
        return cls(
            timer_id=data['timer_id'],
            name=data['name'],
            duration=data['duration'],
            milestones=milestones,
            action_list_id=data.get('action_list_id'),
            field_id=data.get('field_id'),
            created_at=data.get('created_at'),
            ready_states=data.get('ready_states', {}),
            auto_start_tm=data.get('auto_start_tm', False),
            match_number=data.get('match_number'),
            auto_detect_action_list=data.get('auto_detect_action_list', True)
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
        current_time = time.time()
        return cls(
            timer_id=data.get('timer_id', 'unknown'),
            start_timestamp=data.get('start_timestamp', current_time),
            end_timestamp=data.get('end_timestamp', current_time),
            is_running=data.get('is_running', False),
            duration=data.get('duration', 0),
            paused_at=data.get('paused_at'),
            last_milestone_triggered=data.get('last_milestone_triggered')
        )
