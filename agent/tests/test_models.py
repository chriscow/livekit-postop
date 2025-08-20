"""
Tests for scheduling data models
"""
import pytest
from datetime import datetime, timedelta

from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType


class TestCallScheduleItem:
    """Tests for CallScheduleItem model"""
    
    def test_default_values(self):
        """Test that default values are set correctly"""
        call = CallScheduleItem()
        
        assert call.id is not None
        assert len(call.id) > 0
        assert call.call_type == CallType.WELLNESS_CHECK
        assert call.priority == 3
        assert call.status == CallStatus.PENDING
        assert call.max_attempts == 3
        assert call.attempt_count == 0
        assert isinstance(call.created_at, datetime)
        assert isinstance(call.updated_at, datetime)
    
    def test_custom_values(self):
        """Test creating CallScheduleItem with custom values"""
        scheduled_time = datetime(2025, 1, 15, 14, 0, 0)
        
        call = CallScheduleItem(
            patient_id="test-patient",
            patient_phone="+1234567890",
            scheduled_time=scheduled_time,
            call_type=CallType.DISCHARGE_REMINDER,
            priority=1,
            llm_prompt="Test prompt"
        )
        
        assert call.patient_id == "test-patient"
        assert call.patient_phone == "+1234567890"
        assert call.scheduled_time == scheduled_time
        assert call.call_type == CallType.DISCHARGE_REMINDER
        assert call.priority == 1
        assert call.llm_prompt == "Test prompt"
    
    def test_to_dict(self):
        """Test serialization to dictionary"""
        scheduled_time = datetime(2025, 1, 15, 14, 0, 0)
        
        call = CallScheduleItem(
            id="test-123",
            patient_id="patient-456",
            scheduled_time=scheduled_time,
            call_type=CallType.MEDICATION_REMINDER
        )
        
        data = call.to_dict()
        
        assert data["id"] == "test-123"
        assert data["patient_id"] == "patient-456"
        assert data["scheduled_time"] == scheduled_time.isoformat()
        assert data["call_type"] == "medication_reminder"
        assert data["status"] == "pending"
        assert isinstance(data["metadata"], str)  # Now serialized as JSON string
    
    def test_from_dict(self):
        """Test deserialization from dictionary"""
        data = {
            "id": "test-123",
            "patient_id": "patient-456",
            "patient_phone": "+1234567890",
            "scheduled_time": "2025-01-15T14:00:00",
            "call_type": "discharge_reminder",
            "priority": 2,
            "llm_prompt": "Test prompt",
            "status": "pending",
            "max_attempts": 3,
            "attempt_count": 0,
            "related_discharge_order_id": "order-123",
            "metadata": {"test": "value"},
            "notes": "Test notes",
            "created_at": "2025-01-15T10:00:00",
            "updated_at": "2025-01-15T10:00:00"
        }
        
        call = CallScheduleItem.from_dict(data)
        
        assert call.id == "test-123"
        assert call.patient_id == "patient-456"
        assert call.patient_phone == "+1234567890"
        assert call.scheduled_time == datetime(2025, 1, 15, 14, 0, 0)
        assert call.call_type == CallType.DISCHARGE_REMINDER
        assert call.priority == 2
        assert call.llm_prompt == "Test prompt"
        assert call.status == CallStatus.PENDING
        assert call.related_discharge_order_id == "order-123"
        assert call.metadata == {"test": "value"}
        assert call.notes == "Test notes"
    
    def test_can_retry(self):
        """Test retry logic"""
        call = CallScheduleItem(max_attempts=3, attempt_count=1)
        
        # Can retry when under max attempts and status allows
        call.status = CallStatus.FAILED
        assert call.can_retry() is True
        
        call.status = CallStatus.NO_ANSWER
        assert call.can_retry() is True
        
        # Cannot retry when at max attempts
        call.attempt_count = 3
        assert call.can_retry() is False
        
        # Cannot retry when status doesn't allow
        call.attempt_count = 1
        call.status = CallStatus.COMPLETED
        assert call.can_retry() is False
        
        call.status = CallStatus.CANCELLED
        assert call.can_retry() is False
    
    def test_increment_attempt(self):
        """Test attempt count increment"""
        call = CallScheduleItem(attempt_count=1)
        original_updated = call.updated_at
        
        # Wait a tiny bit to ensure timestamp changes
        import time
        time.sleep(0.001)
        
        call.increment_attempt()
        
        assert call.attempt_count == 2
        assert call.updated_at > original_updated


class TestCallRecord:
    """Tests for CallRecord model"""
    
    def test_default_values(self):
        """Test default values for CallRecord"""
        record = CallRecord()
        
        assert record.id is not None
        assert len(record.id) > 0
        assert record.status == CallStatus.PENDING
        assert record.retry_count == 0
        assert isinstance(record.patient_responses, dict)
        assert isinstance(record.additional_calls_scheduled, list)
        assert isinstance(record.created_at, datetime)
        assert isinstance(record.updated_at, datetime)
    
    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization/deserialization roundtrip"""
        started_time = datetime(2025, 1, 15, 14, 0, 0)
        ended_time = datetime(2025, 1, 15, 14, 5, 0)
        
        record = CallRecord(
            id="record-123",
            call_schedule_item_id="call-456",
            patient_id="patient-789",
            started_at=started_time,
            ended_at=ended_time,
            status=CallStatus.COMPLETED,
            room_name="test-room",
            patient_responses={"question1": "answer1"}
        )
        
        # Serialize and deserialize
        data = record.to_dict()
        restored_record = CallRecord.from_dict(data)
        
        assert restored_record.id == record.id
        assert restored_record.call_schedule_item_id == record.call_schedule_item_id
        assert restored_record.patient_id == record.patient_id
        assert restored_record.started_at == record.started_at
        assert restored_record.ended_at == record.ended_at
        assert restored_record.status == record.status
        assert restored_record.room_name == record.room_name
        assert restored_record.patient_responses == record.patient_responses
    
    def test_calculate_duration(self):
        """Test duration calculation"""
        record = CallRecord()
        
        # No duration when times not set
        record.calculate_duration()
        assert record.duration_seconds is None
        
        # Set start time only
        record.started_at = datetime(2025, 1, 15, 14, 0, 0)
        record.calculate_duration()
        assert record.duration_seconds is None
        
        # Set both times
        record.ended_at = datetime(2025, 1, 15, 14, 5, 30)  # 5 minutes 30 seconds later
        record.calculate_duration()
        
        assert record.duration_seconds == 330  # 5.5 minutes = 330 seconds
        assert isinstance(record.updated_at, datetime)


class TestEnums:
    """Tests for enum values"""
    
    def test_call_status_values(self):
        """Test CallStatus enum values"""
        assert CallStatus.PENDING.value == "pending"
        assert CallStatus.IN_PROGRESS.value == "in_progress"
        assert CallStatus.COMPLETED.value == "completed"
        assert CallStatus.FAILED.value == "failed"
        assert CallStatus.CANCELLED.value == "cancelled"
        assert CallStatus.NO_ANSWER.value == "no_answer"
        assert CallStatus.VOICEMAIL.value == "voicemail"
    
    def test_call_type_values(self):
        """Test CallType enum values"""
        assert CallType.DISCHARGE_REMINDER.value == "discharge_reminder"
        assert CallType.WELLNESS_CHECK.value == "wellness_check"
        assert CallType.MEDICATION_REMINDER.value == "medication_reminder"
        assert CallType.FOLLOW_UP.value == "follow_up"
        assert CallType.URGENT.value == "urgent"