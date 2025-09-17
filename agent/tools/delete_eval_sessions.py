#!/usr/bin/env python3
"""
Delete Evaluation Sessions Tool

Safely removes all evaluation sessions from the database.
Provides confirmation prompts and detailed reporting.
"""

import os
import sys
import asyncio
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from shared.database import get_database, close_database


async def list_eval_sessions():
    """List all evaluation sessions before deletion"""

    try:
        db = await get_database()

        # Get all evaluation sessions
        query = """
        SELECT session_id, timestamp, created_at, is_evaluation, source_session_id,
               jsonb_array_length(transcript) as message_count,
               jsonb_array_length(collected_instructions) as instruction_count
        FROM sessions
        WHERE session_id LIKE 'eval_%' OR is_evaluation = true
        ORDER BY created_at DESC
        """

        async with db.pool.acquire() as conn:
            eval_sessions = await conn.fetch(query)

        return eval_sessions

    except Exception as e:
        print(f"❌ Failed to list evaluation sessions: {e}")
        return []


async def delete_eval_sessions(session_ids):
    """Delete specific evaluation sessions"""

    try:
        db = await get_database()

        deleted_count = 0
        async with db.pool.acquire() as conn:
            for session_id in session_ids:
                try:
                    result = await conn.execute(
                        "DELETE FROM sessions WHERE session_id = $1",
                        session_id
                    )
                    # Extract number from result like "DELETE 1"
                    rows_affected = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
                    if rows_affected > 0:
                        deleted_count += 1
                        print(f"   ✅ Deleted: {session_id}")
                    else:
                        print(f"   ⚠️  Not found: {session_id}")
                except Exception as e:
                    print(f"   ❌ Failed to delete {session_id}: {e}")

        return deleted_count

    except Exception as e:
        print(f"❌ Failed to delete evaluation sessions: {e}")
        return 0


def confirm_deletion(sessions):
    """Ask user for confirmation before deletion"""

    if not sessions:
        print("ℹ️  No evaluation sessions found to delete.")
        return False

    print(f"\n⚠️  WARNING: About to delete {len(sessions)} evaluation sessions")
    print("=" * 60)
    print(f"{'Session ID':<35} {'Created':<19} {'Messages'}")
    print("-" * 60)

    for session in sessions:
        session_id = session['session_id']
        created_at = session['created_at'].strftime("%Y-%m-%d %H:%M:%S") if session['created_at'] else "Unknown"
        msg_count = session['message_count'] if session['message_count'] is not None else 0

        print(f"{session_id:<35} {created_at:<19} {msg_count}")

    print(f"\n🚨 This action cannot be undone!")

    while True:
        response = input("\nDo you want to proceed? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            return False
        else:
            print("Please enter 'yes' or 'no'")


async def main():
    """Main deletion workflow with safety checks"""

    try:
        print("🗑️  EVALUATION SESSION DELETION TOOL")
        print("=" * 50)

        # Step 1: List all evaluation sessions
        print("📋 Scanning for evaluation sessions...")
        eval_sessions = await list_eval_sessions()

        if not eval_sessions:
            print("✅ No evaluation sessions found in database.")
            return True

        # Step 2: Show what will be deleted and confirm
        if not confirm_deletion(eval_sessions):
            print("❌ Deletion cancelled by user.")
            return False

        # Step 3: Perform deletion
        print(f"\n🗑️  Deleting {len(eval_sessions)} evaluation sessions...")
        session_ids = [s['session_id'] for s in eval_sessions]
        deleted_count = await delete_eval_sessions(session_ids)

        # Step 4: Report results
        print(f"\n📊 DELETION RESULTS")
        print("=" * 30)
        print(f"Sessions targeted: {len(eval_sessions)}")
        print(f"Successfully deleted: {deleted_count}")
        print(f"Failed to delete: {len(eval_sessions) - deleted_count}")

        if deleted_count == len(eval_sessions):
            print(f"\n✅ All evaluation sessions deleted successfully!")
        elif deleted_count > 0:
            print(f"\n⚠️  Partial success: {deleted_count}/{len(eval_sessions)} sessions deleted")
        else:
            print(f"\n❌ No sessions were deleted")

        return deleted_count > 0

    except Exception as e:
        print(f"❌ Deletion failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await close_database()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)