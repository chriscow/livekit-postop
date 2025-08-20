"""
RQ tasks for executing scheduled patient follow-up calls
"""
import json
import logging
from datetime import datetime
from rq import get_current_job
from rq.decorators import job
import redis

from utils.time_utils import now_utc, parse_iso_to_utc

from .models import CallScheduleItem, CallRecord, CallStatus
from .scheduler import CallScheduler

logger = logging.getLogger("followup-tasks")

# Redis connection for RQ
import os
redis_conn = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'redis'), 
    port=int(os.environ.get('REDIS_PORT', 6379)), 
    decode_responses=True
)


@job('followup_calls', connection=redis_conn, timeout=300)
def execute_followup_call(call_id: str) -> str:
    """
    RQ task to execute a scheduled follow-up call via LiveKit
    
    Args:
        call_id: The unique identifier of the call to execute
        
    Returns:
        Status message indicating the result
    """
    current_job = get_current_job()
    scheduler = CallScheduler()
    
    try:
        logger.info(f"Starting execution of call {call_id}")
        
        # Get call data from scheduler
        call_data = scheduler.redis_client.hgetall(f"postop:scheduled_calls:{call_id}")
        if not call_data:
            error_msg = f"Call {call_id} not found in scheduler"
            logger.error(error_msg)
            return error_msg
        
        call_item = CallScheduleItem.from_dict(call_data)
        
        # Check if call is still pending
        if call_item.status != CallStatus.PENDING:
            logger.warning(f"Call {call_id} is not pending (status: {call_item.status})")
            return f"Call {call_id} already processed"
        
        # Update call status to in_progress
        scheduler.update_call_status(call_id, CallStatus.IN_PROGRESS, "Starting call execution")
        
        # Create call record
        call_record = CallRecord(
            call_schedule_item_id=call_id,
            patient_id=call_item.patient_id,
            started_at=now_utc(),
            status=CallStatus.IN_PROGRESS
        )
        
        # Execute the actual LiveKit call
        success, result_data = _execute_livekit_call(call_item, call_record)
        
        # Update call record with results
        call_record.ended_at = now_utc()
        call_record.calculate_duration()
        
        if success:
            call_record.status = CallStatus.COMPLETED
            call_record.outcome_notes = result_data.get("outcome", "Call completed successfully")
            call_record.room_name = result_data.get("room_name")
            call_record.participant_identity = result_data.get("participant_identity")
            
            # Update scheduled call status
            scheduler.update_call_status(
                call_id, 
                CallStatus.COMPLETED, 
                f"Call completed at {call_record.ended_at}"
            )
            
            logger.info(f"Successfully completed call {call_id}")
            result_msg = f"Call {call_id} completed successfully"
            
        else:
            # Handle failure
            error_message = result_data.get("error", "Unknown error occurred")
            call_record.status = CallStatus.FAILED
            call_record.error_message = error_message
            call_record.outcome_notes = f"Call failed: {error_message}"
            
            # Check if we should retry
            call_item.increment_attempt()
            
            if call_item.can_retry():
                # Schedule retry (will be handled by scheduler daemon)
                scheduler.update_call_status(
                    call_id,
                    CallStatus.PENDING, 
                    f"Retry {call_item.attempt_count}/{call_item.max_attempts}: {error_message}"
                )
                logger.info(f"Call {call_id} will be retried (attempt {call_item.attempt_count})")
                result_msg = f"Call {call_id} failed, will retry: {error_message}"
                
            else:
                # Max retries reached
                scheduler.update_call_status(
                    call_id,
                    CallStatus.FAILED,
                    f"Max retries reached: {error_message}"
                )
                logger.error(f"Call {call_id} failed permanently: {error_message}")
                result_msg = f"Call {call_id} failed permanently: {error_message}"
        
        # Save call record
        scheduler.save_call_record(call_record)
        
        return result_msg
        
    except Exception as e:
        error_msg = f"Exception executing call {call_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Update call status on exception
        scheduler.update_call_status(call_id, CallStatus.FAILED, error_msg)
        
        # Save error record
        error_record = CallRecord(
            call_schedule_item_id=call_id,
            patient_id=call_item.patient_id if 'call_item' in locals() else "unknown",
            started_at=now_utc(),
            ended_at=now_utc(),
            status=CallStatus.FAILED,
            error_message=str(e),
            outcome_notes=f"Task execution failed: {str(e)}"
        )
        scheduler.save_call_record(error_record)
        
        return error_msg


def _execute_livekit_call(call_item: CallScheduleItem, call_record: CallRecord) -> tuple[bool, dict]:
    """
    Execute the actual LiveKit outbound call
    
    Args:
        call_item: The call to execute
        call_record: Call record to update with results
        
    Returns:
        Tuple of (success: bool, result_data: dict)
    """
    try:
        # Import here to avoid circular imports
        from followup.call_executor import execute_livekit_call
        
        return execute_livekit_call(call_item, call_record)
        
    except ImportError:
        logger.error("LiveKit call executor not available")
        return False, {"error": "LiveKit call executor not available"}
    except Exception as e:
        logger.error(f"Error executing LiveKit call: {e}")
        return False, {"error": str(e)}


@job('followup_calls', connection=redis_conn, timeout=60)
def schedule_followup_call(call_item_dict: dict, delay_seconds: int = 0) -> str:
    """
    RQ task to schedule a follow-up call for future execution
    
    Args:
        call_item_dict: Dictionary representation of CallScheduleItem
        delay_seconds: Seconds to delay before scheduling (for retries)
        
    Returns:
        Status message
    """
    try:
        call_item = CallScheduleItem.from_dict(call_item_dict)
        scheduler = CallScheduler()
        
        # Store the call in scheduler
        success = scheduler.schedule_call(call_item)
        
        if success:
            # Calculate when to execute the call
            scheduled_time = call_item.scheduled_time
            current_time = now_utc()
            
            if scheduled_time <= current_time:
                # Call is due now, execute immediately
                execute_followup_call.delay(call_item.id)
                logger.info(f"Immediately queued call {call_item.id} for execution")
                return f"Call {call_item.id} queued for immediate execution"
            else:
                # Call is scheduled for future, will be picked up by daemon
                logger.info(f"Scheduled call {call_item.id} for {scheduled_time}")
                return f"Call {call_item.id} scheduled for {scheduled_time}"
        else:
            error_msg = f"Failed to schedule call {call_item.id}"
            logger.error(error_msg)
            return error_msg
            
    except Exception as e:
        error_msg = f"Exception scheduling call: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@job('followup_calls', connection=redis_conn, timeout=120)  
def process_pending_calls() -> str:
    """
    RQ task to process all pending calls that are due for execution.
    This is typically run by a scheduler daemon on a regular interval.
    
    Returns:
        Status message with number of calls processed
    """
    try:
        scheduler = CallScheduler()
        pending_calls = scheduler.get_pending_calls(limit=50)  # Process up to 50 calls at once
        
        if not pending_calls:
            return "No pending calls to process"
        
        queued_count = 0
        for call in pending_calls:
            try:
                # Queue the call for execution
                execute_followup_call.delay(call.id)
                queued_count += 1
                logger.info(f"Queued call {call.id} for execution")
                
            except Exception as e:
                logger.error(f"Failed to queue call {call.id}: {e}")
                # Mark call as failed
                scheduler.update_call_status(
                    call.id, 
                    CallStatus.FAILED, 
                    f"Failed to queue for execution: {str(e)}"
                )
        
        result_msg = f"Processed {len(pending_calls)} pending calls, queued {queued_count} for execution"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"Exception processing pending calls: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@job('followup_calls', connection=redis_conn, timeout=180)
def generate_patient_calls(
    patient_id: str, 
    patient_phone: str, 
    patient_name: str,
    discharge_time_iso: str, 
    selected_order_ids: list
) -> str:
    """
    RQ task to generate all follow-up calls for a patient based on their discharge orders
    
    Args:
        patient_id: Unique patient identifier
        patient_phone: Patient's phone number
        patient_name: Patient's name
        discharge_time_iso: ISO format string of discharge datetime
        selected_order_ids: List of discharge order IDs that apply to this patient
        
    Returns:
        Status message with number of calls generated
    """
    try:
        discharge_time = parse_iso_to_utc(discharge_time_iso)
        scheduler = CallScheduler()
        
        # Generate all calls for the patient
        calls = scheduler.generate_calls_for_patient(
            patient_id=patient_id,
            patient_phone=patient_phone,
            patient_name=patient_name,
            discharge_time=discharge_time,
            selected_order_ids=selected_order_ids
        )
        
        # Schedule each call
        scheduled_count = 0
        for call in calls:
            if scheduler.schedule_call(call):
                scheduled_count += 1
                logger.info(f"Scheduled call {call.id} for {call.scheduled_time}")
            else:
                logger.error(f"Failed to schedule call {call.id}")
        
        result_msg = f"Generated and scheduled {scheduled_count}/{len(calls)} calls for patient {patient_id}"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"Exception generating patient calls: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg