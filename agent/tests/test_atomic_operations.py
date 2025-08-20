"""
Test atomic Redis operations

Quick verification that the new atomic operations prevent race conditions
and handle timezone-aware datetime operations correctly.
"""
import pytest
from datetime import datetime, timedelta
from freezegun import freeze_time

from utils.time_utils import now_utc, parse_iso_to_utc, to_utc
from utils.redis_atomic import create_atomic_redis_ops
from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallStatus, CallType
from config.redis import create_redis_connection


class TestAtomicOperations:
    """Test atomic Redis operations"""
    
    def setup_method(self):
        """Set up test environment"""
        self.redis_client = create_redis_connection()
        self.atomic_ops = create_atomic_redis_ops(self.redis_client)
        
        # Clear test data
        test_keys = self.redis_client.keys("*atomic-test*")
        if test_keys:
            self.redis_client.delete(*test_keys)
    
    def teardown_method(self):
        """Clean up test data"""
        test_keys = self.redis_client.keys("*atomic-test*")
        if test_keys:
            self.redis_client.delete(*test_keys)
    
    def test_timezone_aware_scheduling(self):
        """Test that timezone-aware datetime handling works correctly"""
        with freeze_time("2025-01-15 14:30:00"):
            # Test UTC time handling
            utc_now = now_utc()
            assert utc_now.tzinfo is not None
            assert utc_now.tzinfo.utcoffset(None) == timedelta(0)
            
            # Test ISO parsing
            iso_string = "2025-01-15T14:30:00"
            parsed_dt = parse_iso_to_utc(iso_string)
            assert parsed_dt.tzinfo is not None
            
            # Test scheduling with timezone-aware times
            scheduler = CallScheduler()
            call_item = CallScheduleItem(
                id="atomic-test-001",
                patient_id="atomic-patient-001",
                patient_phone="+1555000111",
                scheduled_time=utc_now + timedelta(hours=1),
                call_type=CallType.DISCHARGE_REMINDER,
                priority=1,
                llm_prompt="Test timezone-aware scheduling"
            )
            
            success = scheduler.schedule_call(call_item)
            assert success
            
            # Verify stored time is correct
            stored_data = self.redis_client.hgetall("postop:scheduled_calls:atomic-test-001")
            assert stored_data
            stored_time = datetime.fromisoformat(stored_data['scheduled_time'])
            
            # Should match our UTC time
            expected_time = utc_now + timedelta(hours=1)
            assert abs((stored_time - expected_time).total_seconds()) < 1
    
    def test_atomic_dequeue_prevents_race_conditions(self):
        """Test that atomic dequeue prevents multiple workers claiming same calls"""
        scheduler = CallScheduler()
        
        with freeze_time("2025-01-15 15:00:00"):
            current_time = now_utc()
            
            # Create calls that are due now
            calls = []
            for i in range(3):
                call = CallScheduleItem(
                    id=f"atomic-race-test-{i:03d}",
                    patient_id=f"race-patient-{i:03d}",
                    patient_phone=f"+155500{i:04d}",
                    scheduled_time=current_time - timedelta(minutes=5),  # Due 5 minutes ago
                    call_type=CallType.WELLNESS_CHECK,
                    priority=1,
                    llm_prompt=f"Race condition test call {i}"
                )
                calls.append(call)
                
                # Schedule normally (not atomic batch, to test race conditions)
                success = scheduler.schedule_call(call)
                assert success
            
            # Simulate two workers trying to claim calls simultaneously
            worker1_calls = scheduler.get_due_calls_atomic(limit=10)
            worker2_calls = scheduler.get_due_calls_atomic(limit=10)
            
            # Worker 1 should get all the calls, worker 2 should get none
            assert len(worker1_calls) == 3
            assert len(worker2_calls) == 0
            
            # Verify all calls are marked as in_progress
            for call in worker1_calls:
                stored_data = self.redis_client.hgetall(f"postop:scheduled_calls:{call.id}")
                assert stored_data['status'] == 'in_progress'
    
    def test_batch_scheduling_atomicity(self):
        """Test that batch scheduling is atomic - all succeed or all fail"""
        scheduler = CallScheduler()
        
        with freeze_time("2025-01-15 16:00:00"):
            # Create batch of calls
            calls = []
            for i in range(5):
                call = CallScheduleItem(
                    id=f"batch-test-{i:03d}",
                    patient_id=f"batch-patient-{i:03d}",
                    patient_phone=f"+155511{i:04d}",
                    scheduled_time=now_utc() + timedelta(hours=i+1),
                    call_type=CallType.MEDICATION_REMINDER,
                    priority=2,
                    llm_prompt=f"Batch test call {i}"
                )
                calls.append(call)
            
            # Schedule all calls atomically
            scheduled_count = scheduler.batch_schedule_calls(calls)
            assert scheduled_count == 5
            
            # Verify all calls were stored
            for call in calls:
                stored_data = self.redis_client.hgetall(f"postop:scheduled_calls:{call.id}")
                assert stored_data
                assert stored_data['patient_id'] == call.patient_id
                assert stored_data['status'] == CallStatus.PENDING.value
                
                # Verify in time index
                score = self.redis_client.zscore("postop:scheduled_calls:by_time", call.id)
                assert score is not None
                
                # Verify in patient index
                patient_calls = self.redis_client.smembers(f"postop:scheduled_calls:patient:{call.patient_id}")
                assert call.id in patient_calls
    
    def test_conditional_status_update(self):
        """Test that status updates only succeed when current status matches expected"""
        scheduler = CallScheduler()
        
        # Create and schedule a call
        call = CallScheduleItem(
            id="status-test-001",
            patient_id="status-patient-001",
            patient_phone="+1555222333",
            scheduled_time=now_utc() + timedelta(hours=1),
            call_type=CallType.DISCHARGE_REMINDER,
            priority=1,
            llm_prompt="Status update test"
        )
        
        scheduler.schedule_call(call)
        
        # Try to update from PENDING to IN_PROGRESS (should succeed)
        success = scheduler.update_call_status_atomic(
            call.id, 
            CallStatus.PENDING, 
            CallStatus.IN_PROGRESS,
            "Starting execution"
        )
        assert success
        
        # Verify status was updated
        stored_data = self.redis_client.hgetall("postop:scheduled_calls:status-test-001")
        assert stored_data['status'] == CallStatus.IN_PROGRESS.value
        
        # Try to update from PENDING to COMPLETED (should fail - status is now IN_PROGRESS)
        success = scheduler.update_call_status_atomic(
            call.id,
            CallStatus.PENDING,
            CallStatus.COMPLETED,
            "Trying to complete from wrong status"
        )
        assert not success
        
        # Status should remain IN_PROGRESS
        stored_data = self.redis_client.hgetall("postop:scheduled_calls:status-test-001")
        assert stored_data['status'] == CallStatus.IN_PROGRESS.value
        
        # Try correct status transition (should succeed)
        success = scheduler.update_call_status_atomic(
            call.id,
            CallStatus.IN_PROGRESS,
            CallStatus.COMPLETED,
            "Completed successfully"
        )
        assert success
        
        stored_data = self.redis_client.hgetall("postop:scheduled_calls:status-test-001")
        assert stored_data['status'] == CallStatus.COMPLETED.value
        assert stored_data['notes'] == "Completed successfully"


class TestTimeUtils:
    """Test timezone utility functions"""
    
    def test_utc_handling(self):
        """Test UTC datetime handling"""
        with freeze_time("2025-01-15 12:00:00"):
            utc_time = now_utc()
            
            # Should be timezone-aware
            assert utc_time.tzinfo is not None
            assert utc_time.tzinfo.utcoffset(None) == timedelta(0)
            
            # Should match frozen time
            expected = datetime(2025, 1, 15, 12, 0, 0, tzinfo=utc_time.tzinfo)
            assert utc_time == expected
    
    def test_iso_parsing_with_timezone(self):
        """Test parsing ISO strings with different timezone formats"""
        # Test naive ISO string (should assume UTC)
        naive_iso = "2025-01-15T14:30:00"
        parsed = parse_iso_to_utc(naive_iso)
        assert parsed.tzinfo is not None
        
        # Test ISO string with UTC timezone
        utc_iso = "2025-01-15T14:30:00+00:00"
        parsed_utc = parse_iso_to_utc(utc_iso)
        assert parsed_utc.tzinfo is not None
        
        # Test ISO string with EST timezone
        est_iso = "2025-01-15T09:30:00-05:00"
        parsed_est = parse_iso_to_utc(est_iso)
        
        # Should convert to UTC (14:30 UTC)
        expected_utc = datetime(2025, 1, 15, 14, 30, 0)
        assert parsed_est.replace(tzinfo=None) == expected_utc
    
    def test_business_hours_adjustment(self):
        """Test business hours adjustment functionality"""
        from utils.time_utils import add_business_hours_offset
        
        # Test scheduling outside business hours gets moved to business hours
        base_time = datetime(2025, 1, 15, 23, 0, 0)  # 11 PM
        
        # Add 1 hour (would be midnight) - should move to 9 AM next day
        adjusted = add_business_hours_offset(
            base_time, 
            offset_hours=1,
            patient_timezone='US/Eastern'
        )
        
        # Should be moved to business hours
        assert adjusted.hour >= 9  # Should be at least 9 AM in some timezone
        assert adjusted.hour < 17   # Should be before 5 PM


if __name__ == "__main__":
    # Run basic atomic operations test
    test_ops = TestAtomicOperations()
    test_ops.setup_method()
    
    try:
        test_ops.test_timezone_aware_scheduling()
        print("✅ Timezone-aware scheduling test passed")
        
        test_ops.test_atomic_dequeue_prevents_race_conditions() 
        print("✅ Atomic dequeue race condition test passed")
        
        test_ops.test_batch_scheduling_atomicity()
        print("✅ Batch scheduling atomicity test passed")
        
        test_ops.test_conditional_status_update()
        print("✅ Conditional status update test passed")
        
        print("\n🎉 All atomic operations tests passed!")
        
    finally:
        test_ops.teardown_method()