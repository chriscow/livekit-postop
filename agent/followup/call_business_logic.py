"""
Business logic for call execution - pure functions with no external dependencies

These functions contain the core business logic for call execution,
separated from infrastructure concerns for easier testing.
"""
import logging
from typing import Dict, Any, Tuple
from datetime import datetime

from scheduling.models import CallScheduleItem, CallRecord, CallStatus

logger = logging.getLogger("call-business-logic")


def prepare_call_metadata(call_item: CallScheduleItem) -> Dict[str, Any]:
    """
    Prepare metadata for agent dispatch
    
    Args:
        call_item: The call to prepare metadata for
        
    Returns:
        Dictionary of metadata for the agent
    """
    return {
        "call_schedule_item": call_item.to_dict(),
        "patient_phone": call_item.patient_phone,
        "call_type": call_item.call_type.value,
        "related_order_id": call_item.related_discharge_order_id
    }


def generate_room_name(call_item: CallScheduleItem) -> str:
    """
    Generate room name for the call
    
    Args:
        call_item: The call to generate room name for
        
    Returns:
        Unique room name for this call
    """
    return f"followup-{call_item.id}"


def should_retry_call(
    sip_status_code: str, 
    attempt_count: int, 
    max_attempts: int = 3
) -> bool:
    """
    Determine if a failed call should be retried based on SIP status
    
    Args:
        sip_status_code: SIP response code from the call attempt
        attempt_count: Current number of attempts
        max_attempts: Maximum allowed attempts
        
    Returns:
        True if the call should be retried, False otherwise
    """
    if attempt_count >= max_attempts:
        return False
    
    # Don't retry for permanent failures
    permanent_failures = ['404', '410', '603']  # Not found, gone, decline
    if sip_status_code in permanent_failures:
        return False
    
    # Retry for temporary failures
    retryable_statuses = ['486', '487', '408', '503']  # Busy, cancelled, timeout, service unavailable
    return sip_status_code in retryable_statuses


def calculate_retry_delay(attempt_count: int) -> int:
    """
    Calculate delay before retry using exponential backoff
    
    Args:
        attempt_count: Current attempt number
        
    Returns:
        Delay in seconds
    """
    # Exponential backoff: 5 minutes, 15 minutes, 30 minutes
    delays = [300, 900, 1800]  # 5m, 15m, 30m
    return delays[min(attempt_count - 1, len(delays) - 1)]


def classify_sip_error(sip_status_code: str) -> Tuple[str, bool]:
    """
    Classify SIP error code into human-readable message and retryability
    
    Args:
        sip_status_code: SIP response code
        
    Returns:
        Tuple of (human_readable_message, is_retryable)
    """
    status_meanings = {
        '486': ('Patient phone was busy', True),
        '487': ('Call was cancelled or timed out', True),
        '408': ('No answer - call timed out', True),
        '503': ('Service temporarily unavailable', True),
        '404': ('Phone number not found', False),
        '603': ('Call declined', False),
        '410': ('Phone number no longer in service', False)
    }
    
    message, retryable = status_meanings.get(
        sip_status_code, 
        (f'SIP error {sip_status_code}', True)
    )
    
    return message, retryable


def update_call_record_for_attempt(
    call_record: CallRecord, 
    room_name: str, 
    attempt_number: int
) -> None:
    """
    Update call record with attempt information
    
    Args:
        call_record: Call record to update
        room_name: Room name for this attempt
        attempt_number: Current attempt number
    """
    call_record.room_name = room_name
    call_record.participant_identity = "patient"
    call_record.started_at = datetime.now()
    call_record.status = CallStatus.IN_PROGRESS
    call_record.retry_count = attempt_number
    call_record.updated_at = datetime.now()


def update_call_record_for_success(
    call_record: CallRecord, 
    dispatch_id: str, 
    participant_id: str
) -> None:
    """
    Update call record for successful call initiation
    
    Args:
        call_record: Call record to update
        dispatch_id: LiveKit dispatch ID
        participant_id: SIP participant ID
    """
    call_record.outcome_notes = f"Call initiated successfully. Dispatch: {dispatch_id}, Participant: {participant_id}"
    call_record.updated_at = datetime.now()


def update_call_record_for_failure(
    call_record: CallRecord, 
    error_message: str, 
    sip_status_code: str = None,
    sip_status_text: str = None
) -> None:
    """
    Update call record for failed call attempt
    
    Args:
        call_record: Call record to update
        error_message: Error message from the failure
        sip_status_code: SIP status code if available
        sip_status_text: SIP status text if available
    """
    call_record.ended_at = datetime.now()
    call_record.status = CallStatus.FAILED
    call_record.error_message = error_message
    
    # Build detailed outcome notes
    outcome_parts = [error_message]
    if sip_status_code:
        outcome_parts.append(f"SIP Status: {sip_status_code}")
    if sip_status_text:
        outcome_parts.append(f"SIP Text: {sip_status_text}")
    
    call_record.outcome_notes = " | ".join(outcome_parts)
    call_record.updated_at = datetime.now()


def create_success_result(
    room_name: str, 
    dispatch_id: str, 
    participant_id: str
) -> Dict[str, Any]:
    """
    Create result dictionary for successful call
    
    Args:
        room_name: Room name for the call
        dispatch_id: LiveKit dispatch ID
        participant_id: SIP participant ID
        
    Returns:
        Result dictionary
    """
    return {
        "room_name": room_name,
        "participant_identity": "patient",
        "dispatch_id": dispatch_id,
        "sip_participant_id": participant_id,
        "outcome": "Call initiated successfully"
    }


def create_failure_result(
    room_name: str, 
    error_message: str, 
    sip_status_code: str = None,
    sip_status_text: str = None
) -> Dict[str, Any]:
    """
    Create result dictionary for failed call
    
    Args:
        room_name: Room name for the call
        error_message: Error message
        sip_status_code: SIP status code if available
        sip_status_text: SIP status text if available
        
    Returns:
        Result dictionary
    """
    human_message, retryable = classify_sip_error(sip_status_code) if sip_status_code else (error_message, True)
    
    return {
        "error": error_message,
        "sip_status_code": sip_status_code,
        "sip_status": sip_status_text,
        "retryable": retryable,
        "room_name": room_name,
        "human_message": human_message
    }