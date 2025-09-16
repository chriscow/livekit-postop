"""
Database module for PostOp AI session and transcript storage

Provides PostgreSQL storage for session data and conversation transcripts.
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
import asyncpg
from asyncpg import Pool, Connection

logger = logging.getLogger("postop-agent")


class SessionDatabase:
    """Handles PostgreSQL storage for PostOp AI sessions"""

    def __init__(self, database_url: str = None):
        """
        Initialize database connection

        Args:
            database_url: PostgreSQL connection string (defaults to DATABASE_URL env var)
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        self.pool: Optional[Pool] = None

    async def initialize(self):
        """Initialize database connection pool and create tables if needed"""
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )

            # Create tables if they don't exist
            await self._create_tables()
            logger.info("[DATABASE] Initialized PostgreSQL connection pool")

        except Exception as e:
            logger.error(f"[DATABASE] Failed to initialize: {e}")
            raise

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("[DATABASE] Closed connection pool")

    async def _create_tables(self):
        """Create database tables if they don't exist"""
        create_sessions_table = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id VARCHAR(255) PRIMARY KEY,
            timestamp VARCHAR(255),
            patient_name VARCHAR(255),
            patient_language VARCHAR(100),
            transcript JSONB NOT NULL DEFAULT '[]',
            collected_instructions JSONB DEFAULT '[]',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_timestamp ON sessions(timestamp);
        CREATE INDEX IF NOT EXISTS idx_sessions_patient_name ON sessions(patient_name);
        CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_transcript_gin ON sessions USING GIN(transcript);
        """

        async with self.pool.acquire() as conn:
            await conn.execute(create_sessions_table)
            logger.info("[DATABASE] Created/verified sessions table")

    async def save_session(
        self,
        session_id: str,
        timestamp: str,
        patient_name: Optional[str] = None,
        patient_language: Optional[str] = None,
        transcript: List[Dict[str, Any]] = None,
        collected_instructions: List[Dict[str, Any]] = None
    ) -> bool:
        """
        Save or update session data in PostgreSQL

        Args:
            session_id: Unique session identifier
            timestamp: Session start timestamp
            patient_name: Patient's name (optional)
            patient_language: Patient's preferred language (optional)
            transcript: OpenAI format conversation messages (JSONB)
            collected_instructions: Captured discharge instructions (JSONB)

        Returns:
            True if successful, False otherwise
        """
        if transcript is None:
            transcript = []
        if collected_instructions is None:
            collected_instructions = []

        try:
            insert_query = """
            INSERT INTO sessions (
                session_id, timestamp, patient_name, patient_language,
                transcript, collected_instructions, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (session_id)
            DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                patient_name = EXCLUDED.patient_name,
                patient_language = EXCLUDED.patient_language,
                transcript = EXCLUDED.transcript,
                collected_instructions = EXCLUDED.collected_instructions,
                updated_at = NOW()
            """

            async with self.pool.acquire() as conn:
                await conn.execute(
                    insert_query,
                    session_id,
                    timestamp,
                    patient_name,
                    patient_language,
                    json.dumps(transcript),
                    json.dumps(collected_instructions)
                )

            logger.info(f"[DATABASE] Saved session {session_id}")
            return True

        except Exception as e:
            logger.error(f"[DATABASE] Failed to save session {session_id}: {e}")
            return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data from PostgreSQL

        Args:
            session_id: Session identifier

        Returns:
            Session data dictionary or None if not found
        """
        try:
            query = """
            SELECT session_id, timestamp, patient_name, patient_language,
                   transcript, collected_instructions, created_at, updated_at
            FROM sessions
            WHERE session_id = $1
            """

            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, session_id)

            if row:
                return {
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "patient_name": row["patient_name"],
                    "patient_language": row["patient_language"],
                    "transcript": json.loads(row["transcript"]) if row["transcript"] else [],
                    "collected_instructions": json.loads(row["collected_instructions"]) if row["collected_instructions"] else [],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None

        except Exception as e:
            logger.error(f"[DATABASE] Failed to get session {session_id}: {e}")
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
            query = """
            SELECT session_id, timestamp, patient_name, patient_language,
                   jsonb_array_length(transcript) as message_count,
                   jsonb_array_length(collected_instructions) as instruction_count,
                   created_at, updated_at
            FROM sessions
            ORDER BY created_at DESC
            LIMIT $1
            """

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit)

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"[DATABASE] Failed to list sessions: {e}")
            return []


# Global database instance
_db_instance: Optional[SessionDatabase] = None


async def get_database() -> SessionDatabase:
    """Get or create global database instance"""
    global _db_instance

    if _db_instance is None:
        _db_instance = SessionDatabase()
        await _db_instance.initialize()

    return _db_instance


async def close_database():
    """Close global database instance"""
    global _db_instance

    if _db_instance:
        await _db_instance.close()
        _db_instance = None