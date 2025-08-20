"""
LiveKit Call Executor - Handles outbound calling via LiveKit for scheduled follow-up calls
"""
import logging
import os
from typing import Dict, Any, Tuple
from livekit import api

from discharge.config import LIVEKIT_AGENT_NAME
from scheduling.models import CallScheduleItem, CallRecord, CallStatus
from .livekit_adapter import (
    LiveKitAdapter, RealLiveKitAdapter, AgentDispatchRequest, SipCallRequest
)
from .call_business_logic import (
    prepare_call_metadata, generate_room_name, update_call_record_for_attempt,
    update_call_record_for_success, update_call_record_for_failure,
    create_success_result, create_failure_result
)

logger = logging.getLogger("call-executor")


class LiveKitCallExecutor:
    """
    Executes outbound calls via LiveKit SIP for scheduled patient follow-ups
    
    Uses dependency injection for LiveKit adapter to improve testability.
    Business logic is separated into pure functions.
    """
    
    def __init__(self, livekit_adapter: LiveKitAdapter = None):
        """
        Initialize the LiveKit call executor
        
        Args:
            livekit_adapter: LiveKit adapter for API calls (defaults to real adapter)
        """
        self.outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
        self.agent_name = LIVEKIT_AGENT_NAME
        self.adapter = livekit_adapter or RealLiveKitAdapter()
        
        if not self.outbound_trunk_id or not self.outbound_trunk_id.startswith("ST_"):
            logger.error("SIP_OUTBOUND_TRUNK_ID is not set or invalid")
            raise ValueError("SIP_OUTBOUND_TRUNK_ID must be set and start with 'ST_'")
    
    async def execute_call(
        self, 
        call_item: CallScheduleItem, 
        call_record: CallRecord,
        attempt_number: int = 1
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute an outbound call via LiveKit
        
        Args:
            call_item: The scheduled call to execute
            call_record: Call record to update with execution details
            attempt_number: Current attempt number (for retry tracking)
            
        Returns:
            Tuple of (success: bool, result_data: dict)
        """
        room_name = generate_room_name(call_item)
        
        try:
            logger.info(f"Executing call {call_item.id} to {call_item.patient_phone} (attempt {attempt_number})")
            
            # Update call record for this attempt
            update_call_record_for_attempt(call_record, room_name, attempt_number)
            
            # Create agent dispatch
            agent_metadata = prepare_call_metadata(call_item)
            dispatch_request = AgentDispatchRequest(
                agent_name=self.agent_name,
                room_name=room_name,
                metadata=agent_metadata
            )
            
            logger.info(f"Creating dispatch for agent {self.agent_name} in room {room_name}")
            dispatch_id = await self.adapter.create_agent_dispatch(dispatch_request)
            
            # Create SIP participant to make the call
            sip_request = SipCallRequest(
                room_name=room_name,
                trunk_id=self.outbound_trunk_id,
                phone_number=call_item.patient_phone,
                participant_identity="patient"
            )
            
            logger.info(f"Dialing {call_item.patient_phone} to room {room_name}")
            participant_id = await self.adapter.create_sip_participant(sip_request)
            
            # Update call record for success
            update_call_record_for_success(call_record, dispatch_id, participant_id)
            
            # Create success result
            result_data = create_success_result(room_name, dispatch_id, participant_id)
            
            logger.info(f"Call {call_item.id} initiated successfully")
            return True, result_data
            
        except api.TwirpError as e:
            # Handle LiveKit SIP errors
            error_msg = f"LiveKit SIP error: {e.message}"
            sip_status = e.metadata.get('sip_status_code', 'unknown')
            sip_status_text = e.metadata.get('sip_status', 'unknown')
            
            logger.error(f"SIP error for call {call_item.id}: {error_msg}, SIP status: {sip_status} {sip_status_text}")
            
            # Update call record for failure
            update_call_record_for_failure(call_record, error_msg, sip_status, sip_status_text)
            
            # Create failure result
            result_data = create_failure_result(room_name, error_msg, sip_status, sip_status_text)
            
            return False, result_data
            
        except Exception as e:
            # Check if it's a mock TwirpError (for testing)
            if hasattr(e, 'metadata') and 'sip_status_code' in e.metadata:
                error_msg = f"Mock SIP error: {e.message if hasattr(e, 'message') else str(e)}"
                sip_status = e.metadata.get('sip_status_code', 'unknown')
                sip_status_text = e.metadata.get('sip_status', 'unknown')
                
                logger.error(f"Mock SIP error for call {call_item.id}: {error_msg}, SIP status: {sip_status} {sip_status_text}")
                
                # Update call record for failure
                update_call_record_for_failure(call_record, error_msg, sip_status, sip_status_text)
                
                # Create failure result
                result_data = create_failure_result(room_name, error_msg, sip_status, sip_status_text)
                
                return False, result_data
            else:
                # Handle unexpected errors
                error_msg = f"Unexpected error executing call: {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # Update call record for failure
                update_call_record_for_failure(call_record, error_msg)
                
                # Create failure result
                result_data = create_failure_result(room_name, error_msg)
                
                return False, result_data
    
    def execute_call_sync(
        self, 
        call_item: CallScheduleItem, 
        call_record: CallRecord
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Synchronous wrapper for execute_call (for use in RQ tasks)
        
        Args:
            call_item: The scheduled call to execute
            call_record: Call record to update with execution details
            
        Returns:
            Tuple of (success: bool, result_data: dict)
        """
        import asyncio
        
        try:
            # Run the async call execution
            return asyncio.run(self.execute_call(call_item, call_record))
        except Exception as e:
            logger.error(f"Error in sync call execution: {e}")
            return False, {"error": str(e), "retryable": True}


# Synchronous function for use in RQ tasks (since RQ doesn't handle async well)
def execute_livekit_call(call_item: CallScheduleItem, call_record: CallRecord) -> Tuple[bool, Dict[str, Any]]:
    """
    Synchronous function to execute a LiveKit call (for use in RQ tasks)
    
    Args:
        call_item: The scheduled call to execute
        call_record: Call record to update with execution details
        
    Returns:
        Tuple of (success: bool, result_data: dict)
    """
    try:
        executor = LiveKitCallExecutor()
        return executor.execute_call_sync(call_item, call_record)
    except Exception as e:
        logger.error(f"Failed to initialize call executor: {e}")
        return False, {"error": f"Executor initialization failed: {str(e)}", "retryable": False}


class CallOutcomeHandler:
    """
    Handles different call outcomes and determines next actions
    """
    
    @staticmethod
    def should_retry(result_data: Dict[str, Any], attempt_count: int, max_attempts: int) -> bool:
        """
        Determine if a failed call should be retried
        
        Args:
            result_data: Result data from the call attempt
            attempt_count: Current number of attempts
            max_attempts: Maximum allowed attempts
            
        Returns:
            True if the call should be retried, False otherwise
        """
        if attempt_count >= max_attempts:
            return False
        
        # Check if the error is marked as retryable
        if not result_data.get("retryable", False):
            return False
        
        # Check specific SIP status codes
        sip_status = result_data.get("sip_status_code")
        if sip_status:
            # Don't retry for permanent failures
            permanent_failures = ['404', '410', '603']  # Not found, gone, decline
            if str(sip_status) in permanent_failures:
                return False
        
        return True
    
    @staticmethod
    def get_retry_delay(attempt_count: int) -> int:
        """
        Calculate delay before retry (exponential backoff)
        
        Args:
            attempt_count: Current attempt number
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff: 5 minutes, 15 minutes, 30 minutes
        delays = [300, 900, 1800]  # 5m, 15m, 30m
        return delays[min(attempt_count - 1, len(delays) - 1)]
    
    @staticmethod
    def get_outcome_summary(result_data: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of the call outcome
        
        Args:
            result_data: Result data from the call attempt
            
        Returns:
            Human-readable outcome summary
        """
        if "error" not in result_data:
            return "Call completed successfully"
        
        error = result_data["error"]
        sip_status = result_data.get("sip_status_code")
        sip_text = result_data.get("sip_status")
        
        if sip_status:
            status_meanings = {
                '486': 'Patient phone was busy',
                '487': 'Call was cancelled or timed out',
                '408': 'No answer - call timed out',
                '503': 'Service temporarily unavailable',
                '404': 'Phone number not found',
                '603': 'Call declined'
            }
            
            meaning = status_meanings.get(str(sip_status), f'SIP error {sip_status}')
            return f"{meaning} ({error})"
        
        return f"Call failed: {error}"