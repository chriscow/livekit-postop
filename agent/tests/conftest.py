"""
Pytest configuration and fixtures for PostOp AI scheduling tests
"""
import pytest
import redis
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from scheduling.scheduler import CallScheduler
from discharge.discharge_orders import DischargeOrder


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    return Mock(spec=redis.Redis)


@pytest.fixture
def call_scheduler(mock_redis):
    """CallScheduler instance with mocked Redis"""
    scheduler = CallScheduler()
    scheduler.redis_client = mock_redis
    return scheduler


@pytest.fixture
def sample_discharge_time():
    """Sample discharge time for testing"""
    return datetime(2025, 1, 15, 10, 0, 0)  # 10 AM on Jan 15, 2025


@pytest.fixture
def sample_call_item():
    """Sample CallScheduleItem for testing"""
    return CallScheduleItem(
        id="test-call-123",
        patient_id="patient-456",
        patient_phone="+1234567890",
        scheduled_time=datetime(2025, 1, 16, 14, 0, 0),  # 2 PM next day
        call_type=CallType.WELLNESS_CHECK,
        priority=3,
        llm_prompt="Test call prompt for patient wellness check",
        status=CallStatus.PENDING
    )


@pytest.fixture
def sample_call_record():
    """Sample CallRecord for testing"""
    return CallRecord(
        id="record-789",
        call_schedule_item_id="test-call-123",
        patient_id="patient-456",
        started_at=datetime(2025, 1, 16, 14, 0, 0),
        status=CallStatus.IN_PROGRESS
    )


@pytest.fixture
def sample_discharge_order():
    """Sample DischargeOrder with call template"""
    return DischargeOrder(
        id="test_order",
        label="Test Discharge Order",
        discharge_order="Test instructions for patient",
        generates_calls=True,
        call_template={
            "timing": "24_hours_after_discharge",
            "call_type": "discharge_reminder",
            "priority": 2,
            "prompt_template": "You are calling {patient_name} about {discharge_order}"
        }
    )


@pytest.fixture
def mock_livekit_api():
    """Mock LiveKit API for testing"""
    with patch('livekit.api.LiveKitAPI') as mock_api:
        mock_instance = Mock()
        mock_api.return_value = mock_instance
        
        # Mock dispatch creation
        mock_dispatch = Mock()
        mock_dispatch.id = "dispatch-123"
        mock_instance.agent_dispatch.create_dispatch.return_value = mock_dispatch
        
        # Mock SIP participant creation
        mock_participant = Mock()
        mock_participant.participant_id = "participant-456"
        mock_instance.sip.create_sip_participant.return_value = mock_participant
        
        # Mock aclose method
        mock_instance.aclose.return_value = None
        
        yield mock_instance


@pytest.fixture
def redis_test_db():
    """
    Real Redis connection for integration tests.
    Uses database 15 to avoid conflicts with development data.
    """
    try:
        client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
        client.ping()  # Test connection
        
        # Clear the test database before each test
        client.flushdb()
        
        yield client
        
        # Clean up after test
        client.flushdb()
        client.close()
        
    except redis.ConnectionError:
        pytest.skip("Redis not available for integration tests")


@pytest.fixture
def integration_scheduler(redis_test_db):
    """CallScheduler with real Redis for integration tests"""
    scheduler = CallScheduler()
    scheduler.redis_client = redis_test_db
    return scheduler