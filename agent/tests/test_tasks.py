"""
Tests for RQ tasks functionality
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from scheduling.tasks import (
    execute_followup_call, process_pending_calls, generate_patient_calls
)
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from followup.livekit_adapter import MockLiveKitAdapter


class TestExecuteFollowupCall:
    """Tests for execute_followup_call task"""
    
    @patch('scheduling.tasks.CallScheduler')
    @patch('scheduling.tasks.execute_livekit_call')
    def test_execute_followup_call_success(self, mock_execute_call, mock_scheduler_class):
        """Test successful call execution"""
        # Setup mocks
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        # Mock call item
        call_item = CallScheduleItem(
            id="test-call-123",
            patient_id="patient-456",
            patient_phone="+1234567890",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Test call"
        )
        mock_scheduler.get_call.return_value = call_item
        
        # Mock successful call execution
        mock_execute_call.return_value = (True, {"outcome": "success"})
        
        # Execute task
        result = execute_followup_call("test-call-123")
        
        # Verify result
        assert result["success"] is True
        assert result["call_id"] == "test-call-123"
        
        # Verify scheduler interactions
        mock_scheduler.get_call.assert_called_once_with("test-call-123")
        mock_scheduler.update_call_status.assert_called_with(
            "test-call-123",
            CallStatus.IN_PROGRESS,
            "Executing call"
        )
        mock_scheduler.save_call_record.assert_called_once()
        
        # Verify call execution
        mock_execute_call.assert_called_once()
        call_record = mock_execute_call.call_args[0][1]
        assert call_record.call_schedule_item_id == "test-call-123"
        assert call_record.patient_id == "patient-456"
    
    @patch('scheduling.tasks.CallScheduler')
    @patch('scheduling.tasks.execute_livekit_call')
    def test_execute_followup_call_failure_retryable(self, mock_execute_call, mock_scheduler_class):
        """Test call execution failure that should be retried"""
        # Setup mocks
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        call_item = CallScheduleItem(
            id="test-call-123",
            patient_id="patient-456",
            patient_phone="+1234567890",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Test call",
            metadata={"attempt_count": 1}
        )
        mock_scheduler.get_call.return_value = call_item
        
        # Mock failed call execution (retryable)
        mock_execute_call.return_value = (False, {
            "error": "SIP error",
            "sip_status_code": "486",  # Busy - retryable
            "retryable": True
        })
        
        # Execute task
        result = execute_followup_call("test-call-123")
        
        # Verify result indicates retry needed
        assert result["success"] is False
        assert result["should_retry"] is True
        assert result["retry_delay"] > 0
        
        # Verify call status updated to failed
        mock_scheduler.update_call_status.assert_called_with(
            "test-call-123",
            CallStatus.FAILED,
            "SIP error"
        )
    
    @patch('scheduling.tasks.CallScheduler')
    @patch('scheduling.tasks.execute_livekit_call') 
    def test_execute_followup_call_failure_permanent(self, mock_execute_call, mock_scheduler_class):
        """Test call execution failure that should not be retried"""
        # Setup mocks
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        call_item = CallScheduleItem(
            id="test-call-123",
            patient_id="patient-456",
            patient_phone="+1234567890",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Test call",
            metadata={"attempt_count": 1}
        )
        mock_scheduler.get_call.return_value = call_item
        
        # Mock failed call execution (permanent failure)
        mock_execute_call.return_value = (False, {
            "error": "Phone number not found",
            "sip_status_code": "404",  # Not found - permanent
            "retryable": False
        })
        
        # Execute task
        result = execute_followup_call("test-call-123")
        
        # Verify result indicates no retry
        assert result["success"] is False
        assert result["should_retry"] is False
        
        # Verify call status updated to permanently failed
        mock_scheduler.update_call_status.assert_called_with(
            "test-call-123",
            CallStatus.PERMANENTLY_FAILED,
            "Phone number not found"
        )
    
    @patch('scheduling.tasks.CallScheduler')
    def test_execute_followup_call_not_found(self, mock_scheduler_class):
        """Test execution when call item not found"""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        mock_scheduler.get_call.return_value = None
        
        result = execute_followup_call("nonexistent-call")
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
    
    @patch('scheduling.tasks.CallScheduler')
    @patch('scheduling.tasks.execute_livekit_call')
    def test_execute_followup_call_max_attempts_exceeded(self, mock_execute_call, mock_scheduler_class):
        """Test when maximum retry attempts are exceeded"""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        call_item = CallScheduleItem(
            id="test-call-123",
            patient_id="patient-456",
            patient_phone="+1234567890",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Test call",
            metadata={"attempt_count": 3}  # Already at max attempts
        )
        mock_scheduler.get_call.return_value = call_item
        
        # Mock failed call execution
        mock_execute_call.return_value = (False, {
            "error": "Still busy",
            "sip_status_code": "486",
            "retryable": True
        })
        
        result = execute_followup_call("test-call-123")
        
        # Should not retry due to max attempts
        assert result["success"] is False
        assert result["should_retry"] is False
        
        mock_scheduler.update_call_status.assert_called_with(
            "test-call-123",
            CallStatus.PERMANENTLY_FAILED,
            "Maximum retry attempts exceeded"
        )


class TestProcessPendingCalls:
    """Tests for process_pending_calls task"""
    
    @patch('scheduling.tasks.Queue')
    @patch('scheduling.tasks.CallScheduler')
    def test_process_pending_calls_success(self, mock_scheduler_class, mock_queue_class):
        """Test processing pending calls successfully"""
        # Setup mocks
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        mock_queue = Mock()
        mock_queue_class.return_value = mock_queue
        
        # Mock pending calls
        call1 = CallScheduleItem(
            id="call1",
            patient_id="patient1",
            patient_phone="+1111111111",
            scheduled_time=datetime.now() - timedelta(minutes=5),  # Due
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Call 1"
        )
        call2 = CallScheduleItem(
            id="call2",
            patient_id="patient2",
            patient_phone="+2222222222",
            scheduled_time=datetime.now() - timedelta(minutes=10),  # Due
            call_type=CallType.DISCHARGE_REMINDER,
            priority=2,
            llm_prompt="Call 2"
        )
        
        mock_scheduler.get_pending_calls.return_value = [call1, call2]
        
        # Mock job creation
        mock_job1 = Mock()
        mock_job1.id = "job1"
        mock_job2 = Mock()
        mock_job2.id = "job2"
        mock_queue.enqueue.side_effect = [mock_job1, mock_job2]
        
        # Execute task
        result = process_pending_calls()
        
        # Verify result
        assert result["processed_calls"] == 2
        assert len(result["queued_jobs"]) == 2
        
        # Verify calls were queued
        assert mock_queue.enqueue.call_count == 2
        
        # Verify scheduler was called
        mock_scheduler.get_pending_calls.assert_called_once_with(limit=50)
    
    @patch('scheduling.tasks.Queue')
    @patch('scheduling.tasks.CallScheduler')
    def test_process_pending_calls_no_calls(self, mock_scheduler_class, mock_queue_class):
        """Test processing when no pending calls"""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        mock_scheduler.get_pending_calls.return_value = []
        
        result = process_pending_calls()
        
        assert result["processed_calls"] == 0
        assert len(result["queued_jobs"]) == 0
    
    @patch('scheduling.tasks.Queue')
    @patch('scheduling.tasks.CallScheduler')
    def test_process_pending_calls_queue_failure(self, mock_scheduler_class, mock_queue_class):
        """Test handling queue failures"""
        # Setup mocks
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        mock_queue = Mock()
        mock_queue_class.return_value = mock_queue
        mock_queue.enqueue.side_effect = Exception("Queue failure")
        
        # Mock pending call
        call1 = CallScheduleItem(
            id="call1",
            patient_id="patient1",
            patient_phone="+1111111111",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Call 1"
        )
        mock_scheduler.get_pending_calls.return_value = [call1]
        
        # Execute task
        result = process_pending_calls()
        
        # Should handle failure gracefully
        assert result["processed_calls"] == 0
        assert len(result["failed_calls"]) == 1
        assert result["failed_calls"][0]["call_id"] == "call1"
        
        # Verify call status was updated to failed
        mock_scheduler.update_call_status.assert_called_with(
            "call1",
            CallStatus.FAILED,
            "Failed to queue: Queue failure"
        )


class TestGeneratePatientCalls:
    """Tests for generate_patient_calls task"""
    
    @patch('scheduling.tasks.CallScheduler')
    def test_generate_patient_calls_success(self, mock_scheduler_class):
        """Test successful patient call generation"""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        # Mock generated calls
        generated_calls = [
            CallScheduleItem(
                id="call1",
                patient_id="patient-123",
                patient_phone="+1234567890",
                scheduled_time=datetime.now() + timedelta(hours=24),
                call_type=CallType.DISCHARGE_REMINDER,
                priority=1,
                llm_prompt="Reminder about discharge instructions"
            ),
            CallScheduleItem(
                id="call2",
                patient_id="patient-123",
                patient_phone="+1234567890",
                scheduled_time=datetime.now() + timedelta(hours=48),
                call_type=CallType.WELLNESS_CHECK,
                priority=2,
                llm_prompt="General wellness check"
            )
        ]
        
        mock_scheduler.generate_calls_for_patient.return_value = generated_calls
        mock_scheduler.schedule_call.return_value = True
        
        # Execute task
        result = generate_patient_calls(
            patient_id="patient-123",
            patient_phone="+1234567890",
            patient_name="John Doe",
            discharge_time=datetime.now(),
            selected_order_ids=["order1", "order2"]
        )
        
        # Verify result
        assert result["success"] is True
        assert result["patient_id"] == "patient-123"
        assert result["calls_generated"] == 2
        assert result["calls_scheduled"] == 2
        
        # Verify scheduler was called correctly
        mock_scheduler.generate_calls_for_patient.assert_called_once_with(
            patient_id="patient-123",
            patient_phone="+1234567890",
            patient_name="John Doe",
            discharge_time=datetime.now(),
            selected_order_ids=["order1", "order2"]
        )
        
        # Verify each call was scheduled
        assert mock_scheduler.schedule_call.call_count == 2
    
    @patch('scheduling.tasks.CallScheduler')
    def test_generate_patient_calls_schedule_failure(self, mock_scheduler_class):
        """Test handling scheduling failures"""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        
        # Mock generated calls
        call1 = CallScheduleItem(
            id="call1",
            patient_id="patient-123",
            patient_phone="+1234567890",
            scheduled_time=datetime.now() + timedelta(hours=24),
            call_type=CallType.DISCHARGE_REMINDER,
            priority=1,
            llm_prompt="Test call 1"
        )
        call2 = CallScheduleItem(
            id="call2",
            patient_id="patient-123",
            patient_phone="+1234567890",
            scheduled_time=datetime.now() + timedelta(hours=48),
            call_type=CallType.WELLNESS_CHECK,
            priority=2,
            llm_prompt="Test call 2"
        )
        
        mock_scheduler.generate_calls_for_patient.return_value = [call1, call2]
        
        # Mock schedule_call to fail for second call
        mock_scheduler.schedule_call.side_effect = [True, False]
        
        # Execute task
        result = generate_patient_calls(
            patient_id="patient-123",
            patient_phone="+1234567890", 
            patient_name="John Doe",
            discharge_time=datetime.now(),
            selected_order_ids=["order1"]
        )
        
        # Verify partial success
        assert result["success"] is True  # At least one call succeeded
        assert result["calls_generated"] == 2
        assert result["calls_scheduled"] == 1
        assert len(result["failed_calls"]) == 1
        assert result["failed_calls"][0] == "call2"
    
    @patch('scheduling.tasks.CallScheduler')
    def test_generate_patient_calls_no_calls_generated(self, mock_scheduler_class):
        """Test when no calls are generated"""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler
        mock_scheduler.generate_calls_for_patient.return_value = []
        
        result = generate_patient_calls(
            patient_id="patient-123",
            patient_phone="+1234567890",
            patient_name="John Doe", 
            discharge_time=datetime.now(),
            selected_order_ids=[]
        )
        
        assert result["success"] is True
        assert result["calls_generated"] == 0
        assert result["calls_scheduled"] == 0