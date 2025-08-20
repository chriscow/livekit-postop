"""
Data models for the PostOp AI call scheduling system
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import uuid


class CallStatus(Enum):
    """Status of a scheduled call"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"


class CallType(Enum):
    """Type of scheduled call"""
    DISCHARGE_REMINDER = "discharge_reminder"
    WELLNESS_CHECK = "wellness_check"
    MEDICATION_REMINDER = "medication_reminder"
    FOLLOW_UP = "follow_up"
    URGENT = "urgent"
    # LLM-generated call types
    COMPRESSION_CHECK = "compression_check"
    ACTIVITY_GUIDANCE = "activity_guidance"
    GENERAL_FOLLOWUP = "general_followup"
    
    @classmethod
    def from_string(cls, value: str) -> "CallType":
        """Convert string to CallType, with fallback for unknown types"""
        if not value:
            return cls.GENERAL_FOLLOWUP
        
        # Try exact match first
        try:
            return cls(value)
        except ValueError:
            pass
        
        # Try common mappings
        value_lower = value.lower().replace(' ', '_').replace('-', '_')
        mapping = {
            'compression_reminder': cls.COMPRESSION_CHECK,
            'medication_check': cls.MEDICATION_REMINDER,
            'wellness_call': cls.WELLNESS_CHECK,
            'followup': cls.GENERAL_FOLLOWUP,
            'follow_up_call': cls.FOLLOW_UP,
            'general_follow_up': cls.GENERAL_FOLLOWUP,
            'discharge_followup': cls.DISCHARGE_REMINDER,
        }
        
        if value_lower in mapping:
            return mapping[value_lower]
        
        # Default fallback
        return cls.GENERAL_FOLLOWUP


@dataclass
class CallScheduleItem:
    """
    Represents a scheduled follow-up call for a patient.
    Each call has its own LLM prompt that defines the conversation purpose.
    """
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str = ""
    patient_phone: str = ""
    
    # Scheduling details
    scheduled_time: datetime = field(default_factory=datetime.now)
    call_type: CallType = CallType.WELLNESS_CHECK
    priority: int = 3  # 1=urgent, 2=important, 3=routine
    
    # Call content and execution
    llm_prompt: str = ""  # The conversation instructions for this specific call
    status: CallStatus = CallStatus.PENDING
    
    # Retry and failure handling
    max_attempts: int = 3
    attempt_count: int = 0
    
    # Optional discharge order reference
    related_discharge_order_id: Optional[str] = None
    
    # Metadata and notes
    metadata: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        import json
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_phone": self.patient_phone,
            "scheduled_time": self.scheduled_time.isoformat(),
            "call_type": self.call_type.value,
            "priority": self.priority,
            "llm_prompt": self.llm_prompt,
            "status": self.status.value,
            "max_attempts": self.max_attempts,
            "attempt_count": self.attempt_count,
            "related_discharge_order_id": self.related_discharge_order_id,
            "metadata": json.dumps(self.metadata),
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallScheduleItem":
        """Create from dictionary"""
        # Handle Redis empty strings as None
        related_order_id = data.get("related_discharge_order_id")
        if related_order_id == "":
            related_order_id = None
        
        # Parse metadata if it's a string (from Redis)
        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            import json
            metadata = json.loads(metadata) if metadata else {}
        
        return cls(
            id=data["id"],
            patient_id=data["patient_id"],
            patient_phone=data["patient_phone"],
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]),
            call_type=CallType.from_string(data["call_type"]),
            priority=int(data["priority"]),
            llm_prompt=data["llm_prompt"],
            status=CallStatus(data["status"]),
            max_attempts=int(data["max_attempts"]),
            attempt_count=int(data["attempt_count"]),
            related_discharge_order_id=related_order_id,
            metadata=metadata,
            notes=data.get("notes", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )
    
    def can_retry(self) -> bool:
        """Check if this call can be retried"""
        return (
            self.attempt_count < self.max_attempts and 
            self.status in [CallStatus.FAILED, CallStatus.NO_ANSWER]
        )
    
    def increment_attempt(self):
        """Increment attempt count and update timestamp"""
        self.attempt_count += 1
        self.updated_at = datetime.now()


@dataclass 
class CallRecord:
    """
    Records the outcome and details of an executed call
    """
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    call_schedule_item_id: str = ""
    patient_id: str = ""
    
    # Call execution details
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    
    # Call outcome
    status: CallStatus = CallStatus.PENDING
    outcome_notes: str = ""
    
    # LiveKit details
    room_name: Optional[str] = None
    participant_identity: Optional[str] = None
    
    # Error information
    error_message: Optional[str] = None
    retry_count: int = 0
    
    # Conversation summary (optional)
    conversation_summary: str = ""
    patient_responses: Dict[str, Any] = field(default_factory=dict)
    
    # Additional scheduled calls created during this call
    additional_calls_scheduled: list[str] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "call_schedule_item_id": self.call_schedule_item_id,
            "patient_id": self.patient_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "outcome_notes": self.outcome_notes,
            "room_name": self.room_name,
            "participant_identity": self.participant_identity,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "conversation_summary": self.conversation_summary,
            "patient_responses": self.patient_responses,
            "additional_calls_scheduled": self.additional_calls_scheduled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallRecord":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            call_schedule_item_id=data["call_schedule_item_id"],
            patient_id=data["patient_id"],
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            duration_seconds=data.get("duration_seconds"),
            status=CallStatus(data["status"]),
            outcome_notes=data.get("outcome_notes", ""),
            room_name=data.get("room_name"),
            participant_identity=data.get("participant_identity"),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            conversation_summary=data.get("conversation_summary", ""),
            patient_responses=data.get("patient_responses", {}),
            additional_calls_scheduled=data.get("additional_calls_scheduled", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )
    
    def calculate_duration(self):
        """Calculate and set duration from start/end times"""
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
            self.updated_at = datetime.now()