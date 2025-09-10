"""
Shared utilities package for PostOp AI system

Contains shared utilities used by multiple workflows:
- email_service: Email functionality for sending summaries
"""

from .email_service import send_instruction_summary_email

__all__ = [
    'send_instruction_summary_email'
]