#!/usr/bin/env python3
"""
Session List Tool for PostOp AI

Lists database sessions with human-readable timestamps and message counts,
ordered by most recent first. Useful for finding sessions to replay in chat mode.

Usage:
    python list_sessions.py [--limit N] [--detailed]

Examples:
    python list_sessions.py                    # List 20 most recent sessions
    python list_sessions.py --limit 50         # List 50 most recent sessions
    python list_sessions.py --detailed         # Include patient info and instruction counts
"""

import os
import sys
import asyncio
import argparse
from datetime import datetime
from typing import Optional

# Add parent directory to path so we can import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from shared.database import get_database, close_database


def format_timestamp(timestamp_str: str, created_at: Optional[datetime] = None) -> str:
    """
    Format timestamp to human-readable string

    Args:
        timestamp_str: Session timestamp string (e.g., "20250117_143022")
        created_at: Database created_at timestamp (fallback)

    Returns:
        Human-readable timestamp string
    """
    try:
        # Try to parse the session timestamp format (YYYYMMDD_HHMMSS)
        if timestamp_str and len(timestamp_str) >= 13:
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass

    # Fallback to database created_at timestamp
    if created_at:
        return created_at.strftime("%Y-%m-%d %H:%M:%S")

    return "Unknown"


def format_session_row(session: dict, detailed: bool = False) -> str:
    """
    Format a single session row for display

    Args:
        session: Session data dictionary
        detailed: Whether to include detailed information

    Returns:
        Formatted string for the session
    """
    session_id = session.get("session_id", "Unknown")
    timestamp_str = session.get("timestamp", "")
    created_at = session.get("created_at")
    message_count = session.get("message_count", 0)

    # Format the basic info
    formatted_time = format_timestamp(timestamp_str, created_at)
    basic_info = f"{session_id:<25} {formatted_time:<19} {message_count:>8} msgs"

    if not detailed:
        return basic_info

    # Add detailed information
    patient_name = session.get("patient_name") or "Unknown"
    patient_language = session.get("patient_language") or "Unknown"
    instruction_count = session.get("instruction_count", 0)

    detailed_info = f" | {patient_name:<15} {patient_language:<8} {instruction_count:>3} instr"
    return basic_info + detailed_info


async def list_sessions(limit: int = 20, detailed: bool = False):
    """
    List recent sessions from the database

    Args:
        limit: Maximum number of sessions to display
        detailed: Whether to show detailed information
    """
    try:
        # Get database connection
        db = await get_database()

        # Fetch recent sessions
        sessions = await db.list_recent_sessions(limit=limit)

        if not sessions:
            print("No sessions found in database.")
            return

        # Print header
        print(f"\nFound {len(sessions)} recent sessions:\n")

        if detailed:
            print(f"{'Session ID':<25} {'Date/Time':<19} {'Messages':>8} | {'Patient':<15} {'Language':<8} {'Instr':>3}")
            print("-" * 90)
        else:
            print(f"{'Session ID':<25} {'Date/Time':<19} {'Messages':>8}")
            print("-" * 55)

        # Print each session
        for session in sessions:
            print(format_session_row(session, detailed))

        print(f"\nUse 'python agents.py chat <session_id>' to replay any session")

    except Exception as e:
        print(f"Error listing sessions: {e}", file=sys.stderr)
        return 1

    finally:
        # Clean up database connection
        await close_database()

    return 0


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="List PostOp AI database sessions with timestamps and message counts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    List 20 most recent sessions
  %(prog)s --limit 50         List 50 most recent sessions
  %(prog)s --detailed         Include patient names and instruction counts
  %(prog)s -l 100 -d          List 100 sessions with full details
        """
    )

    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Maximum number of sessions to display (default: 20)"
    )

    parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="Show detailed information including patient names and instruction counts"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.limit <= 0:
        print("Error: --limit must be a positive integer", file=sys.stderr)
        return 1

    if args.limit > 1000:
        print("Warning: Large limits may be slow. Consider using a smaller value.", file=sys.stderr)

    # Check database configuration
    if not os.getenv("DATABASE_URL"):
        print("Error: DATABASE_URL environment variable not set", file=sys.stderr)
        print("Please configure your PostgreSQL connection string", file=sys.stderr)
        return 1

    # Run the session listing
    try:
        return asyncio.run(list_sessions(args.limit, args.detailed))
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())