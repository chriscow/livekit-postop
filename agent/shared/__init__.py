"""
Shared utilities package for PostOp AI system

Contains shared utilities used by multiple workflows:
- email_service: Email functionality for sending summaries
- database: PostgreSQL storage for sessions and transcripts
"""

from .email_service import send_instruction_summary_email
from .database import get_database, close_database, SessionDatabase

__all__ = [
    'send_instruction_summary_email',
    'get_database',
    'close_database',
    'SessionDatabase'
]