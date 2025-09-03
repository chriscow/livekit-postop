#!/usr/bin/env python3
"""
Clear All Conversations Tool

This script safely clears all conversation data from Redis.
It will delete:
- All conversation messages (postop:conversations:*)
- The session tracking set (postop:conversations:sessions)

Usage:
    PYTHONPATH=. uv run python tools/clear_conversations.py
"""

import os
import sys
import redis
from dotenv import load_dotenv

def main():
    """Clear all conversation data from Redis"""
    load_dotenv()
    
    # Get Redis URL from environment
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    try:
        # Connect to Redis
        print(f"🔌 Connecting to Redis at {redis_url}...")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        
        # Test connection
        redis_client.ping()
        print("✅ Redis connection successful")
        
        # Get all session IDs first for reporting
        session_ids = redis_client.smembers('postop:conversations:sessions')
        print(f"📊 Found {len(session_ids)} conversation sessions")
        
        if len(session_ids) == 0:
            print("ℹ️  No conversations found to clear")
            return
            
        # Ask for confirmation
        print("\n🚨 This will permanently delete ALL conversation data!")
        print("Sessions to be deleted:")
        for session_id in sorted(session_ids):
            message_count = redis_client.llen(f'postop:conversations:{session_id}')
            print(f"  - {session_id} ({message_count} messages)")
            
        confirm = input("\nAre you sure you want to delete all conversations? (type 'yes' to confirm): ")
        
        if confirm.lower() != 'yes':
            print("❌ Operation cancelled")
            return
            
        print("\n🧹 Clearing conversation data...")
        
        # Clear all conversation message lists
        deleted_conversations = 0
        total_messages = 0
        
        for session_id in session_ids:
            conversation_key = f'postop:conversations:{session_id}'
            message_count = redis_client.llen(conversation_key)
            
            if message_count > 0:
                redis_client.delete(conversation_key)
                deleted_conversations += 1
                total_messages += message_count
                print(f"  ✓ Deleted {session_id} ({message_count} messages)")
        
        # Clear the sessions tracking set
        if session_ids:
            redis_client.delete('postop:conversations:sessions')
            print(f"  ✓ Cleared sessions index")
        
        print(f"\n🎉 Successfully cleared all conversation data!")
        print(f"   • {deleted_conversations} conversations deleted")
        print(f"   • {total_messages} total messages removed")
        print(f"   • Sessions index cleared")
        
    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")
        print("Make sure Redis is running and REDIS_URL is correct")
        sys.exit(1)
    except redis.RedisError as e:
        print(f"❌ Redis error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()