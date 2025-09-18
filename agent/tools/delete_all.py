#!/usr/bin/env python3
"""
Delete All Conversations Tool

Safely removes ALL conversations/sessions from the database.
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

from shared.redis_database import get_database, close_database


async def list_all_sessions():
    """List all sessions before deletion"""

    try:
        db = await get_database()
        all_sessions = []

        # Get all session keys from Redis
        async for key in db.client.scan_iter(match="session:*"):
            session_data = await db.client.get(key)
            if session_data:
                import json
                session = json.loads(session_data) if isinstance(session_data, str) else session_data

                session_id = session.get('session_id', '')
                transcript = session.get('transcript', [])
                instructions = session.get('collected_instructions', [])
                created_at_str = session.get('created_at')

                all_sessions.append({
                    'session_id': session_id,
                    'timestamp': session.get('timestamp'),
                    'created_at': datetime.fromisoformat(created_at_str) if created_at_str else None,
                    'patient_name': session.get('patient_name'),
                    'is_evaluation': session.get('is_evaluation', False),
                    'message_count': len(transcript),
                    'instruction_count': len(instructions)
                })

        # Sort by created_at DESC
        all_sessions.sort(key=lambda x: x['created_at'] or datetime.min, reverse=True)
        return all_sessions

    except Exception as e:
        print(f"❌ Failed to list sessions: {e}")
        return []


async def delete_all_sessions(session_ids):
    """Delete all specified sessions"""

    try:
        db = await get_database()

        deleted_count = 0
        for session_id in session_ids:
            try:
                # Delete session from Redis
                result = await db.delete_session(session_id)
                if result:
                    deleted_count += 1
                    print(f"   ✅ Deleted: {session_id}")
                else:
                    print(f"   ⚠️  Not found: {session_id}")
            except Exception as e:
                print(f"   ❌ Failed to delete {session_id}: {e}")

        return deleted_count

    except Exception as e:
        print(f"❌ Failed to delete sessions: {e}")
        return 0


def confirm_deletion(sessions):
    """Ask user for confirmation before deletion"""

    if not sessions:
        print("ℹ️  No conversations found to delete.")
        return False

    print(f"\n⚠️  WARNING: About to delete ALL {len(sessions)} conversations")
    print("=" * 70)
    print(f"{'Session ID':<35} {'Created':<19} {'Patient':<15} {'Messages'}")
    print("-" * 70)

    for session in sessions:
        session_id = session['session_id']
        created_at = session['created_at'].strftime("%Y-%m-%d %H:%M:%S") if session['created_at'] else "Unknown"
        patient_name = session['patient_name'] or "Unknown"
        msg_count = session['message_count'] if session['message_count'] is not None else 0
        eval_marker = " [EVAL]" if session['is_evaluation'] else ""

        print(f"{session_id:<35} {created_at:<19} {patient_name:<15} {msg_count}{eval_marker}")

    print(f"\n🚨 This action cannot be undone!")
    print("   This will delete ALL conversations including:")
    print("   - Patient conversations")
    print("   - Evaluation sessions")
    print("   - All transcript data")
    print("   - All collected instructions")

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
        print("🗑️  DELETE ALL CONVERSATIONS TOOL")
        print("=" * 50)

        # Step 1: List all sessions
        print("📋 Scanning for all conversations...")
        all_sessions = await list_all_sessions()

        if not all_sessions:
            print("✅ No conversations found in database.")
            return True

        # Step 2: Show what will be deleted and confirm
        if not confirm_deletion(all_sessions):
            print("❌ Deletion cancelled by user.")
            return False

        # Step 3: Perform deletion
        print(f"\n🗑️  Deleting {len(all_sessions)} conversations...")
        session_ids = [s['session_id'] for s in all_sessions]
        deleted_count = await delete_all_sessions(session_ids)

        # Step 4: Report results
        print(f"\n📊 DELETION RESULTS")
        print("=" * 30)
        print(f"Conversations targeted: {len(all_sessions)}")
        print(f"Successfully deleted: {deleted_count}")
        print(f"Failed to delete: {len(all_sessions) - deleted_count}")

        if deleted_count == len(all_sessions):
            print(f"\n✅ All conversations deleted successfully!")
        elif deleted_count > 0:
            print(f"\n⚠️  Partial success: {deleted_count}/{len(all_sessions)} conversations deleted")
        else:
            print(f"\n❌ No conversations were deleted")

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