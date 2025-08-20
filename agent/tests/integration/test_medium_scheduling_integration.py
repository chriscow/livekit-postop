"""
Medium Integration Tests for Scheduling System

Tests that the scheduling system, call queue, and Redis work together properly.
This includes:
- Generating calls from discharge orders
- Scheduling calls in Redis  
- RQ task queue integration
- Call status tracking
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import redis
from freezegun import freeze_time

# Import our scheduling components
from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from scheduling.tasks import execute_followup_call, generate_patient_calls
from discharge.discharge_orders import get_selected_orders
from config.redis import create_redis_connection, get_redis_url


class TestSchedulingSystemIntegration:
    """Test integration between scheduler, Redis, and call queue"""
    
    def setup_method(self):
        """Set up test environment"""
        self.redis_client = create_redis_connection()
        # Clear any existing test data
        test_keys = self.redis_client.keys("test_call:*")
        if test_keys:
            self.redis_client.delete(*test_keys)
    
    def teardown_method(self):
        """Clean up test data"""
        test_keys = self.redis_client.keys("test_call:*")
        if test_keys:
            self.redis_client.delete(*test_keys)
    
    @pytest.mark.asyncio
    async def test_scheduler_redis_integration(self):
        """Test that scheduler can store and retrieve calls from Redis"""
        scheduler = CallScheduler()
        
        # Create a test call
        call_item = CallScheduleItem(
            id="test-call-001",
            patient_id="patient-123",
            patient_phone="+1234567890",
            scheduled_time=datetime.now() - timedelta(minutes=1),
            call_type=CallType.DISCHARGE_REMINDER,
            priority=2,
            llm_prompt="Test call about compression bandage removal.",
            related_discharge_order_id="vm_compression"
        )
        
        # Schedule the call
        success = scheduler.schedule_call(call_item)
        assert success, "Call should be scheduled successfully"
        
        # Retrieve pending calls
        pending_calls = scheduler.get_pending_calls()
        assert len(pending_calls) >= 1, "Should have at least one pending call"
        
        # Find our test call
        test_call = next((c for c in pending_calls if c.id == "test-call-001"), None)
        assert test_call is not None, "Test call should be retrievable"
        assert test_call.patient_phone == "+1234567890"
        assert test_call.call_type == CallType.DISCHARGE_REMINDER
        
        print(f"✅ Scheduler-Redis integration test passed - scheduled and retrieved call")
    
    @pytest.mark.asyncio  
    async def test_call_generation_from_discharge_orders(self):
        """Test generating calls from discharge orders"""
        scheduler = CallScheduler()
        
        # Use a fixed time for predictable scheduling
        with freeze_time("2025-01-15 10:00:00"):
            discharge_time = datetime(2025, 1, 15, 10, 0, 0)
            
            # Generate calls for selected discharge orders
            calls = scheduler.generate_calls_for_patient(
                patient_id="patient-456",
                patient_phone="+1987654321",
                patient_name="Jane Smith",
                discharge_time=discharge_time,
                selected_order_ids=["vm_compression", "vm_activity", "vm_medication"]
            )
            
            assert len(calls) >= 3, "Should generate calls for timing-dependent orders"
            
            # Verify call details
            compression_call = next((c for c in calls if c.discharge_order_id == "vm_compression"), None)
            assert compression_call is not None
            assert compression_call.call_type == CallType.DISCHARGE_REMINDER
            assert "compression bandage" in compression_call.llm_prompt.lower()
            
            # Verify timing
            expected_time = discharge_time + timedelta(hours=24)  # 24_hours_after_discharge
            assert compression_call.scheduled_time == expected_time
            
            print(f"✅ Call generation test passed - created {len(calls)} calls from discharge orders")
    
    @pytest.mark.asyncio
    async def test_call_status_tracking(self):
        """Test call status updates and tracking"""
        scheduler = CallScheduler()
        
        # Create and schedule a call
        call_item = CallScheduleItem(
            id="status-test-001",
            patient_id="patient-789",
            patient_phone="+1555123456", 
            scheduled_time=datetime.now() - timedelta(minutes=1),  # Due now
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="General wellness check call."
        )
        
        scheduler.schedule_call(call_item)
        
        # Update call status to in-progress
        success = scheduler.update_call_status(
            call_item.id, 
            CallStatus.IN_PROGRESS, 
            "Call execution started"
        )
        assert success, "Should update call status successfully"
        
        # Retrieve and verify status
        pending_calls = scheduler.get_pending_calls()
        test_call = next((c for c in pending_calls if c.id == "status-test-001"), None)
        assert test_call is not None
        assert test_call.status == CallStatus.IN_PROGRESS
        
        # Update to completed
        scheduler.update_call_status(
            call_item.id,
            CallStatus.COMPLETED,
            "Call completed successfully"  
        )
        
        # Should no longer be in pending calls
        pending_calls = scheduler.get_pending_calls()
        test_call = next((c for c in pending_calls if c.id == "status-test-001"), None)
        assert test_call is None, "Completed call should not be in pending calls"
        
        print("✅ Call status tracking test passed")
    
    @pytest.mark.asyncio
    async def test_due_calls_identification(self):
        """Test identifying calls that are due for execution"""
        scheduler = CallScheduler()
        
        now = datetime.now()
        
        # Create calls with different timing
        calls = [
            CallScheduleItem(
                id="past-due-001",
                patient_id="patient-001",
                patient_phone="+1111111111",
                patient_name="Past Due",
                scheduled_time=now - timedelta(hours=1),  # Past due
                call_type=CallType.DISCHARGE_REMINDER,
                priority=1,
                llm_prompt="Past due call"
            ),
            CallScheduleItem(
                id="due-now-001", 
                patient_id="patient-002",
                patient_phone="+1222222222",
                patient_name="Due Now",
                scheduled_time=now - timedelta(minutes=1),  # Due now
                call_type=CallType.MEDICATION_REMINDER,
                priority=2,
                llm_prompt="Due now call"
            ),
            CallScheduleItem(
                id="future-001",
                patient_id="patient-003", 
                patient_phone="+1333333333",
                patient_name="Future",
                scheduled_time=now + timedelta(hours=1),  # Future
                call_type=CallType.WELLNESS_CHECK,
                priority=3,
                llm_prompt="Future call"
            )
        ]
        
        # Schedule all calls
        for call in calls:
            scheduler.schedule_call(call)
        
        # Get due calls
        due_calls = scheduler.get_pending_calls()
        due_call_ids = [c.id for c in due_calls]
        
        assert "past-due-001" in due_call_ids, "Past due call should be included"
        assert "due-now-001" in due_call_ids, "Due now call should be included"
        assert "future-001" not in due_call_ids, "Future call should not be included"
        
        print(f"✅ Due calls identification test passed - found {len(due_calls)} due calls")


class TestRQTaskIntegration:
    """Test RQ task integration with mocked call execution"""
    
    @pytest.mark.asyncio
    async def test_execute_followup_call_task_success(self):
        """Test the execute_followup_call task with mocked call executor"""
        
        # Create test call record
        call_item = CallScheduleItem(
            id="rq-test-001",
            patient_id="patient-rq-001",
            patient_phone="+1999888777",
            patient_name="RQ Test Patient",
            scheduled_time=datetime.now(),
            call_type=CallType.DISCHARGE_REMINDER,
            priority=1,
            llm_prompt="Test RQ call execution"
        )
        
        call_record = CallRecord(
            call_schedule_item_id=call_item.id,
            status=CallStatus.PENDING,
            created_at=datetime.now(),
            scheduled_time=call_item.scheduled_time,
            attempt_count=0
        )
        
        # Mock the call executor to simulate success
        with patch('scheduling.tasks.execute_livekit_call') as mock_executor:
            mock_executor.return_value = (True, {
                'room_name': 'test-room-001',
                'participant_identity': 'patient',
                'call_duration': 120
            })
            
            # Execute the task
            result = execute_followup_call(
                call_item_dict=call_item.to_dict(),
                call_record_dict=call_record.to_dict()
            )
            
            assert result['success'] is True
            assert result['call_id'] == call_item.id
            assert 'room_name' in result
            
            # Verify mock was called
            mock_executor.assert_called_once()
            
            print("✅ RQ task success test passed")
    
    @pytest.mark.asyncio
    async def test_execute_followup_call_task_failure(self):
        """Test the execute_followup_call task with failure handling"""
        
        call_item = CallScheduleItem(
            id="rq-test-failure-001",
            patient_id="patient-rq-002",
            patient_phone="+1888777666",
            patient_name="RQ Failure Test",
            scheduled_time=datetime.now(),
            call_type=CallType.MEDICATION_REMINDER,
            priority=2,
            llm_prompt="Test RQ call failure"
        )
        
        call_record = CallRecord(
            call_schedule_item_id=call_item.id,
            status=CallStatus.PENDING,
            created_at=datetime.now(),
            scheduled_time=call_item.scheduled_time,
            attempt_count=0
        )
        
        # Mock the call executor to simulate failure
        with patch('scheduling.tasks.execute_livekit_call') as mock_executor:
            mock_executor.return_value = (False, {
                'error': 'SIP trunk unavailable',
                'sip_status_code': '503',
                'retryable': True
            })
            
            # Execute the task
            result = execute_followup_call(
                call_item_dict=call_item.to_dict(),
                call_record_dict=call_record.to_dict()
            )
            
            assert result['success'] is False
            assert result['call_id'] == call_item.id
            assert 'error' in result
            assert result['retryable'] is True
            
            print("✅ RQ task failure test passed")
    
    def test_generate_patient_calls_task(self):
        """Test the generate_patient_calls RQ task"""
        
        # Mock the scheduler to avoid Redis dependency in this test
        with patch('scheduling.tasks.CallScheduler') as mock_scheduler_class:
            mock_scheduler = Mock()
            mock_scheduler_class.return_value = mock_scheduler
            
            # Mock generated calls
            mock_calls = [
                CallScheduleItem(
                    id="gen-001",
                    patient_id="patient-gen-001",
                    patient_phone="+1777666555",
                    patient_name="Generated Test",
                    scheduled_time=datetime.now() + timedelta(hours=24),
                    call_type=CallType.DISCHARGE_REMINDER,
                    priority=1,
                    llm_prompt="Generated call 1"
                ),
                CallScheduleItem(
                    id="gen-002", 
                    patient_id="patient-gen-001",
                    patient_phone="+1777666555",
                    patient_name="Generated Test",
                    scheduled_time=datetime.now() + timedelta(hours=48),
                    call_type=CallType.WELLNESS_CHECK,
                    priority=2,
                    llm_prompt="Generated call 2"
                )
            ]
            
            mock_scheduler.generate_calls_for_patient.return_value = mock_calls
            mock_scheduler.schedule_call.return_value = True
            
            # Execute the task
            result = generate_patient_calls(
                patient_id="patient-gen-001",
                patient_phone="+1777666555", 
                patient_name="Generated Test",
                discharge_time_iso="2025-01-15T10:00:00",
                selected_order_ids=["vm_compression", "vm_activity"]
            )
            
            assert result['success'] is True
            assert result['calls_scheduled'] == 2
            assert result['patient_id'] == "patient-gen-001"
            
            # Verify scheduler methods were called
            mock_scheduler.generate_calls_for_patient.assert_called_once()
            assert mock_scheduler.schedule_call.call_count == 2
            
            print("✅ Generate patient calls task test passed")


@pytest.mark.asyncio
async def test_medium_integration_end_to_end():
    """
    Medium complexity end-to-end integration test
    
    Tests: discharge orders → call generation → scheduling → status tracking
    """
    print("\n🔄 Running medium integration test...")
    
    # Setup Redis connection for testing
    redis_client = create_redis_connection()
    test_prefix = "medium_test:"
    
    try:
        # Step 1: Create scheduler
        scheduler = CallScheduler()
        print("✅ Step 1: Created scheduler with Redis connection")
        
        # Step 2: Generate calls from real discharge orders
        with freeze_time("2025-01-15 14:00:00"):
            discharge_time = datetime(2025, 1, 15, 14, 0, 0)
            
            # Get actual selected discharge orders
            selected_orders = get_selected_orders()
            timing_dependent_orders = [order.id for order in selected_orders if order.generates_calls]
            
            calls = scheduler.generate_calls_for_patient(
                patient_id="integration-test-patient",
                patient_phone="+1555999888",
                patient_name="Integration Test Patient", 
                discharge_time=discharge_time,
                selected_order_ids=timing_dependent_orders[:3]  # Limit to first 3
            )
            
            assert len(calls) > 0, "Should generate calls from discharge orders"
            print(f"✅ Step 2: Generated {len(calls)} calls from discharge orders")
        
        # Step 3: Schedule all generated calls
        scheduled_count = 0
        for call in calls:
            if scheduler.schedule_call(call):
                scheduled_count += 1
        
        assert scheduled_count == len(calls), "All calls should be scheduled"
        print(f"✅ Step 3: Scheduled {scheduled_count} calls in Redis")
        
        # Step 4: Retrieve and verify scheduled calls
        pending_calls = scheduler.get_pending_calls()
        test_calls = [c for c in pending_calls if c.patient_id == "integration-test-patient"]
        
        assert len(test_calls) == len(calls), "All test calls should be retrievable"
        print(f"✅ Step 4: Retrieved {len(test_calls)} pending calls")
        
        # Step 5: Test call status updates
        first_call = test_calls[0]
        scheduler.update_call_status(first_call.id, CallStatus.IN_PROGRESS, "Test execution")
        scheduler.update_call_status(first_call.id, CallStatus.COMPLETED, "Test completed")
        
        # Verify status update
        updated_pending = scheduler.get_pending_calls()
        updated_test_calls = [c for c in updated_pending if c.patient_id == "integration-test-patient"]
        
        assert len(updated_test_calls) == len(calls) - 1, "Completed call should be removed from pending"
        print("✅ Step 5: Call status tracking working correctly")
        
        # Step 6: Test due calls functionality
        due_calls = scheduler.get_pending_calls()
        print(f"✅ Step 6: Found {len(due_calls)} total due calls in system")
        
        print(f"\n🎉 Medium integration test PASSED!")
        print(f"   Calls generated: {len(calls)}")
        print(f"   Calls scheduled: {scheduled_count}")
        print(f"   Status tracking: ✅")
        print(f"   Redis integration: ✅")
        
    finally:
        # Cleanup test data (clean up any test calls)
        test_keys = redis_client.keys("call:*integration-test-patient*")
        if test_keys:
            redis_client.delete(*test_keys)
            print(f"🧹 Cleaned up {len(test_keys)} test keys")


if __name__ == "__main__":
    # Run medium integration test directly
    asyncio.run(test_medium_integration_end_to_end())