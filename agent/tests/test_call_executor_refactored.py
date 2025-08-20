"""
Tests for refactored call executor with separated concerns
"""
import pytest
import os
from unittest.mock import patch, AsyncMock

from followup.call_executor import LiveKitCallExecutor
from followup.livekit_adapter import MockLiveKitAdapter
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from livekit.api import TwirpError


class TestRefactoredCallExecutor:
    """Tests for the refactored call executor with dependency injection"""
    
    def test_init_with_valid_trunk_id(self):
        """Test initialization with valid SIP trunk ID"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            mock_adapter = MockLiveKitAdapter()
            executor = LiveKitCallExecutor(livekit_adapter=mock_adapter)
            
            assert executor.outbound_trunk_id == 'ST_test123'
            assert executor.agent_name == 'postop-followup-agent'
            assert executor.adapter == mock_adapter
    
    def test_init_without_trunk_id(self):
        """Test initialization fails without SIP trunk ID"""
        with patch.dict(os.environ, {}, clear=True):
            mock_adapter = MockLiveKitAdapter()
            with pytest.raises(ValueError, match="SIP_OUTBOUND_TRUNK_ID must be set"):
                LiveKitCallExecutor(livekit_adapter=mock_adapter)
    
    @pytest.mark.asyncio
    async def test_execute_call_success(self, sample_call_item, sample_call_record):
        """Test successful call execution with mock adapter"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            mock_adapter = MockLiveKitAdapter()
            executor = LiveKitCallExecutor(livekit_adapter=mock_adapter)
            
            success, result_data = await executor.execute_call(sample_call_item, sample_call_record)
            
            # Verify success
            assert success is True
            assert 'room_name' in result_data
            assert 'dispatch_id' in result_data
            assert 'sip_participant_id' in result_data
            
            # Verify adapter was called correctly
            assert len(mock_adapter.dispatches_created) == 1
            assert len(mock_adapter.participants_created) == 1
            
            dispatch = mock_adapter.dispatches_created[0]
            assert dispatch['agent_name'] == 'postop-followup-agent'
            assert dispatch['room_name'] == f"followup-{sample_call_item.id}"
            
            participant = mock_adapter.participants_created[0]
            assert participant['phone_number'] == sample_call_item.patient_phone
            assert participant['trunk_id'] == 'ST_test123'
            
            # Verify call record was updated
            assert sample_call_record.room_name == f"followup-{sample_call_item.id}"
            assert sample_call_record.participant_identity == "patient"
            assert sample_call_record.status == CallStatus.IN_PROGRESS
    
    @pytest.mark.asyncio
    async def test_execute_call_sip_failure(self, sample_call_item, sample_call_record):
        """Test call execution with SIP failure"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            mock_adapter = MockLiveKitAdapter()
            # Configure mock to fail on SIP participant creation (not dispatch)
            mock_adapter.should_fail = True
            mock_adapter.fail_on_dispatch = False  # Fail on SIP participant creation
            mock_adapter.failure_sip_code = "486"
            mock_adapter.failure_error = "Busy Here"
            
            executor = LiveKitCallExecutor(livekit_adapter=mock_adapter)
            
            success, result_data = await executor.execute_call(sample_call_item, sample_call_record)
            
            # Verify failure
            assert success is False
            assert 'error' in result_data
            assert result_data['sip_status_code'] == '486'
            assert result_data['retryable'] is True  # 486 is retryable
            
            # Verify dispatch was created but participant failed
            assert len(mock_adapter.dispatches_created) == 1
            assert len(mock_adapter.participants_created) == 0
            
            # Verify call record was updated for failure
            assert sample_call_record.status == CallStatus.FAILED
            assert sample_call_record.error_message is not None
    
    @pytest.mark.asyncio
    async def test_execute_call_generic_failure(self, sample_call_item, sample_call_record):
        """Test call execution with generic failure"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            mock_adapter = MockLiveKitAdapter()
            # Configure mock to fail on dispatch creation
            mock_adapter.should_fail = True
            mock_adapter.fail_on_dispatch = True  # Fail on dispatch creation
            mock_adapter.failure_error = "Generic adapter failure"
            
            executor = LiveKitCallExecutor(livekit_adapter=mock_adapter)
            
            success, result_data = await executor.execute_call(sample_call_item, sample_call_record)
            
            # Verify failure
            assert success is False
            assert 'error' in result_data
            assert result_data['retryable'] is True  # Generic errors are retryable
            
            # Verify no operations succeeded
            assert len(mock_adapter.dispatches_created) == 0
            assert len(mock_adapter.participants_created) == 0
    
    @pytest.mark.asyncio
    async def test_execute_call_with_attempt_number(self, sample_call_item, sample_call_record):
        """Test call execution with specific attempt number"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            mock_adapter = MockLiveKitAdapter()
            executor = LiveKitCallExecutor(livekit_adapter=mock_adapter)
            
            success, result_data = await executor.execute_call(
                sample_call_item, sample_call_record, attempt_number=3
            )
            
            # Verify attempt number was recorded
            assert sample_call_record.retry_count == 3
    
    def test_execute_call_sync(self, sample_call_item, sample_call_record):
        """Test synchronous wrapper works correctly"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            mock_adapter = MockLiveKitAdapter()
            executor = LiveKitCallExecutor(livekit_adapter=mock_adapter)
            
            success, result_data = executor.execute_call_sync(sample_call_item, sample_call_record)
            
            assert success is True
            assert len(mock_adapter.dispatches_created) == 1
            assert len(mock_adapter.participants_created) == 1


class TestMockLiveKitAdapter:
    """Tests for the mock LiveKit adapter"""
    
    @pytest.mark.asyncio
    async def test_create_agent_dispatch_success(self):
        """Test successful agent dispatch creation"""
        from followup.livekit_adapter import AgentDispatchRequest
        
        adapter = MockLiveKitAdapter()
        request = AgentDispatchRequest(
            agent_name="test-agent",
            room_name="test-room",
            metadata={"test": "data"}
        )
        
        dispatch_id = await adapter.create_agent_dispatch(request)
        
        assert dispatch_id is not None
        assert len(adapter.dispatches_created) == 1
        assert adapter.dispatches_created[0]['agent_name'] == "test-agent"
        assert adapter.dispatches_created[0]['room_name'] == "test-room"
    
    @pytest.mark.asyncio
    async def test_create_sip_participant_success(self):
        """Test successful SIP participant creation"""
        from followup.livekit_adapter import SipCallRequest
        
        adapter = MockLiveKitAdapter()
        request = SipCallRequest(
            room_name="test-room",
            trunk_id="ST_test123",
            phone_number="+1234567890",
            participant_identity="patient"
        )
        
        participant_id = await adapter.create_sip_participant(request)
        
        assert participant_id is not None
        assert len(adapter.participants_created) == 1
        assert adapter.participants_created[0]['phone_number'] == "+1234567890"
    
    @pytest.mark.asyncio
    async def test_mock_failure_modes(self):
        """Test mock adapter failure modes"""
        from followup.livekit_adapter import AgentDispatchRequest
        
        adapter = MockLiveKitAdapter()
        adapter.should_fail = True
        adapter.fail_on_dispatch = True  # Need to set this for dispatch failures
        adapter.failure_error = "Test failure"
        
        request = AgentDispatchRequest("test", "test", {})
        
        with pytest.raises(Exception, match="Test failure"):
            await adapter.create_agent_dispatch(request)
    
    def test_mock_reset(self):
        """Test mock adapter reset functionality"""
        adapter = MockLiveKitAdapter()
        adapter.should_fail = True
        adapter.failure_error = "Test"
        adapter.dispatches_created = [{"test": "data"}]
        adapter.participants_created = [{"test": "data"}]
        
        adapter.reset()
        
        assert adapter.should_fail is False
        assert adapter.failure_error is None
        assert len(adapter.dispatches_created) == 0
        assert len(adapter.participants_created) == 0