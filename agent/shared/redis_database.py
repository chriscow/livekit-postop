"""
Redis Database module for PostOp AI session and transcript storage

Provides Redis storage for session data and conversation transcripts.
Simple implementation using redis-py with JSON serialization.
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
import redis.asyncio as redis

logger = logging.getLogger("postop-agent")


class SessionRedisDatabase:
    """Handles Redis storage for PostOp AI sessions"""

    def __init__(self, redis_url: str = None):
        """
        Initialize Redis connection

        Args:
            redis_url: Redis connection string (defaults to REDIS_URL env var)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        if not self.redis_url:
            raise ValueError("REDIS_URL environment variable not set")

        self.client = None

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            # Create Redis client
            self.client = redis.from_url(self.redis_url, decode_responses=True)

            # Test connection
            response = await self.client.ping()
            if not response:
                raise Exception("Redis ping failed")
            logger.info("[REDIS] Successfully connected to Redis")

        except Exception as e:
            logger.error(f"[REDIS] Failed to initialize: {e}")
            raise

    async def close(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            logger.info("[REDIS] Closed connection")

    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for session"""
        return f"session:{session_id}"

    async def save_session(
        self,
        session_id: str,
        timestamp: str,
        patient_name: Optional[str] = None,
        patient_language: Optional[str] = None,
        transcript: List[Dict[str, Any]] = None,
        collected_instructions: List[Dict[str, Any]] = None,
        is_evaluation: bool = False,
        source_session_id: Optional[str] = None,
        evaluation_metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Save or update session data in Redis

        Args:
            session_id: Unique session identifier
            timestamp: Session start timestamp
            patient_name: Patient's name (optional)
            patient_language: Patient's preferred language (optional)
            transcript: OpenAI format conversation messages
            collected_instructions: Captured discharge instructions
            is_evaluation: Whether this is an evaluation run (default: False)
            source_session_id: Original session ID if this is an evaluation (optional)
            evaluation_metadata: Additional metadata for evaluation runs (optional)

        Returns:
            True if successful, False otherwise
        """
        if transcript is None:
            transcript = []
        if collected_instructions is None:
            collected_instructions = []
        if evaluation_metadata is None:
            evaluation_metadata = {}

        try:
            session_data = {
                "session_id": session_id,
                "timestamp": timestamp,
                "patient_name": patient_name,
                "patient_language": patient_language,
                "transcript": transcript,
                "collected_instructions": collected_instructions,
                "is_evaluation": is_evaluation,
                "source_session_id": source_session_id,
                "evaluation_metadata": evaluation_metadata,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            # Store as JSON string in Redis
            key = self._session_key(session_id)
            await self.client.set(key, json.dumps(session_data))

            logger.info(f"[REDIS] Saved session {session_id}")
            return True

        except Exception as e:
            logger.error(f"[REDIS] Failed to save session {session_id}: {e}")
            return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data from Redis

        Args:
            session_id: Session identifier

        Returns:
            Session data dictionary or None if not found
        """
        try:
            key = self._session_key(session_id)
            data = await self.client.get(key)

            if data:
                session_data = json.loads(data)
                # Convert created_at/updated_at strings back to datetime objects for compatibility
                if session_data.get("created_at"):
                    session_data["created_at"] = datetime.fromisoformat(session_data["created_at"])
                if session_data.get("updated_at"):
                    session_data["updated_at"] = datetime.fromisoformat(session_data["updated_at"])
                return session_data

            return None

        except Exception as e:
            logger.error(f"[REDIS] Failed to get session {session_id}: {e}")
            return None

    async def list_recent_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get list of recent sessions

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session summaries
        """
        try:
            # Find all session keys
            keys = []
            async for key in self.client.scan_iter(match="session:*"):
                keys.append(key)

            # Get all session data
            sessions = []
            for key in keys:
                data = await self.client.get(key)
                if data and data.strip():  # Check that data is not empty
                    try:
                        session_data = json.loads(data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[REDIS] Failed to parse session data for key {key}: {e}")
                        continue
                    # Calculate message and instruction counts
                    transcript = session_data.get("transcript", [])
                    instructions = session_data.get("collected_instructions", [])

                    # Convert datetime strings for sorting
                    created_at_str = session_data.get("created_at")
                    if created_at_str:
                        created_at = datetime.fromisoformat(created_at_str)
                    else:
                        created_at = datetime.now()

                    session_summary = {
                        "session_id": session_data.get("session_id"),
                        "timestamp": session_data.get("timestamp"),
                        "patient_name": session_data.get("patient_name"),
                        "patient_language": session_data.get("patient_language"),
                        "message_count": len(transcript),
                        "instruction_count": len(instructions),
                        "created_at": created_at,
                        "updated_at": datetime.fromisoformat(session_data.get("updated_at", created_at_str))
                    }
                    sessions.append(session_summary)

            # Sort by created_at (most recent first) and limit
            sessions.sort(key=lambda x: x["created_at"], reverse=True)
            return sessions[:limit]

        except Exception as e:
            logger.error(f"[REDIS] Failed to list sessions: {e}")
            return []

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from Redis

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if not found or error
        """
        try:
            key = self._session_key(session_id)
            result = await self.client.delete(key)

            if result > 0:
                logger.info(f"[REDIS] Deleted session {session_id}")
                return True
            else:
                logger.warning(f"[REDIS] Session {session_id} not found for deletion")
                return False

        except Exception as e:
            logger.error(f"[REDIS] Failed to delete session {session_id}: {e}")
            return False


# Global database instance
_redis_db_instance: Optional[SessionRedisDatabase] = None


async def get_redis_database() -> SessionRedisDatabase:
    """Get or create global Redis database instance"""
    global _redis_db_instance

    if _redis_db_instance is None:
        _redis_db_instance = SessionRedisDatabase()
        await _redis_db_instance.initialize()

    return _redis_db_instance


async def close_redis_database():
    """Close global Redis database instance"""
    global _redis_db_instance

    if _redis_db_instance:
        try:
            await _redis_db_instance.close()
        except Exception as e:
            logger.error(f"Error closing Redis database during cleanup: {e}")
        finally:
            _redis_db_instance = None


def close_redis_database_sync():
    """Synchronous Redis database cleanup for signal handlers"""
    global _redis_db_instance

    if _redis_db_instance and _redis_db_instance.client:
        try:
            # Force close Redis connection
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_redis_db_instance.client.close())
            except RuntimeError:
                # No running loop, force close
                try:
                    if hasattr(_redis_db_instance.client, 'connection_pool'):
                        _redis_db_instance.client.connection_pool.disconnect()
                except:
                    pass
        except Exception:
            # Ignore all errors during forced cleanup
            pass
        finally:
            _redis_db_instance = None


# Compatibility function for existing code
async def get_database() -> SessionRedisDatabase:
    """Compatibility function - returns Redis database instance"""
    return await get_redis_database()


async def close_database():
    """Compatibility function - closes Redis database"""
    await close_redis_database()


def close_database_sync():
    """Compatibility function - synchronous cleanup"""
    close_redis_database_sync()