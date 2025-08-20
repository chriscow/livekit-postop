"""
RQ tasks for LLM-based discharge instruction analysis and call scheduling
"""

import logging
import os
from datetime import datetime
from rq import get_current_job
from rq.decorators import job
import redis

from utils.time_utils import now_utc
from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallType, CallStatus
from .transcript_analyzer import analyze_and_schedule_calls

logger = logging.getLogger("analysis-tasks")

# Redis connection for RQ
redis_conn = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'redis'), 
    port=int(os.environ.get('REDIS_PORT', 6379)), 
    decode_responses=True
)


@job('analysis', connection=redis_conn, timeout=180)
def analyze_discharge_and_schedule_calls(
    session_id: str,
    patient_name: str,
    patient_phone: str, 
    patient_language: str,
    collected_instructions: list,
    original_instructions: list = None,
    discharge_time_iso: str = None
) -> str:
    """
    RQ task to analyze discharge instructions with LLM and schedule follow-up calls
    
    Args:
        session_id: Discharge session identifier
        patient_name: Patient's name
        patient_phone: Patient's phone number for calls
        patient_language: Patient's preferred language
        collected_instructions: List of collected discharge instructions
        original_instructions: Original English instructions (if translated)
        discharge_time_iso: ISO format discharge time (defaults to now)
        
    Returns:
        Status message with results
    """
    current_job = get_current_job()
    
    try:
        logger.info(f"Starting LLM analysis and call scheduling for session {session_id}")
        
        # Parse discharge time
        if discharge_time_iso:
            from utils.time_utils import parse_iso_to_utc
            discharge_time = parse_iso_to_utc(discharge_time_iso)
        else:
            discharge_time = now_utc()
        
        # Perform LLM analysis and get call recommendations
        import asyncio
        analysis, call_items = asyncio.run(analyze_and_schedule_calls(
            session_id=session_id,
            patient_name=patient_name,
            patient_phone=patient_phone,
            patient_language=patient_language,
            collected_instructions=collected_instructions,
            original_instructions=original_instructions,
            discharge_time=discharge_time
        ))
        
        if not call_items:
            logger.warning(f"No calls recommended by LLM for session {session_id}")
            return f"Analysis completed for {patient_name}, but no follow-up calls were recommended"
        
        # Convert to CallScheduleItem objects and schedule them
        scheduler = CallScheduler()
        scheduled_count = 0
        
        for call_data in call_items:
            try:
                # Create CallScheduleItem from LLM recommendation
                call_item = CallScheduleItem(
                    patient_id=call_data["patient_id"],
                    patient_phone=call_data["patient_phone"],
                    scheduled_time=call_data["scheduled_time"],
                    call_type=CallType.from_string(call_data.get("call_type", "general_followup")),
                    priority=call_data.get("priority", 3),
                    llm_prompt=call_data["llm_prompt"],
                    metadata=call_data.get("metadata", {}),
                    status=CallStatus.PENDING
                )
                
                # Schedule the call
                if scheduler.schedule_call(call_item):
                    scheduled_count += 1
                    logger.info(f"Scheduled LLM-generated call {call_item.id} for {call_item.scheduled_time}")
                else:
                    logger.error(f"Failed to schedule call for {patient_name}")
                    
            except Exception as e:
                logger.error(f"Error creating/scheduling call for {patient_name}: {e}")
                continue
        
        # Create summary message
        result_msg = f"LLM analysis completed for {patient_name}: {scheduled_count}/{len(call_items)} calls scheduled successfully"
        
        # Add analysis insights to the message
        if analysis.overall_complexity == "complex":
            result_msg += f" (Complex case - {analysis.analysis_confidence:.1%} confidence)"
        elif analysis.special_considerations:
            result_msg += f" (Special considerations noted)"
        
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"Exception in LLM analysis for session {session_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@job('analysis', connection=redis_conn, timeout=120)
def trigger_post_discharge_analysis(session_id: str) -> str:
    """
    RQ task to trigger post-discharge analysis after agent workflow completes
    
    This task retrieves session data from Redis and initiates LLM analysis
    
    Args:
        session_id: The discharge session identifier
        
    Returns:
        Status message
    """
    try:
        logger.info(f"Triggering post-discharge analysis for session {session_id}")
        
        # Import here to avoid circular imports
        from shared.memory import RedisMemory
        memory = RedisMemory()
        
        # Retrieve session data from Redis
        session_data = memory.get_all_session_data(session_id)
        
        if not session_data:
            error_msg = f"No session data found for {session_id}"
            logger.error(error_msg)
            return error_msg
        
        # Extract required information
        patient_name = session_data.get("patient_name")
        patient_language = session_data.get("patient_language", "english")
        
        # Note: Patient phone would need to be added to session data in the discharge agent
        # For now, we'll use a placeholder and log a warning
        patient_phone = session_data.get("patient_phone", "+15551234567")  # Placeholder
        if patient_phone == "+15551234567":
            logger.warning(f"Using placeholder phone number for session {session_id}")
        
        # Get collected instructions - these would be stored by the discharge agent
        collected_instructions = session_data.get("collected_instructions", [])
        original_instructions = session_data.get("original_instructions", [])
        
        if not collected_instructions and not original_instructions:
            logger.warning(f"No instructions found for session {session_id}")
            # Still proceed with minimal analysis
            collected_instructions = [{"text": "General post-procedure care", "type": "general"}]
        
        # Queue the LLM analysis task
        analyze_discharge_and_schedule_calls.delay(
            session_id=session_id,
            patient_name=patient_name,
            patient_phone=patient_phone,
            patient_language=patient_language,
            collected_instructions=collected_instructions,
            original_instructions=original_instructions,
            discharge_time_iso=datetime.now().isoformat()
        )
        
        result_msg = f"Queued LLM analysis for {patient_name} (session {session_id})"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"Exception triggering analysis for session {session_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@job('analysis', connection=redis_conn, timeout=60)
def test_llm_analysis(patient_name: str = "Test Patient") -> str:
    """
    Test task for LLM analysis with sample data
    
    Args:
        patient_name: Name for test patient
        
    Returns:
        Test results
    """
    try:
        logger.info(f"Running LLM analysis test for {patient_name}")
        
        # Create sample discharge instructions
        test_instructions = [
            {
                "text": "Remove compression bandages in 24 hours and keep the area clean and dry",
                "type": "wound_care"
            },
            {
                "text": "Take ibuprofen 400mg every 6 hours for pain as needed",
                "type": "medication"
            },
            {
                "text": "Avoid strenuous activity for 48 hours, then gradually return to normal activities",
                "type": "activity"
            },
            {
                "text": "Call immediately if you notice increased swelling, redness, or fever over 101°F",
                "type": "warning"
            }
        ]
        
        # Run analysis
        test_session_id = f"test-{int(datetime.now().timestamp())}"
        
        import asyncio
        analysis, call_items = asyncio.run(analyze_and_schedule_calls(
            session_id=test_session_id,
            patient_name=patient_name,
            patient_phone="+15551234567",
            patient_language="english",
            collected_instructions=test_instructions,
            discharge_time=datetime.now()
        ))
        
        # Format results
        result_msg = f"LLM Analysis Test Results for {patient_name}:\\n"
        result_msg += f"- Instructions analyzed: {len(analysis.analyzed_instructions)}\\n"
        result_msg += f"- Calls recommended: {len(analysis.call_recommendations)}\\n"
        result_msg += f"- Overall complexity: {analysis.overall_complexity}\\n"
        result_msg += f"- Analysis confidence: {analysis.analysis_confidence:.1%}\\n"
        
        if analysis.special_considerations:
            result_msg += f"- Special considerations: {', '.join(analysis.special_considerations)}\\n"
        
        result_msg += f"\\nRecommended Calls:\\n"
        for i, call in enumerate(call_items, 1):
            result_msg += f"  {i}. {call['call_type']} - Priority {call['priority']} - {call['scheduled_time'].strftime('%Y-%m-%d %H:%M')}\\n"
        
        logger.info(f"LLM analysis test completed successfully")
        return result_msg
        
    except Exception as e:
        error_msg = f"LLM analysis test failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg