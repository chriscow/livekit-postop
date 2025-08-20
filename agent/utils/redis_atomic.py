"""
Atomic Redis operations for PostOp AI system

Provides Lua scripts and atomic operations to prevent race conditions
in multi-worker environments, particularly for call scheduling and status updates.
"""
import redis
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("redis-atomic")

# Lua script for atomic dequeue of due calls
DEQUEUE_DUE_CALLS_SCRIPT = """
-- Get due call IDs
local due_calls = redis.call('ZRANGEBYSCORE', KEYS[1], 0, ARGV[1], 'LIMIT', 0, ARGV[2])

-- For each due call, check if it's still pending and claim it
local claimed_calls = {}
for i = 1, #due_calls do
    local call_id = due_calls[i]
    local call_key = KEYS[2] .. call_id
    
    -- Get current status
    local current_status = redis.call('HGET', call_key, 'status')
    
    -- Only claim if still pending
    if current_status == 'pending' then
        -- Atomically update status to in_progress
        redis.call('HSET', call_key, 'status', 'in_progress')
        redis.call('HSET', call_key, 'updated_at', ARGV[3])
        
        -- Remove from due calls index
        redis.call('ZREM', KEYS[1], call_id)
        
        -- Add to claimed list
        table.insert(claimed_calls, call_id)
    end
end

return claimed_calls
"""

# Lua script for atomic attempt count increment
INCREMENT_ATTEMPT_SCRIPT = """
-- Increment attempt count and update timestamp
local call_key = KEYS[1]
local new_count = redis.call('HINCRBY', call_key, 'attempt_count', 1)
redis.call('HSET', call_key, 'updated_at', ARGV[1])

-- Check if max attempts reached
local max_attempts = redis.call('HGET', call_key, 'max_attempts')
if max_attempts and tonumber(new_count) >= tonumber(max_attempts) then
    -- Mark as failed if max attempts reached
    redis.call('HSET', call_key, 'status', 'failed')
    redis.call('HSET', call_key, 'notes', 'Max retry attempts reached')
    return {new_count, 'max_reached'}
else
    -- Reset to pending for retry
    redis.call('HSET', call_key, 'status', 'pending')
    -- Re-add to due calls index with original scheduled time
    local scheduled_time = redis.call('HGET', call_key, 'scheduled_time')
    if scheduled_time then
        local timestamp = redis.call('EVAL', 'return os.time()', 0)
        redis.call('ZADD', KEYS[2], timestamp, ARGV[2])
    end
    return {new_count, 'retry'}
end
"""

# Lua script for atomic status update with conditions
CONDITIONAL_STATUS_UPDATE_SCRIPT = """
-- Update status only if current status matches expected
local call_key = KEYS[1]
local expected_status = ARGV[1]
local new_status = ARGV[2]
local timestamp = ARGV[3]
local notes = ARGV[4]

local current_status = redis.call('HGET', call_key, 'status')

if current_status == expected_status then
    redis.call('HSET', call_key, 'status', new_status)
    redis.call('HSET', call_key, 'updated_at', timestamp)
    if notes and notes ~= '' then
        redis.call('HSET', call_key, 'notes', notes)
    end
    
    -- Remove from due calls index if completing
    if new_status == 'completed' or new_status == 'failed' or new_status == 'cancelled' then
        redis.call('ZREM', KEYS[2], ARGV[5])  -- call_id
    end
    
    return 1  -- Success
else
    return 0  -- Status mismatch
end
"""

# Lua script for cleanup old completed calls
CLEANUP_OLD_CALLS_SCRIPT = """
-- Find old completed/failed calls and move them to archive
local calls_pattern = KEYS[1] .. '*'
local cutoff_timestamp = ARGV[1]
local archive_key = KEYS[2]
local records_key = KEYS[3]

local archived_count = 0
local keys = redis.call('KEYS', calls_pattern)

for i = 1, #keys do
    local call_key = keys[i]
    local status = redis.call('HGET', call_key, 'status')
    local updated_at = redis.call('HGET', call_key, 'updated_at')
    
    -- Check if call is completed/failed and old enough
    if (status == 'completed' or status == 'failed' or status == 'cancelled') and 
       updated_at and updated_at < cutoff_timestamp then
        
        -- Get call data
        local call_data = redis.call('HGETALL', call_key)
        
        -- Store in archive (as JSON string)
        local call_id = string.match(call_key, '[^:]+$')
        redis.call('HSET', archive_key, call_id, cjson.encode(call_data))
        
        -- Delete original call
        redis.call('DEL', call_key)
        
        -- Clean up related records
        local patient_id = ''
        for j = 1, #call_data, 2 do
            if call_data[j] == 'patient_id' then
                patient_id = call_data[j + 1]
                break
            end
        end
        
        if patient_id ~= '' then
            redis.call('SREM', KEYS[1] .. ':patient:' .. patient_id, call_id)
        end
        
        archived_count = archived_count + 1
    end
end

return archived_count
"""


class AtomicRedisOperations:
    """
    Provides atomic Redis operations to prevent race conditions
    """
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize with Redis client
        
        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        self.calls_key = "postop:scheduled_calls"
        self.calls_by_time_key = f"{self.calls_key}:by_time"
        
        # Register Lua scripts
        self._dequeue_script = self.redis.register_script(DEQUEUE_DUE_CALLS_SCRIPT)
        self._increment_script = self.redis.register_script(INCREMENT_ATTEMPT_SCRIPT)
        self._status_update_script = self.redis.register_script(CONDITIONAL_STATUS_UPDATE_SCRIPT)
        self._cleanup_script = self.redis.register_script(CLEANUP_OLD_CALLS_SCRIPT)
    
    def dequeue_due_calls(self, current_timestamp: float, limit: int = 50) -> List[str]:
        """
        Atomically dequeue due calls and mark them as in_progress
        
        Args:
            current_timestamp: Current timestamp (due calls before this time)
            limit: Maximum number of calls to dequeue
            
        Returns:
            List of call IDs that were successfully claimed
        """
        try:
            current_iso = datetime.utcfromtimestamp(current_timestamp).isoformat()
            
            claimed_calls = self._dequeue_script(
                keys=[self.calls_by_time_key, f"{self.calls_key}:"],
                args=[current_timestamp, limit, current_iso]
            )
            
            logger.info(f"Atomically claimed {len(claimed_calls)} due calls")
            return claimed_calls
            
        except Exception as e:
            logger.error(f"Error in atomic dequeue: {e}")
            return []
    
    def increment_attempt_with_retry_logic(
        self, 
        call_id: str, 
        max_attempts: int
    ) -> Tuple[int, str]:
        """
        Atomically increment attempt count and handle retry logic
        
        Args:
            call_id: Call ID to increment
            max_attempts: Maximum allowed attempts
            
        Returns:
            Tuple of (new_attempt_count, action) where action is 'retry' or 'max_reached'
        """
        try:
            current_iso = datetime.utcnow().isoformat()
            call_key = f"{self.calls_key}:{call_id}"
            
            result = self._increment_script(
                keys=[call_key, self.calls_by_time_key],
                args=[current_iso, call_id]
            )
            
            attempt_count, action = result
            logger.info(f"Call {call_id} attempt incremented to {attempt_count}, action: {action}")
            
            return int(attempt_count), action
            
        except Exception as e:
            logger.error(f"Error incrementing attempt for call {call_id}: {e}")
            return 0, 'error'
    
    def conditional_status_update(
        self, 
        call_id: str, 
        expected_status: str, 
        new_status: str, 
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
        try:
            current_iso = datetime.utcnow().isoformat()
            call_key = f"{self.calls_key}:{call_id}"
            
            result = self._status_update_script(
                keys=[call_key, self.calls_by_time_key],
                args=[expected_status, new_status, current_iso, notes, call_id]
            )
            
            success = bool(result)
            if success:
                logger.info(f"Status updated for call {call_id}: {expected_status} -> {new_status}")
            else:
                logger.warning(f"Status update failed for call {call_id}: expected {expected_status} but found different status")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating status for call {call_id}: {e}")
            return False
    
    def cleanup_old_calls(self, days_old: int = 30) -> int:
        """
        Archive and cleanup old completed/failed calls
        
        Args:
            days_old: Archive calls older than this many days
            
        Returns:
            Number of calls archived
        """
        try:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            cutoff_iso = cutoff_date.isoformat()
            
            archived_count = self._cleanup_script(
                keys=[
                    f"{self.calls_key}:",  # Pattern for call keys
                    f"{self.calls_key}:archive",  # Archive storage
                    f"postop:call_records:"  # Records pattern
                ],
                args=[cutoff_iso]
            )
            
            logger.info(f"Archived {archived_count} old calls (older than {days_old} days)")
            return archived_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old calls: {e}")
            return 0
    
    def get_call_with_lock(self, call_id: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Get call data with distributed lock to prevent concurrent modifications
        
        Args:
            call_id: Call ID to retrieve
            timeout: Lock timeout in seconds
            
        Returns:
            Call data dictionary if successful, None otherwise
        """
        lock_key = f"{self.calls_key}:lock:{call_id}"
        call_key = f"{self.calls_key}:{call_id}"
        
        try:
            # Try to acquire lock
            lock_acquired = self.redis.set(lock_key, "locked", nx=True, ex=timeout)
            
            if not lock_acquired:
                logger.warning(f"Could not acquire lock for call {call_id}")
                return None
            
            # Get call data
            call_data = self.redis.hgetall(call_key)
            
            if not call_data:
                logger.warning(f"Call {call_id} not found")
                return None
            
            return call_data
            
        except Exception as e:
            logger.error(f"Error getting call {call_id} with lock: {e}")
            return None
        finally:
            # Always release lock
            try:
                self.redis.delete(lock_key)
            except Exception as e:
                logger.error(f"Error releasing lock for call {call_id}: {e}")
    
    def batch_schedule_calls(self, calls_data: List[Dict[str, Any]]) -> int:
        """
        Atomically schedule multiple calls in a single transaction
        
        Args:
            calls_data: List of call data dictionaries
            
        Returns:
            Number of calls successfully scheduled
        """
        if not calls_data:
            return 0
            
        pipe = self.redis.pipeline()
        scheduled_count = 0
        
        try:
            for call_data in calls_data:
                call_id = call_data.get('id')
                if not call_id:
                    continue
                
                # Convert None values to empty strings for Redis
                redis_data = {k: (v if v is not None else "") for k, v in call_data.items()}
                
                # Store call data
                call_key = f"{self.calls_key}:{call_id}"
                pipe.hset(call_key, mapping=redis_data)
                
                # Add to time index
                scheduled_time = call_data.get('scheduled_time')
                if scheduled_time:
                    if isinstance(scheduled_time, datetime):
                        timestamp = scheduled_time.timestamp()
                    else:
                        timestamp = datetime.fromisoformat(scheduled_time).timestamp()
                    
                    pipe.zadd(self.calls_by_time_key, {call_id: timestamp})
                
                # Add to patient index
                patient_id = call_data.get('patient_id')
                if patient_id:
                    pipe.sadd(f"{self.calls_key}:patient:{patient_id}", call_id)
                
                scheduled_count += 1
            
            # Execute all operations atomically
            pipe.execute()
            
            logger.info(f"Batch scheduled {scheduled_count} calls atomically")
            return scheduled_count
            
        except Exception as e:
            logger.error(f"Error in batch scheduling: {e}")
            return 0


def create_atomic_redis_ops(redis_client: redis.Redis = None) -> AtomicRedisOperations:
    """
    Factory function to create AtomicRedisOperations instance
    
    Args:
        redis_client: Redis client instance (defaults to creating new one)
        
    Returns:
        AtomicRedisOperations instance
    """
    if redis_client is None:
        from config.redis import create_redis_connection
        redis_client = create_redis_connection()
    
    return AtomicRedisOperations(redis_client)