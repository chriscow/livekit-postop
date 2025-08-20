"""
CallScheduler - Generates and manages scheduled patient follow-up calls
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import redis

from utils.time_utils import now_utc, parse_iso_to_utc, to_utc, add_business_hours_offset
from utils.redis_atomic import create_atomic_redis_ops

from .models import CallScheduleItem, CallRecord, CallStatus, CallType
from discharge.discharge_orders import DischargeOrder, get_selected_orders

logger = logging.getLogger("call-scheduler")


class CallScheduler:
    """
    Manages the scheduling and generation of patient follow-up calls.
    
    Handles:
    - Generating calls from discharge orders with call templates
    - Creating standalone wellness check calls
    - Parsing flexible timing specifications
    - Storing/retrieving calls from Redis
    """
    
    def __init__(self, redis_host: str = None, redis_port: int = None):
        """Initialize the call scheduler with Redis connection"""
        import os
        
        # Use environment variables as defaults, fallback to redis for Docker
        if redis_host is None:
            redis_host = os.environ.get('REDIS_HOST', 'redis')
        if redis_port is None:
            redis_port = int(os.environ.get('REDIS_PORT', 6379))
            
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.calls_key = "postop:scheduled_calls"
        self.records_key = "postop:call_records"
        self.atomic_ops = create_atomic_redis_ops(self.redis_client)
    
    def generate_calls_for_patient(
        self, 
        patient_id: str, 
        patient_phone: str,
        patient_name: str,
        discharge_time: datetime, 
        selected_order_ids: List[str]
    ) -> List[CallScheduleItem]:
        """
        Generate all scheduled calls for a patient based on their discharge orders
        
        Args:
            patient_id: Unique patient identifier
            patient_phone: Patient's phone number for outbound calls
            patient_name: Patient's name for personalized prompts
            discharge_time: When the patient was discharged
            selected_order_ids: List of discharge order IDs that apply to this patient
            
        Returns:
            List of CallScheduleItem objects ready to be scheduled
        """
        calls = []
        
        # Get discharge orders that generate calls
        selected_orders = [order for order in get_selected_orders() if order.id in selected_order_ids]
        
        for order in selected_orders:
            if order.generates_calls and order.call_template:
                order_calls = self._generate_calls_from_order(
                    order, patient_id, patient_phone, patient_name, discharge_time
                )
                calls.extend(order_calls)
        
        # Add a general wellness check call
        wellness_call = self._generate_wellness_check_call(
            patient_id, patient_phone, patient_name, discharge_time
        )
        calls.append(wellness_call)
        
        logger.info(f"Generated {len(calls)} calls for patient {patient_id}")
        return calls
    
    def _generate_calls_from_order(
        self, 
        order: DischargeOrder, 
        patient_id: str, 
        patient_phone: str,
        patient_name: str,
        discharge_time: datetime
    ) -> List[CallScheduleItem]:
        """Generate calls from a discharge order's call template"""
        if not order.call_template:
            return []
        
        template = order.call_template
        timing_spec = template.get("timing", "")
        
        # Parse timing specification to get scheduled times
        scheduled_times = self.parse_timing_spec(timing_spec, discharge_time)
        
        calls = []
        for scheduled_time in scheduled_times:
            # Fill in the prompt template with patient-specific data
            prompt = template["prompt_template"].format(
                patient_name=patient_name,
                discharge_order=order.discharge_order
            )
            
            call = CallScheduleItem(
                patient_id=patient_id,
                patient_phone=patient_phone,
                scheduled_time=scheduled_time,
                call_type=CallType(template.get("call_type", "discharge_reminder")),
                priority=template.get("priority", 3),
                llm_prompt=prompt,
                related_discharge_order_id=order.id,
                metadata={
                    "order_label": order.label,
                    "original_timing": timing_spec
                }
            )
            calls.append(call)
        
        return calls
    
    def _generate_wellness_check_call(
        self, 
        patient_id: str, 
        patient_phone: str,
        patient_name: str,
        discharge_time: datetime
    ) -> CallScheduleItem:
        """Generate a general wellness check call"""
        # Schedule within 24 hours after discharge
        scheduled_time = discharge_time + timedelta(hours=18)  # 6 PM next day
        
        prompt = f"""You are calling {patient_name} for a courtesy wellness check after their procedure. 
        This is a general follow-up call to see how they're feeling. 
        Ask about their overall comfort, pain levels, and if they have any questions about their recovery. 
        Be warm and caring in your approach."""
        
        return CallScheduleItem(
            patient_id=patient_id,
            patient_phone=patient_phone,
            scheduled_time=scheduled_time,
            call_type=CallType.WELLNESS_CHECK,
            priority=3,
            llm_prompt=prompt,
            metadata={
                "call_source": "automatic_wellness_check"
            }
        )
    
    def parse_timing_spec(self, timing: str, discharge_time: datetime) -> List[datetime]:
        """
        Parse flexible timing specifications into scheduled datetime objects
        
        Supported formats:
        - "24_hours_after_discharge"
        - "48_hours_after_discharge" 
        - "daily_for_2_days_starting_12_hours_after_discharge"
        - "daily_for_3_days_starting_8_hours_after_discharge"
        - "day_before_date:2025-06-23"
        - "within_24_hours"
        
        Args:
            timing: Timing specification string
            discharge_time: Patient's discharge datetime
            
        Returns:
            List of datetime objects when calls should be scheduled
        """
        scheduled_times = []
        
        # Pattern: X_hours_after_discharge
        hours_match = re.match(r'(\d+)_hours_after_discharge', timing)
        if hours_match:
            hours = int(hours_match.group(1))
            scheduled_times.append(discharge_time + timedelta(hours=hours))
            return scheduled_times
        
        # Pattern: daily_for_X_days_starting_Y_hours_after_discharge
        daily_match = re.match(r'daily_for_(\d+)_days_starting_(\d+)_hours_after_discharge', timing)
        if daily_match:
            num_days = int(daily_match.group(1))
            start_hours = int(daily_match.group(2))
            
            start_time = discharge_time + timedelta(hours=start_hours)
            for day in range(num_days):
                scheduled_times.append(start_time + timedelta(days=day))
            return scheduled_times
        
        # Pattern: day_before_date:YYYY-MM-DD
        date_match = re.match(r'day_before_date:(\d{4}-\d{2}-\d{2})', timing)
        if date_match:
            target_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
            # Schedule for 2 PM the day before
            reminder_time = target_date - timedelta(days=1)
            reminder_time = reminder_time.replace(hour=14, minute=0, second=0, microsecond=0)
            scheduled_times.append(reminder_time)
            return scheduled_times
        
        # Pattern: within_24_hours (schedule for 18 hours after discharge)
        if timing == "within_24_hours":
            scheduled_times.append(discharge_time + timedelta(hours=18))
            return scheduled_times
        
        # Default fallback - schedule 24 hours after discharge
        logger.warning(f"Unknown timing specification: {timing}. Using default of 24 hours.")
        scheduled_times.append(discharge_time + timedelta(hours=24))
        return scheduled_times
    
    def schedule_call(self, call_item: CallScheduleItem) -> bool:
        """
        Store a call in Redis for scheduled execution
        
        Args:
            call_item: The call to schedule
            
        Returns:
            True if successfully scheduled, False otherwise
        """
        try:
            # Store call data in Redis hash
            call_data = call_item.to_dict()
            
            # Convert None values to empty strings for Redis compatibility
            for key, value in call_data.items():
                if value is None:
                    call_data[key] = ""
            
            self.redis_client.hset(
                f"{self.calls_key}:{call_item.id}", 
                mapping=call_data
            )
            
            # Add to scheduled calls index with timestamp
            timestamp = call_item.scheduled_time.timestamp()
            self.redis_client.zadd(
                f"{self.calls_key}:by_time",
                {call_item.id: timestamp}
            )
            
            # Add to patient's calls index
            self.redis_client.sadd(
                f"{self.calls_key}:patient:{call_item.patient_id}",
                call_item.id
            )
            
            logger.info(f"Scheduled call {call_item.id} for {call_item.scheduled_time}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule call {call_item.id}: {e}")
            return False
    
    def get_pending_calls(self, limit: int = 100) -> List[CallScheduleItem]:
        """
        Get calls that are ready to be executed (scheduled time has passed)
        
        Args:
            limit: Maximum number of calls to return
            
        Returns:
            List of CallScheduleItem objects ready for execution
        """
        current_time = now_utc().timestamp()
        
        # Get call IDs that are due
        due_call_ids = self.redis_client.zrangebyscore(
            f"{self.calls_key}:by_time",
            0, current_time,
            start=0, num=limit
        )
        
        pending_calls = []
        for call_id in due_call_ids:
            call_data = self.redis_client.hgetall(f"{self.calls_key}:{call_id}")
            if call_data:
                try:
                    call_item = CallScheduleItem.from_dict(call_data)
                    # Only include pending calls
                    if call_item.status == CallStatus.PENDING:
                        pending_calls.append(call_item)
                except Exception as e:
                    logger.error(f"Error deserializing call {call_id}: {e}")
        
        return pending_calls
    
    def update_call_status(self, call_id: str, status: CallStatus, notes: str = "") -> bool:
        """
        Update the status of a scheduled call
        
        Args:
            call_id: The call's unique identifier
            status: New status to set
            notes: Optional notes about the status change
            
        Returns:
            True if successfully updated, False otherwise
        """
        try:
            # Get current call data
            call_data = self.redis_client.hgetall(f"{self.calls_key}:{call_id}")
            if not call_data:
                logger.warning(f"Call {call_id} not found for status update")
                return False
            
            # Update status and timestamp
            call_data["status"] = status.value
            call_data["updated_at"] = now_utc().isoformat()
            if notes:
                call_data["notes"] = notes
            
            # Save back to Redis
            self.redis_client.hset(f"{self.calls_key}:{call_id}", mapping=call_data)
            
            # If call is completed or failed, remove from scheduled index
            if status in [CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.CANCELLED]:
                self.redis_client.zrem(f"{self.calls_key}:by_time", call_id)
            
            logger.info(f"Updated call {call_id} status to {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update call {call_id} status: {e}")
            return False
    
    def save_call_record(self, call_record: CallRecord) -> bool:
        """
        Save a call execution record
        
        Args:
            call_record: The call record to save
            
        Returns:
            True if successfully saved, False otherwise
        """
        try:
            record_data = call_record.to_dict()
            self.redis_client.hset(
                f"{self.records_key}:{call_record.id}",
                mapping=record_data
            )
            
            # Add to patient's records index
            self.redis_client.sadd(
                f"{self.records_key}:patient:{call_record.patient_id}",
                call_record.id
            )
            
            logger.info(f"Saved call record {call_record.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save call record {call_record.id}: {e}")
            return False
    
    def get_patient_calls(self, patient_id: str) -> List[CallScheduleItem]:
        """Get all scheduled calls for a patient"""
        call_ids = self.redis_client.smembers(f"{self.calls_key}:patient:{patient_id}")
        
        calls = []
        for call_id in call_ids:
            call_data = self.redis_client.hgetall(f"{self.calls_key}:{call_id}")
            if call_data:
                try:
                    calls.append(CallScheduleItem.from_dict(call_data))
                except Exception as e:
                    logger.error(f"Error deserializing call {call_id}: {e}")
        
        return sorted(calls, key=lambda c: c.scheduled_time)
    
    def get_due_calls_atomic(self, limit: int = 50) -> List[CallScheduleItem]:
        """
        Atomically get and claim due calls to prevent race conditions
        
        Args:
            limit: Maximum number of calls to claim
            
        Returns:
            List of CallScheduleItem objects that were successfully claimed
        """
        current_time = now_utc().timestamp()
        
        # Use atomic operations to claim due calls
        claimed_call_ids = self.atomic_ops.dequeue_due_calls(current_time, limit)
        
        claimed_calls = []
        for call_id in claimed_call_ids:
            call_data = self.redis_client.hgetall(f"{self.calls_key}:{call_id}")
            if call_data:
                try:
                    call_item = CallScheduleItem.from_dict(call_data)
                    claimed_calls.append(call_item)
                except Exception as e:
                    logger.error(f"Error deserializing claimed call {call_id}: {e}")
        
        return claimed_calls
    
    def batch_schedule_calls(self, calls: List[CallScheduleItem]) -> int:
        """
        Atomically schedule multiple calls in a single transaction
        
        Args:
            calls: List of CallScheduleItem objects to schedule
            
        Returns:
            Number of calls successfully scheduled
        """
        if not calls:
            return 0
        
        # Convert calls to dictionaries
        calls_data = []
        for call in calls:
            call_dict = call.to_dict()
            # Convert None values to empty strings for Redis compatibility
            for key, value in call_dict.items():
                if value is None:
                    call_dict[key] = ""
            calls_data.append(call_dict)
        
        # Use atomic batch scheduling
        scheduled_count = self.atomic_ops.batch_schedule_calls(calls_data)
        
        if scheduled_count == len(calls):
            logger.info(f"Successfully batch scheduled {scheduled_count} calls")
        else:
            logger.warning(f"Only scheduled {scheduled_count}/{len(calls)} calls in batch")
        
        return scheduled_count
    
    def cleanup_old_calls(self, days_old: int = 30) -> int:
        """
        Archive and cleanup old completed/failed calls
        
        Args:
            days_old: Archive calls older than this many days
            
        Returns:
            Number of calls archived
        """
        return self.atomic_ops.cleanup_old_calls(days_old)
    
    def update_call_status_atomic(
        self, 
        call_id: str, 
        expected_status: CallStatus, 
        new_status: CallStatus, 
        notes: str = ""
    ) -> bool:
        """
        Atomically update call status only if current status matches expected
        
        Args:
            call_id: Call ID to update
            expected_status: Expected current status
            new_status: New status to set
            notes: Optional notes to add
            
        Returns:
            True if update succeeded, False if status didn't match
        """
        return self.atomic_ops.conditional_status_update(
            call_id, 
            expected_status.value, 
            new_status.value, 
            notes
        )