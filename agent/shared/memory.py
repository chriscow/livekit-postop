"""
Memory management for the PostOp AI system
Supports both Redis and in-memory fallback for demo purposes
"""
import redis
import json
import logging
from typing import Any, Dict
from datetime import datetime
from discharge.config import REDIS_URL
from discharge.discharge_orders import DISCHARGE_ORDERS, SELECTED_DISCHARGE_ORDERS

logger = logging.getLogger("postop-agent")

class RedisMemory:
    def __init__(self):
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis successfully")
        except (redis.ConnectionError, redis.RedisError) as e:
            logger.error(f"Redis connection failed: {e}")
            raise RuntimeError(f"Redis is required but unavailable: {e}") from e
    
    def store_patient_data(self, phone_number: str, key: str, value: Any):
        """Store patient data in Redis"""
        patient_key = f"patient:{phone_number}:{key}"
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        elif isinstance(value, bool):
            value = str(value)  # Convert boolean to string for Redis
        self.redis_client.set(patient_key, value)
    
    def get_patient_data(self, phone_number: str, key: str):
        """Retrieve patient data from Redis"""
        patient_key = f"patient:{phone_number}:{key}"
        value = self.redis_client.get(patient_key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Handle boolean conversion
                if value == "True":
                    return True
                elif value == "False":
                    return False
                return value
        return None
    
    def store_session_data(self, session_id: str, key: str, value: Any, append: bool = False):
        """Store session data in Redis"""
        session_key = f"session:{session_id}:{key}"
        
        if append:
            # Append to a list in Redis
            if isinstance(value, str):
                # Create a timestamped entry for conversation logs
                timestamped_value = {
                    "timestamp": datetime.now().isoformat(),
                    "content": value
                }
                self.redis_client.lpush(session_key, json.dumps(timestamped_value))
            else:
                self.redis_client.lpush(session_key, json.dumps(value))
        else:
            # Regular set operation
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif isinstance(value, bool):
                value = str(value)  # Convert boolean to string for Redis
            self.redis_client.set(session_key, value)
    
    def get_session_data(self, session_id: str, key: str):
        """Retrieve session data from Redis"""
        session_key = f"session:{session_id}:{key}"
        
        # Check if this is a list (conversation log)
        if self.redis_client.type(session_key) == 'list':
            # Get all entries from the list
            entries = self.redis_client.lrange(session_key, 0, -1)
            return [json.loads(entry) for entry in entries]
        
        # Regular get operation
        value = self.redis_client.get(session_key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Handle boolean conversion
                if value == "True":
                    return True
                elif value == "False":
                    return False
                return value
        return None
    
    def get_all_session_data(self, session_id: str):
        """Get all data for a session"""
        pattern = f"session:{session_id}:*"
        keys = self.redis_client.keys(pattern)
        data = {}
        for key in keys:
            field = key.split(':')[-1]
            data[field] = self.get_session_data(session_id, field)
        return data
    
    def get_all_patient_data(self, phone_number: str):
        """Get all data for a patient"""
        pattern = f"patient:{phone_number}:*"
        keys = self.redis_client.keys(pattern)
        data = {}
        for key in keys:
            field = key.split(':')[-1]
            data[field] = self.get_patient_data(phone_number, field)
        return data
    
    def get_conversation_log(self, session_id: str):
        """Get full conversation log for accountability"""
        conversation = {
            "session_id": session_id,
            "user_inputs": self.get_session_data(session_id, "user_inputs") or [],
            "maya_outputs": self.get_session_data(session_id, "maya_outputs") or [],
            "function_calls": self.get_session_data(session_id, "function_calls") or []
        }
        return conversation
    
    def store_room_person(self, session_id: str, person_name: str, relationship: str = "unknown", language: str = "English"):
        """Store information about a person present in the room"""
        person_data = {
            "name": person_name,
            "relationship": relationship,
            "language": language,
            "registered_at": datetime.now().isoformat()
        }
        
        # Get existing room people or initialize empty list
        room_people = self.get_session_data(session_id, "room_people") or []
        
        # Check for duplicates (by name)
        existing_names = [person.get("name", "").lower() for person in room_people]
        if person_name.lower() not in existing_names:
            room_people.append(person_data)
            self.store_session_data(session_id, "room_people", room_people)
            logger.info(f"Registered room person: {person_name} ({relationship}, {language}) for session {session_id}")
            return True
        else:
            logger.warning(f"Person {person_name} already registered for session {session_id}")
            return False
    
    def get_room_people(self, session_id: str):
        """Get list of all people registered in the room"""
        return self.get_session_data(session_id, "room_people") or []
    
    def get_room_person_summary(self, session_id: str) -> str:
        """Get formatted summary of people in the room"""
        room_people = self.get_room_people(session_id)
        if not room_people:
            return "No additional people registered in the room"
        
        summary_parts = []
        for person in room_people:
            name = person.get("name", "Unknown")
            relationship = person.get("relationship", "unknown")
            language = person.get("language", "English")
            summary_parts.append(f"{name} ({relationship}, speaks {language})")
        
        return f"People in room: {', '.join(summary_parts)}"

    def get_patient_summary(self, phone_number: str) -> Dict[str, Any]:
        """Get comprehensive patient summary for review"""
        if not phone_number:
            return {
                "basic_info": {"nurse_id": "Unknown", "record_number": "Unknown"},
                "discharge_tracking": {"completed_orders": [], "additional_instructions": []}
            }
        
        # Get all patient data
        all_data = self.get_all_patient_data(phone_number)
        
        return {
            "basic_info": {
                "nurse_id": all_data.get("nurse_id", "Not provided"),
                "record_number": all_data.get("record_number", "Not provided"),
                "language": all_data.get("language", "English"),
                "consent": all_data.get("consent", False)
            },
            "discharge_tracking": {
                "completed_orders": all_data.get("completed_orders", []),
                "additional_instructions": all_data.get("additional_instructions", [])
            }
        }