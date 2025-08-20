"""
Tests for LiveKit call executor functionality
"""
import pytest
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from followup.call_executor import LiveKitCallExecutor, execute_livekit_call, CallOutcomeHandler
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from livekit import api


class TestLiveKitCallExecutor:
    """Tests for LiveKitCallExecutor class"""
    
    def test_init_with_valid_trunk_id(self):
        """Test initialization with valid SIP trunk ID"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            executor = LiveKitCallExecutor()
            assert executor.outbound_trunk_id == 'ST_test123'
            assert executor.agent_name == 'postop-followup-agent'
    
    def test_init_without_trunk_id(self):
        """Test initialization fails without SIP trunk ID"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SIP_OUTBOUND_TRUNK_ID must be set"):
                LiveKitCallExecutor()
    
    def test_init_with_invalid_trunk_id(self):
        """Test initialization fails with invalid SIP trunk ID"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'invalid_id'}):
            with pytest.raises(ValueError, match="SIP_OUTBOUND_TRUNK_ID must be set"):
                LiveKitCallExecutor()
    
    @pytest.mark.asyncio
    async def test_execute_call_success(self, sample_call_item, sample_call_record, mock_livekit_api):
        """Test successful call execution"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            executor = LiveKitCallExecutor()
            
            # Mock the API instance
            with patch('livekit.api.LiveKitAPI', return_value=mock_livekit_api):
                success, result_data = await executor.execute_call(sample_call_item, sample_call_record)
            
            assert success is True
            assert 'room_name' in result_data
            assert 'participant_identity' in result_data
            assert 'outcome' in result_data
            assert result_data['room_name'] == f"followup-{sample_call_item.id}"
            assert result_data['participant_identity'] == "patient"
            
            # Verify API calls were made
            mock_livekit_api.agent_dispatch.create_dispatch.assert_called_once()
            mock_livekit_api.sip.create_sip_participant.assert_called_once()
            mock_livekit_api.aclose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_call_sip_error(self, sample_call_item, sample_call_record):
        """Test call execution with SIP error"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            executor = LiveKitCallExecutor()
            
            # Mock API to raise TwirpError
            mock_api = Mock()
            mock_api.aclose = AsyncMock()
            
            # Create mock dispatch
            mock_dispatch = Mock()
            mock_dispatch.id = "dispatch-123"
            mock_api.agent_dispatch.create_dispatch = AsyncMock(return_value=mock_dispatch)
            
            # Make SIP participant creation raise TwirpError
            class MockTwirpError(Exception):
                def __init__(self, message, metadata):
                    self.message = message
                    self.metadata = metadata
            
            twirp_error = MockTwirpError("SIP_ERROR", {"sip_status_code": "486", "sip_status": "Busy Here"})
            mock_api.sip.create_sip_participant = AsyncMock(side_effect=twirp_error)
            
            with patch('livekit.api.LiveKitAPI', return_value=mock_api):
                with patch('followup.call_executor.api.TwirpError', MockTwirpError):
                    success, result_data = await executor.execute_call(sample_call_item, sample_call_record)
            
            assert success is False
            assert 'error' in result_data
            assert result_data['sip_status_code'] == '486'
            assert result_data['sip_status'] == 'Busy Here'
            assert result_data['retryable'] is True  # 486 is retryable
    
    @pytest.mark.asyncio
    async def test_execute_call_unexpected_error(self, sample_call_item, sample_call_record):
        """Test call execution with unexpected error"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            executor = LiveKitCallExecutor()
            
            # Mock API to raise unexpected exception
            mock_api = Mock()
            mock_api.aclose = AsyncMock()
            mock_api.agent_dispatch.create_dispatch = AsyncMock(side_effect=Exception("Unexpected error"))
            
            with patch('livekit.api.LiveKitAPI', return_value=mock_api):
                success, result_data = await executor.execute_call(sample_call_item, sample_call_record)
            
            assert success is False
            assert 'error' in result_data
            assert 'Unexpected error' in result_data['error']
            assert result_data['retryable'] is True  # Unexpected errors are retryable by default
    
    def test_execute_call_sync(self, sample_call_item, sample_call_record):
        """Test synchronous wrapper for call execution"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            executor = LiveKitCallExecutor()
            
            # Mock the async execute_call method
            async def mock_execute(call_item, call_record):
                return True, {"outcome": "success"}
            
            executor.execute_call = mock_execute
            
            success, result_data = executor.execute_call_sync(sample_call_item, sample_call_record)
            
            assert success is True
            assert result_data['outcome'] == "success"
    
    def test_execute_call_sync_error(self, sample_call_item, sample_call_record):
        """Test synchronous wrapper error handling"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            executor = LiveKitCallExecutor()
            
            # Mock the async execute_call method to raise exception
            async def mock_execute(call_item, call_record):
                raise Exception("Async error")
            
            executor.execute_call = mock_execute
            
            success, result_data = executor.execute_call_sync(sample_call_item, sample_call_record)
            
            assert success is False
            assert 'error' in result_data
            assert 'Async error' in result_data['error']


class TestExecuteLivekitCallFunction:
    """Tests for the standalone execute_livekit_call function"""
    
    def test_execute_livekit_call_success(self, sample_call_item, sample_call_record):
        """Test successful call execution via standalone function"""
        with patch.dict(os.environ, {'SIP_OUTBOUND_TRUNK_ID': 'ST_test123'}):
            with patch('followup.call_executor.LiveKitCallExecutor') as mock_executor_class:
                mock_executor = Mock()
                mock_executor.execute_call_sync.return_value = (True, {"outcome": "success"})
                mock_executor_class.return_value = mock_executor
                
                success, result_data = execute_livekit_call(sample_call_item, sample_call_record)
                
                assert success is True
                assert result_data['outcome'] == "success"
                mock_executor.execute_call_sync.assert_called_once_with(sample_call_item, sample_call_record)
    
    def test_execute_livekit_call_initialization_error(self, sample_call_item, sample_call_record):
        """Test error during executor initialization"""
        with patch('followup.call_executor.LiveKitCallExecutor', side_effect=Exception("Init error")):
            success, result_data = execute_livekit_call(sample_call_item, sample_call_record)
            
            assert success is False
            assert 'error' in result_data
            assert 'Init error' in result_data['error']
            assert result_data['retryable'] is False


class TestCallOutcomeHandler:
    """Tests for CallOutcomeHandler utility class"""
    
    def test_should_retry_under_max_attempts(self):
        """Test retry logic when under max attempts"""
        result_data = {"retryable": True}
        
        # Should retry when under max attempts
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is True
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=2, max_attempts=3) is True
    
    def test_should_not_retry_at_max_attempts(self):
        """Test no retry when at max attempts"""
        result_data = {"retryable": True}
        
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=3, max_attempts=3) is False
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=4, max_attempts=3) is False
    
    def test_should_not_retry_when_not_retryable(self):
        """Test no retry when error is not retryable"""
        result_data = {"retryable": False}
        
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is False
    
    def test_should_not_retry_permanent_sip_failures(self):
        """Test no retry for permanent SIP failures"""
        # 404 - Not found (permanent failure)
        result_data = {"retryable": True, "sip_status_code": "404"}
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is False
        
        # 410 - Gone (permanent failure)
        result_data = {"retryable": True, "sip_status_code": "410"}
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is False
        
        # 603 - Decline (permanent failure)
        result_data = {"retryable": True, "sip_status_code": "603"}
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is False
    
    def test_should_retry_temporary_sip_failures(self):
        """Test retry for temporary SIP failures"""
        # 486 - Busy (temporary)
        result_data = {"retryable": True, "sip_status_code": "486"}
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is True
        
        # 503 - Service unavailable (temporary)
        result_data = {"retryable": True, "sip_status_code": "503"}
        assert CallOutcomeHandler.should_retry(result_data, attempt_count=1, max_attempts=3) is True
    
    def test_get_retry_delay(self):
        """Test retry delay calculation (exponential backoff)"""
        assert CallOutcomeHandler.get_retry_delay(1) == 300   # 5 minutes
        assert CallOutcomeHandler.get_retry_delay(2) == 900   # 15 minutes
        assert CallOutcomeHandler.get_retry_delay(3) == 1800  # 30 minutes
        assert CallOutcomeHandler.get_retry_delay(4) == 1800  # Caps at 30 minutes
    
    def test_get_outcome_summary_success(self):
        """Test outcome summary for successful calls"""
        result_data = {"outcome": "success"}
        summary = CallOutcomeHandler.get_outcome_summary(result_data)
        assert summary == "Call completed successfully"
    
    def test_get_outcome_summary_sip_errors(self):
        """Test outcome summary for SIP errors"""
        # Busy
        result_data = {"error": "SIP error", "sip_status_code": "486"}
        summary = CallOutcomeHandler.get_outcome_summary(result_data)
        assert "Patient phone was busy" in summary
        
        # No answer
        result_data = {"error": "SIP error", "sip_status_code": "408"}
        summary = CallOutcomeHandler.get_outcome_summary(result_data)
        assert "No answer - call timed out" in summary
        
        # Not found
        result_data = {"error": "SIP error", "sip_status_code": "404"}
        summary = CallOutcomeHandler.get_outcome_summary(result_data)
        assert "Phone number not found" in summary
    
    def test_get_outcome_summary_generic_error(self):
        """Test outcome summary for generic errors"""
        result_data = {"error": "Something went wrong"}
        summary = CallOutcomeHandler.get_outcome_summary(result_data)
        assert summary == "Call failed: Something went wrong"