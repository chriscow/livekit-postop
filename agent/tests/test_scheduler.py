"""
Tests for CallScheduler functionality
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from discharge.discharge_orders import DischargeOrder


class TestCallScheduler:
    """Tests for CallScheduler class"""
    
    def test_init(self, mock_redis):
        """Test CallScheduler initialization"""
        scheduler = CallScheduler(redis_host="test-host", redis_port=1234)
        assert scheduler.calls_key == "postop:scheduled_calls"
        assert scheduler.records_key == "postop:call_records"
    
    def test_parse_timing_spec_hours_after_discharge(self, call_scheduler, sample_discharge_time):
        """Test parsing 'X_hours_after_discharge' timing specs"""
        # Test 24 hours after discharge
        times = call_scheduler.parse_timing_spec("24_hours_after_discharge", sample_discharge_time)
        expected = sample_discharge_time + timedelta(hours=24)
        assert len(times) == 1
        assert times[0] == expected
        
        # Test 48 hours after discharge
        times = call_scheduler.parse_timing_spec("48_hours_after_discharge", sample_discharge_time)
        expected = sample_discharge_time + timedelta(hours=48)
        assert len(times) == 1
        assert times[0] == expected
    
    def test_parse_timing_spec_daily(self, call_scheduler, sample_discharge_time):
        """Test parsing 'daily_for_X_days_starting_Y_hours_after_discharge' timing specs"""
        # Test daily for 2 days starting 12 hours after discharge
        times = call_scheduler.parse_timing_spec(
            "daily_for_2_days_starting_12_hours_after_discharge", 
            sample_discharge_time
        )
        
        assert len(times) == 2
        
        # First call should be 12 hours after discharge
        expected_first = sample_discharge_time + timedelta(hours=12)
        assert times[0] == expected_first
        
        # Second call should be 36 hours after discharge (12 + 24)
        expected_second = sample_discharge_time + timedelta(hours=36)
        assert times[1] == expected_second
    
    def test_parse_timing_spec_day_before_date(self, call_scheduler, sample_discharge_time):
        """Test parsing 'day_before_date:YYYY-MM-DD' timing specs"""
        times = call_scheduler.parse_timing_spec(
            "day_before_date:2025-06-23", 
            sample_discharge_time
        )
        
        assert len(times) == 1
        # Should be 2 PM on June 22, 2025 (day before June 23)
        expected = datetime(2025, 6, 22, 14, 0, 0)
        assert times[0] == expected
    
    def test_parse_timing_spec_within_24_hours(self, call_scheduler, sample_discharge_time):
        """Test parsing 'within_24_hours' timing spec"""
        times = call_scheduler.parse_timing_spec("within_24_hours", sample_discharge_time)
        
        assert len(times) == 1
        # Should be 18 hours after discharge
        expected = sample_discharge_time + timedelta(hours=18)
        assert times[0] == expected
    
    def test_parse_timing_spec_unknown(self, call_scheduler, sample_discharge_time):
        """Test parsing unknown timing spec (should default to 24 hours)"""
        times = call_scheduler.parse_timing_spec("unknown_format", sample_discharge_time)
        
        assert len(times) == 1
        expected = sample_discharge_time + timedelta(hours=24)
        assert times[0] == expected
    
    @patch('discharge.discharge_orders.get_selected_orders')
    def test_generate_calls_from_order(self, mock_get_orders, call_scheduler, sample_discharge_time):
        """Test generating calls from a discharge order"""
        # Create test order with call template
        order = DischargeOrder(
            id="test_order",
            label="Test Order",
            discharge_order="Test instructions",
            generates_calls=True,
            call_template={
                "timing": "24_hours_after_discharge",
                "call_type": "discharge_reminder",
                "priority": 2,
                "prompt_template": "You are calling {patient_name} about {discharge_order}"
            }
        )
        
        calls = call_scheduler._generate_calls_from_order(
            order=order,
            patient_id="patient-123",
            patient_phone="+1234567890",
            patient_name="John Doe",
            discharge_time=sample_discharge_time
        )
        
        assert len(calls) == 1
        call = calls[0]
        
        assert call.patient_id == "patient-123"
        assert call.patient_phone == "+1234567890"
        assert call.call_type == CallType.DISCHARGE_REMINDER
        assert call.priority == 2
        assert call.related_discharge_order_id == "test_order"
        assert "John Doe" in call.llm_prompt
        assert "Test instructions" in call.llm_prompt
        
        # Check timing
        expected_time = sample_discharge_time + timedelta(hours=24)
        assert call.scheduled_time == expected_time
    
    def test_generate_wellness_check_call(self, call_scheduler, sample_discharge_time):
        """Test generating wellness check call"""
        call = call_scheduler._generate_wellness_check_call(
            patient_id="patient-123",
            patient_phone="+1234567890",
            patient_name="Jane Doe",
            discharge_time=sample_discharge_time
        )
        
        assert call.patient_id == "patient-123"
        assert call.patient_phone == "+1234567890"
        assert call.call_type == CallType.WELLNESS_CHECK
        assert call.priority == 3
        assert call.related_discharge_order_id is None
        assert "Jane Doe" in call.llm_prompt
        assert "wellness check" in call.llm_prompt.lower()
        
        # Should be scheduled 18 hours after discharge
        expected_time = sample_discharge_time + timedelta(hours=18)
        assert call.scheduled_time == expected_time
    
    def test_schedule_call(self, call_scheduler, sample_call_item):
        """Test scheduling a call in Redis"""
        # Mock Redis operations
        call_scheduler.redis_client.hset.return_value = True
        call_scheduler.redis_client.zadd.return_value = 1
        call_scheduler.redis_client.sadd.return_value = 1
        
        result = call_scheduler.schedule_call(sample_call_item)
        
        assert result is True
        
        # Verify Redis operations were called correctly
        call_scheduler.redis_client.hset.assert_called_once()
        call_scheduler.redis_client.zadd.assert_called_once()
        call_scheduler.redis_client.sadd.assert_called_once()
        
        # Check the hset call
        hset_args = call_scheduler.redis_client.hset.call_args
        assert f"postop:scheduled_calls:{sample_call_item.id}" in hset_args[0]
    
    def test_schedule_call_failure(self, call_scheduler, sample_call_item):
        """Test handling of Redis failures during call scheduling"""
        # Mock Redis to raise exception
        call_scheduler.redis_client.hset.side_effect = Exception("Redis error")
        
        result = call_scheduler.schedule_call(sample_call_item)
        
        assert result is False
    
    def test_get_pending_calls(self, call_scheduler):
        """Test retrieving pending calls"""
        # Mock Redis to return call IDs
        current_timestamp = datetime.now().timestamp()
        call_scheduler.redis_client.zrangebyscore.return_value = ["call-1", "call-2"]
        
        # Mock call data
        call_data_1 = {
            "id": "call-1",
            "patient_id": "patient-1",
            "patient_phone": "+1111111111",
            "scheduled_time": datetime(2025, 1, 15, 14, 0, 0).isoformat(),
            "call_type": "wellness_check",
            "priority": "3",
            "llm_prompt": "Test prompt 1",
            "status": "pending",
            "max_attempts": "3",
            "attempt_count": "0",
            "related_discharge_order_id": None,
            "metadata": "{}",
            "notes": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        call_data_2 = {
            "id": "call-2",
            "patient_id": "patient-2", 
            "patient_phone": "+2222222222",
            "scheduled_time": datetime(2025, 1, 15, 15, 0, 0).isoformat(),
            "call_type": "discharge_reminder",
            "priority": "2",
            "llm_prompt": "Test prompt 2",
            "status": "pending",
            "max_attempts": "3",
            "attempt_count": "0",
            "related_discharge_order_id": "order-123",
            "metadata": "{}",
            "notes": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        call_scheduler.redis_client.hgetall.side_effect = [call_data_1, call_data_2]
        
        pending_calls = call_scheduler.get_pending_calls(limit=10)
        
        assert len(pending_calls) == 2
        assert pending_calls[0].id == "call-1"
        assert pending_calls[1].id == "call-2"
        assert all(call.status == CallStatus.PENDING for call in pending_calls)
        
        # Verify Redis calls
        call_scheduler.redis_client.zrangebyscore.assert_called_once()
        assert call_scheduler.redis_client.hgetall.call_count == 2
    
    def test_update_call_status(self, call_scheduler):
        """Test updating call status"""
        # Mock existing call data
        existing_data = {
            "id": "call-123",
            "status": "pending",
            "notes": "",
            "updated_at": datetime(2025, 1, 15, 10, 0, 0).isoformat()
        }
        call_scheduler.redis_client.hgetall.return_value = existing_data
        call_scheduler.redis_client.hset.return_value = True
        
        result = call_scheduler.update_call_status(
            "call-123", 
            CallStatus.COMPLETED, 
            "Call completed successfully"
        )
        
        assert result is True
        
        # Verify Redis operations
        call_scheduler.redis_client.hgetall.assert_called_once_with("postop:scheduled_calls:call-123")
        call_scheduler.redis_client.hset.assert_called_once()
        
        # For completed status, should remove from scheduled index
        call_scheduler.redis_client.zrem.assert_called_once_with(
            "postop:scheduled_calls:by_time", 
            "call-123"
        )
    
    def test_save_call_record(self, call_scheduler, sample_call_record):
        """Test saving call record"""
        call_scheduler.redis_client.hset.return_value = True
        call_scheduler.redis_client.sadd.return_value = 1
        
        result = call_scheduler.save_call_record(sample_call_record)
        
        assert result is True
        
        # Verify Redis operations
        call_scheduler.redis_client.hset.assert_called_once()
        call_scheduler.redis_client.sadd.assert_called_once()
        
        # Check the record key
        hset_args = call_scheduler.redis_client.hset.call_args
        assert f"postop:call_records:{sample_call_record.id}" in hset_args[0]


class TestCallSchedulerIntegration:
    """Integration tests with real Redis (if available)"""
    
    @pytest.mark.integration
    def test_schedule_and_retrieve_call(self, integration_scheduler, sample_call_item):
        """Test scheduling a call and retrieving it"""
        # Schedule the call
        result = integration_scheduler.schedule_call(sample_call_item)
        assert result is True
        
        # Modify the scheduled time to make it "due"
        past_time = datetime.now() - timedelta(minutes=1)
        sample_call_item.scheduled_time = past_time
        integration_scheduler.schedule_call(sample_call_item)
        
        # Retrieve pending calls
        pending_calls = integration_scheduler.get_pending_calls()
        
        assert len(pending_calls) >= 1
        retrieved_call = next(call for call in pending_calls if call.id == sample_call_item.id)
        assert retrieved_call.patient_id == sample_call_item.patient_id
        assert retrieved_call.patient_phone == sample_call_item.patient_phone
    
    @pytest.mark.integration
    def test_call_status_workflow(self, integration_scheduler, sample_call_item):
        """Test complete call status workflow"""
        # Schedule call
        integration_scheduler.schedule_call(sample_call_item)
        
        # Update to in_progress
        result = integration_scheduler.update_call_status(
            sample_call_item.id, 
            CallStatus.IN_PROGRESS,
            "Call started"
        )
        assert result is True
        
        # Update to completed
        result = integration_scheduler.update_call_status(
            sample_call_item.id,
            CallStatus.COMPLETED, 
            "Call finished successfully"
        )
        assert result is True
        
        # Should no longer appear in pending calls
        pending_calls = integration_scheduler.get_pending_calls()
        call_ids = [call.id for call in pending_calls]
        assert sample_call_item.id not in call_ids