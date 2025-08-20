"""
Simplified Medium Integration Tests

Focus on core scheduling functionality without complex call generation.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import redis

# Import core components
from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallStatus, CallType
from scheduling.tasks import generate_patient_calls
from config.redis import create_redis_connection


@pytest.mark.asyncio
async def test_simplified_medium_integration():
    """
    Simplified medium integration test
    
    Tests: basic scheduling → Redis storage → retrieval
    """
    print("\n🔄 Running simplified medium integration test...")
    
    try:
        # Step 1: Create scheduler
        scheduler = CallScheduler()
        print("✅ Step 1: Created scheduler")
        
        # Step 2: Create a simple call manually (avoid complex generation for now)
        call_item = CallScheduleItem(
            id="simple-test-001",
            patient_id="simple-patient-001",
            patient_phone="+1555444333",
            scheduled_time=datetime.now() - timedelta(minutes=1),
            call_type=CallType.DISCHARGE_REMINDER,
            priority=1,
            llm_prompt="This is a simple test call for integration testing.",
            status=CallStatus.PENDING
        )
        print("✅ Step 2: Created test call item")
        
        # Step 3: Schedule the call
        success = scheduler.schedule_call(call_item)
        assert success, "Call should be scheduled successfully"
        print("✅ Step 3: Scheduled call in Redis")
        
        # Step 4: Retrieve pending calls
        pending_calls = scheduler.get_pending_calls()
        test_calls = [c for c in pending_calls if c.patient_id == "simple-patient-001"]
        
        assert len(test_calls) >= 1, "Should retrieve at least one test call"
        retrieved_call = test_calls[0]
        assert retrieved_call.patient_phone == "+1555444333"
        assert retrieved_call.call_type == CallType.DISCHARGE_REMINDER
        print(f"✅ Step 4: Retrieved {len(test_calls)} calls from Redis")
        
        # Step 5: Test status update
        update_success = scheduler.update_call_status(
            call_item.id,
            CallStatus.COMPLETED,
            "Test completed successfully"
        )
        assert update_success, "Status update should succeed"
        print("✅ Step 5: Updated call status")
        
        # Step 6: Test RQ task with mocking
        with patch('scheduling.tasks.CallScheduler') as mock_scheduler_class:
            mock_scheduler = Mock()
            mock_scheduler_class.return_value = mock_scheduler
            
            # Mock successful call generation
            mock_calls = [call_item]
            mock_scheduler.generate_calls_for_patient.return_value = mock_calls
            mock_scheduler.schedule_call.return_value = True
            
            # Test the generate_patient_calls task
            result = generate_patient_calls(
                patient_id="task-test-patient",
                patient_phone="+1888777666",
                patient_name="Task Test Patient",
                discharge_time_iso=datetime.now().isoformat(),
                selected_order_ids=["vm_compression"]
            )
            
            assert isinstance(result, str), f"Result should be a string, got {type(result)}"
            assert "generated and scheduled" in result.lower() or "scheduled" in result.lower()
            print(f"✅ Step 6: RQ task integration test passed - {result}")
        
        # Step 7: Test Redis connection
        redis_client = create_redis_connection()
        redis_client.ping()
        print("✅ Step 7: Redis connection verified")
        
        print(f"\n🎉 Simplified medium integration test PASSED!")
        print(f"   Call scheduling: ✅")
        print(f"   Redis storage: ✅")
        print(f"   Status tracking: ✅")
        print(f"   RQ task mocking: ✅")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        raise
    
    finally:
        # Cleanup
        try:
            redis_client = create_redis_connection()
            test_keys = redis_client.keys("call:*simple-patient-001*")
            if test_keys:
                redis_client.delete(*test_keys)
                print(f"🧹 Cleaned up {len(test_keys)} test keys")
        except:
            pass


class TestSchedulingComponents:
    """Test individual scheduling components"""
    
    def test_call_schedule_item_serialization(self):
        """Test CallScheduleItem to_dict and from_dict"""
        # Create a call item with all fields
        original_call = CallScheduleItem(
            id="test-serialization-001",
            patient_id="patient-serial-001", 
            patient_phone="+1234567890",
            scheduled_time=datetime(2025, 1, 15, 14, 30, 0),
            call_type=CallType.MEDICATION_REMINDER,
            priority=2,
            llm_prompt="Test serialization prompt",
            status=CallStatus.PENDING,
            max_attempts=3,
            attempt_count=0,
            related_discharge_order_id="vm_medication",
            metadata={"test": True, "number": 42},
            notes="Test notes",
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 5, 0)
        )
        
        # Serialize to dict
        call_dict = original_call.to_dict()
        assert isinstance(call_dict, dict)
        assert call_dict['id'] == "test-serialization-001"
        assert call_dict['call_type'] == CallType.MEDICATION_REMINDER.value
        assert call_dict['patient_phone'] == "+1234567890"
        
        # Deserialize back
        recreated_call = CallScheduleItem.from_dict(call_dict)
        assert recreated_call.id == original_call.id
        assert recreated_call.patient_id == original_call.patient_id
        assert recreated_call.call_type == original_call.call_type
        assert recreated_call.scheduled_time == original_call.scheduled_time
        assert recreated_call.metadata == original_call.metadata
        
        print("✅ CallScheduleItem serialization test passed")
    
    def test_redis_connection(self):
        """Test Redis connection and basic operations"""
        redis_client = create_redis_connection()
        
        # Test ping
        redis_client.ping()
        
        # Test basic set/get
        test_key = "integration_test:redis_check"
        test_value = "redis_working"
        
        redis_client.set(test_key, test_value)
        retrieved_value = redis_client.get(test_key)
        
        assert retrieved_value == test_value
        
        # Cleanup
        redis_client.delete(test_key)
        
        print("✅ Redis connection test passed")
    
    def test_scheduler_initialization(self):
        """Test that CallScheduler can be initialized"""
        scheduler = CallScheduler()
        
        # Test that it has the expected attributes
        assert hasattr(scheduler, 'redis_client')
        assert hasattr(scheduler, 'calls_key')
        
        # Test that Redis connection works
        scheduler.redis_client.ping()
        
        print("✅ Scheduler initialization test passed")


if __name__ == "__main__":
    # Run simplified integration test
    asyncio.run(test_simplified_medium_integration())