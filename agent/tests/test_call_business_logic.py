"""
Tests for call business logic - pure functions with no external dependencies
"""
import pytest
from datetime import datetime

from followup.call_business_logic import (
    prepare_call_metadata, generate_room_name, should_retry_call, 
    calculate_retry_delay, classify_sip_error, update_call_record_for_attempt,
    update_call_record_for_success, update_call_record_for_failure,
    create_success_result, create_failure_result
)
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType


class TestPureBusinessLogic:
    """Tests for pure business logic functions"""
    
    def test_prepare_call_metadata(self, sample_call_item):
        """Test call metadata preparation"""
        metadata = prepare_call_metadata(sample_call_item)
        
        assert "call_schedule_item" in metadata
        assert metadata["patient_phone"] == sample_call_item.patient_phone
        assert metadata["call_type"] == sample_call_item.call_type.value
        assert metadata["related_order_id"] == sample_call_item.related_discharge_order_id
    
    def test_generate_room_name(self, sample_call_item):
        """Test room name generation"""
        room_name = generate_room_name(sample_call_item)
        assert room_name == f"followup-{sample_call_item.id}"
    
    def test_should_retry_call_under_max_attempts(self):
        """Test retry logic when under max attempts"""
        # Retryable SIP codes
        assert should_retry_call("486", 1, 3) is True  # Busy
        assert should_retry_call("487", 2, 3) is True  # Cancelled
        assert should_retry_call("408", 1, 3) is True  # Timeout
        assert should_retry_call("503", 2, 3) is True  # Service unavailable
    
    def test_should_not_retry_call_at_max_attempts(self):
        """Test no retry when at max attempts"""
        assert should_retry_call("486", 3, 3) is False
        assert should_retry_call("487", 4, 3) is False
    
    def test_should_not_retry_permanent_failures(self):
        """Test no retry for permanent SIP failures"""
        assert should_retry_call("404", 1, 3) is False  # Not found
        assert should_retry_call("410", 1, 3) is False  # Gone
        assert should_retry_call("603", 1, 3) is False  # Decline
    
    def test_calculate_retry_delay(self):
        """Test retry delay calculation"""
        assert calculate_retry_delay(1) == 300   # 5 minutes
        assert calculate_retry_delay(2) == 900   # 15 minutes
        assert calculate_retry_delay(3) == 1800  # 30 minutes
        assert calculate_retry_delay(4) == 1800  # Caps at 30 minutes
    
    def test_classify_sip_error_retryable(self):
        """Test SIP error classification for retryable errors"""
        message, retryable = classify_sip_error("486")
        assert "busy" in message.lower()
        assert retryable is True
        
        message, retryable = classify_sip_error("408")
        assert "no answer" in message.lower()
        assert retryable is True
    
    def test_classify_sip_error_permanent(self):
        """Test SIP error classification for permanent errors"""
        message, retryable = classify_sip_error("404")
        assert "not found" in message.lower()
        assert retryable is False
        
        message, retryable = classify_sip_error("603")
        assert "declined" in message.lower()
        assert retryable is False
    
    def test_classify_sip_error_unknown(self):
        """Test SIP error classification for unknown codes"""
        message, retryable = classify_sip_error("999")
        assert "999" in message
        assert retryable is True  # Unknown errors are retryable by default
    
    def test_update_call_record_for_attempt(self, sample_call_record):
        """Test updating call record for attempt"""
        room_name = "test-room"
        attempt_number = 2
        
        update_call_record_for_attempt(sample_call_record, room_name, attempt_number)
        
        assert sample_call_record.room_name == room_name
        assert sample_call_record.participant_identity == "patient"
        assert sample_call_record.status == CallStatus.IN_PROGRESS
        assert sample_call_record.retry_count == attempt_number
        assert sample_call_record.started_at is not None
        assert sample_call_record.updated_at is not None
    
    def test_update_call_record_for_success(self, sample_call_record):
        """Test updating call record for success"""
        dispatch_id = "dispatch-123"
        participant_id = "participant-456"
        
        update_call_record_for_success(sample_call_record, dispatch_id, participant_id)
        
        assert dispatch_id in sample_call_record.outcome_notes
        assert participant_id in sample_call_record.outcome_notes
        assert "success" in sample_call_record.outcome_notes.lower()
        assert sample_call_record.updated_at is not None
    
    def test_update_call_record_for_failure(self, sample_call_record):
        """Test updating call record for failure"""
        error_message = "Test error"
        sip_code = "486"
        sip_text = "Busy Here"
        
        update_call_record_for_failure(sample_call_record, error_message, sip_code, sip_text)
        
        assert sample_call_record.status == CallStatus.FAILED
        assert sample_call_record.error_message == error_message
        assert sip_code in sample_call_record.outcome_notes
        assert sip_text in sample_call_record.outcome_notes
        assert error_message in sample_call_record.outcome_notes
        assert sample_call_record.ended_at is not None
        assert sample_call_record.updated_at is not None
    
    def test_create_success_result(self):
        """Test creating success result"""
        room_name = "test-room"
        dispatch_id = "dispatch-123"
        participant_id = "participant-456"
        
        result = create_success_result(room_name, dispatch_id, participant_id)
        
        assert result["room_name"] == room_name
        assert result["dispatch_id"] == dispatch_id
        assert result["sip_participant_id"] == participant_id
        assert result["participant_identity"] == "patient"
        assert "success" in result["outcome"].lower()
    
    def test_create_failure_result_with_sip_error(self):
        """Test creating failure result with SIP error"""
        room_name = "test-room"
        error_message = "SIP error"
        sip_code = "486"
        sip_text = "Busy Here"
        
        result = create_failure_result(room_name, error_message, sip_code, sip_text)
        
        assert result["room_name"] == room_name
        assert result["error"] == error_message
        assert result["sip_status_code"] == sip_code
        assert result["sip_status"] == sip_text
        assert result["retryable"] is True  # 486 is retryable
        assert "busy" in result["human_message"].lower()
    
    def test_create_failure_result_without_sip_error(self):
        """Test creating failure result without SIP error"""
        room_name = "test-room"
        error_message = "Generic error"
        
        result = create_failure_result(room_name, error_message)
        
        assert result["room_name"] == room_name
        assert result["error"] == error_message
        assert result["sip_status_code"] is None
        assert result["retryable"] is True  # Generic errors are retryable
        assert result["human_message"] == error_message