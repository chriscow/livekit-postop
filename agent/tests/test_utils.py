"""
Test utilities to reduce boilerplate and improve test maintainability
"""
import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock

from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from discharge.discharge_orders import DischargeOrder
from followup.livekit_adapter import MockLiveKitAdapter


class CallItemBuilder:
    """Builder pattern for creating test CallScheduleItems"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset to default values"""
        self._id = "test-call-123"
        self._patient_id = "patient-456"
        self._patient_phone = "+1234567890"
        self._scheduled_time = datetime.now() + timedelta(hours=1)
        self._call_type = CallType.WELLNESS_CHECK
        self._priority = 2
        self._llm_prompt = "Test call prompt"
        self._status = CallStatus.PENDING
        self._related_order_id = None
        self._metadata = {}
        return self
    
    def with_id(self, call_id: str):
        self._id = call_id
        return self
    
    def with_patient(self, patient_id: str, phone: str = None):
        self._patient_id = patient_id
        if phone:
            self._patient_phone = phone
        return self
    
    def with_phone(self, phone: str):
        self._patient_phone = phone
        return self
    
    def with_scheduled_time(self, scheduled_time: datetime):
        self._scheduled_time = scheduled_time
        return self
    
    def scheduled_in_past(self, minutes: int = 5):
        self._scheduled_time = datetime.now() - timedelta(minutes=minutes)
        return self
    
    def scheduled_in_future(self, hours: int = 1):
        self._scheduled_time = datetime.now() + timedelta(hours=hours)
        return self
    
    def with_call_type(self, call_type: CallType):
        self._call_type = call_type
        return self
    
    def as_discharge_reminder(self, order_id: str = "test-order"):
        self._call_type = CallType.DISCHARGE_REMINDER
        self._related_order_id = order_id
        return self
    
    def as_wellness_check(self):
        self._call_type = CallType.WELLNESS_CHECK
        return self
    
    def as_follow_up(self):
        self._call_type = CallType.FOLLOW_UP
        return self
    
    def with_priority(self, priority: int):
        self._priority = priority
        return self
    
    def with_prompt(self, prompt: str):
        self._llm_prompt = prompt
        return self
    
    def with_status(self, status: CallStatus):
        self._status = status
        return self
    
    def as_pending(self):
        self._status = CallStatus.PENDING
        return self
    
    def as_in_progress(self):
        self._status = CallStatus.IN_PROGRESS
        return self
    
    def as_completed(self):
        self._status = CallStatus.COMPLETED
        return self
    
    def as_failed(self):
        self._status = CallStatus.FAILED
        return self
    
    def with_metadata(self, **metadata):
        self._metadata.update(metadata)
        return self
    
    def with_attempt_count(self, count: int):
        self._metadata["attempt_count"] = count
        return self
    
    def build(self) -> CallScheduleItem:
        """Build the CallScheduleItem"""
        return CallScheduleItem(
            id=self._id,
            patient_id=self._patient_id,
            patient_phone=self._patient_phone,
            scheduled_time=self._scheduled_time,
            call_type=self._call_type,
            priority=self._priority,
            llm_prompt=self._llm_prompt,
            status=self._status,
            related_discharge_order_id=self._related_order_id,
            metadata=self._metadata
        )


class CallRecordBuilder:
    """Builder pattern for creating test CallRecords"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset to default values"""
        self._id = "record-789"
        self._call_schedule_item_id = "test-call-123"
        self._patient_id = "patient-456"
        self._started_at = datetime.now()
        self._ended_at = None
        self._status = CallStatus.IN_PROGRESS
        self._room_name = None
        self._participant_identity = None
        self._error_message = None
        self._metadata = {}
        return self
    
    def with_id(self, record_id: str):
        self._id = record_id
        return self
    
    def for_call(self, call_id: str, patient_id: str = None):
        self._call_schedule_item_id = call_id
        if patient_id:
            self._patient_id = patient_id
        return self
    
    def with_status(self, status: CallStatus):
        self._status = status
        return self
    
    def as_completed(self, ended_at: datetime = None):
        self._status = CallStatus.COMPLETED
        self._ended_at = ended_at or datetime.now()
        return self
    
    def as_failed(self, error: str = "Test error", ended_at: datetime = None):
        self._status = CallStatus.FAILED
        self._error_message = error
        self._ended_at = ended_at or datetime.now()
        return self
    
    def in_room(self, room_name: str, participant_identity: str = "patient"):
        self._room_name = room_name
        self._participant_identity = participant_identity
        return self
    
    def with_metadata(self, **metadata):
        self._metadata.update(metadata)
        return self
    
    def build(self) -> CallRecord:
        """Build the CallRecord"""
        return CallRecord(
            id=self._id,
            call_schedule_item_id=self._call_schedule_item_id,
            patient_id=self._patient_id,
            started_at=self._started_at,
            ended_at=self._ended_at,
            status=self._status,
            room_name=self._room_name,
            participant_identity=self._participant_identity,
            error_message=self._error_message,
            metadata=self._metadata
        )


class DischargeOrderBuilder:
    """Builder pattern for creating test DischargeOrders"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset to default values"""
        self._id = "test-order"
        self._label = "Test Discharge Order"
        self._discharge_order = "Test discharge instructions"
        self._generates_calls = True
        self._call_template = {
            "timing": "24_hours_after_discharge",
            "call_type": "discharge_reminder",
            "priority": 2,
            "prompt_template": "Test prompt template"
        }
        return self
    
    def with_id(self, order_id: str):
        self._id = order_id
        return self
    
    def with_label(self, label: str):
        self._label = label
        return self
    
    def with_instructions(self, instructions: str):
        self._discharge_order = instructions
        return self
    
    def generates_calls(self, generates: bool = True):
        self._generates_calls = generates
        return self
    
    def with_timing(self, timing: str):
        if self._call_template:
            self._call_template["timing"] = timing
        return self
    
    def with_call_template(self, **template):
        self._call_template = template
        return self
    
    def build(self) -> DischargeOrder:
        """Build the DischargeOrder"""
        return DischargeOrder(
            id=self._id,
            label=self._label,
            discharge_order=self._discharge_order,
            generates_calls=self._generates_calls,
            call_template=self._call_template
        )


class MockFactory:
    """Factory for creating common mocks"""
    
    @staticmethod
    def scheduler_mock():
        """Create a mock CallScheduler"""
        mock = Mock()
        mock.get_call.return_value = None
        mock.get_pending_calls.return_value = []
        mock.schedule_call.return_value = True
        mock.update_call_status.return_value = None
        mock.save_call_record.return_value = None
        mock.generate_calls_for_patient.return_value = []
        return mock
    
    @staticmethod
    def livekit_adapter_mock(should_fail: bool = False, sip_error: str = None):
        """Create a mock LiveKit adapter"""
        adapter = MockLiveKitAdapter()
        if should_fail:
            adapter.should_fail = True
            if sip_error:
                adapter.failure_sip_code = sip_error
        return adapter
    
    @staticmethod
    def agent_mock():
        """Create a mock agent for RAG testing"""
        mock = Mock()
        mock.session = Mock()
        mock.session.say = AsyncMock()
        mock.session.generate_reply = AsyncMock()
        mock._llm = Mock()
        mock._llm.complete = AsyncMock()
        return mock
    
    @staticmethod
    def run_context_mock(agent=None):
        """Create a mock RunContext"""
        mock = Mock()
        mock.agent = agent or MockFactory.agent_mock()
        mock.session = mock.agent.session
        return mock


class AssertionHelpers:
    """Helper methods for common test assertions"""
    
    @staticmethod
    def assert_call_item_equals(actual: CallScheduleItem, expected: CallScheduleItem):
        """Assert two CallScheduleItems are equal"""
        assert actual.id == expected.id
        assert actual.patient_id == expected.patient_id
        assert actual.patient_phone == expected.patient_phone
        assert actual.call_type == expected.call_type
        assert actual.priority == expected.priority
        assert actual.llm_prompt == expected.llm_prompt
        assert actual.status == expected.status
    
    @staticmethod
    def assert_call_record_updated_for_success(record: CallRecord, room_name: str):
        """Assert call record was updated for successful call"""
        assert record.room_name == room_name
        assert record.participant_identity == "patient"
        assert record.status == CallStatus.IN_PROGRESS
        assert record.started_at is not None
    
    @staticmethod
    def assert_call_record_updated_for_failure(record: CallRecord, error_msg: str):
        """Assert call record was updated for failed call"""
        assert record.status == CallStatus.FAILED
        assert record.error_message == error_msg
        assert record.ended_at is not None
    
    @staticmethod
    def assert_result_success(result: Dict[str, Any], expected_keys: List[str] = None):
        """Assert a task result indicates success"""
        assert result.get("success") is True
        if expected_keys:
            for key in expected_keys:
                assert key in result
    
    @staticmethod
    def assert_result_failure(result: Dict[str, Any], expected_error: str = None):
        """Assert a task result indicates failure"""
        assert result.get("success") is False
        if expected_error:
            assert expected_error in str(result.get("error", ""))
    
    @staticmethod
    def assert_sip_error_result(result: Dict[str, Any], sip_code: str, retryable: bool):
        """Assert result contains expected SIP error information"""
        assert result.get("sip_status_code") == sip_code
        assert result.get("retryable") is retryable
        assert "error" in result


# Pytest fixtures using the builders
@pytest.fixture
def call_item_builder():
    """Fixture providing a CallItemBuilder"""
    return CallItemBuilder()


@pytest.fixture
def call_record_builder():
    """Fixture providing a CallRecordBuilder"""
    return CallRecordBuilder()


@pytest.fixture
def discharge_order_builder():
    """Fixture providing a DischargeOrderBuilder"""
    return DischargeOrderBuilder()


@pytest.fixture
def mock_factory():
    """Fixture providing MockFactory"""
    return MockFactory


@pytest.fixture
def assert_helpers():
    """Fixture providing AssertionHelpers"""
    return AssertionHelpers


# Common test scenarios
def create_pending_calls_scenario(count: int = 3) -> List[CallScheduleItem]:
    """Create a list of pending calls for testing"""
    builder = CallItemBuilder()
    calls = []
    
    for i in range(count):
        call = (builder
                .reset()
                .with_id(f"call-{i+1}")
                .with_patient(f"patient-{i+1}", f"+155500{i+1:04d}")
                .scheduled_in_past(minutes=i*5 + 5)
                .as_pending()
                .build())
        calls.append(call)
    
    return calls


def create_mixed_status_calls_scenario() -> List[CallScheduleItem]:
    """Create calls with mixed statuses for testing"""
    builder = CallItemBuilder()
    
    return [
        builder.reset().with_id("pending-1").as_pending().scheduled_in_past().build(),
        builder.reset().with_id("progress-1").as_in_progress().build(),
        builder.reset().with_id("completed-1").as_completed().build(),
        builder.reset().with_id("failed-1").as_failed().build(),
        builder.reset().with_id("pending-2").as_pending().scheduled_in_future().build(),
    ]