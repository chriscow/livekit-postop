#!/bin/bash

# Reset PostOp AI Demo Data
# This script clears all demo data but restores medical knowledge for RAG
# Supports both local and Docker environments

set -e  # Exit on any error

echo "🗑️  PostOp AI Demo Reset"
echo "======================="

# Check if .env file exists and load it
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Auto-detect environment (Docker vs Local)
USE_DOCKER=false
DOCKER_MODE_ARG=""

# Check command line arguments
if [[ "$1" == "--docker" ]] || [[ "$1" == "-d" ]]; then
    USE_DOCKER=true
    DOCKER_MODE_ARG="--docker"
elif [[ "$1" == "--local" ]] || [[ "$1" == "-l" ]]; then
    USE_DOCKER=false
else
    # Auto-detect: if Docker containers are running, prefer Docker
    if docker-compose ps postop-scheduler 2>/dev/null | grep -q "Up"; then
        USE_DOCKER=true
        echo "🐳 Auto-detected: Using Docker environment"
    else
        USE_DOCKER=false
        echo "💻 Auto-detected: Using local environment"
    fi
fi

# Set execution context based on environment
if [ "$USE_DOCKER" = true ]; then
    echo "🐳 Operating in Docker environment"
    
    # Check if Docker containers are running
    if ! docker-compose ps postop-scheduler 2>/dev/null | grep -q "Up"; then
        echo "❌ Error: Docker containers are not running"
        echo "Please start them with: docker-compose up -d"
        exit 1
    fi
    
    PYTHON_CMD="docker-compose exec -T postop-scheduler python"
    REDIS_URL_DEFAULT="redis://redis:6379/0"
    echo "✅ Docker containers: Running"
else
    echo "💻 Operating in local environment"
    
    # Check if Redis is running locally
    if ! redis-cli ping > /dev/null 2>&1; then
        echo "❌ Error: Local Redis is not running"
        echo "Please start Redis with: redis-server"
        echo "Or use Docker mode: $0 --docker"
        exit 1
    fi
    
    # Set environment variables for local mode
    export LIVEKIT_AGENT_NAME=${LIVEKIT_AGENT_NAME:-postop-ai}
    export PYTHONPATH=.
    PYTHON_CMD="uv run python"
    REDIS_URL_DEFAULT="redis://localhost:6379/0"
    echo "✅ Local Redis: Running"
fi

echo ""

# Show what will be deleted
echo "🔍 Checking current PostOp AI data..."
$PYTHON_CMD << EOF
import redis
import os

# Connect to Redis
redis_url = os.getenv('REDIS_URL', '$REDIS_URL_DEFAULT')
r = redis.from_url(redis_url)

# Get all PostOp AI keys
postop_keys = r.keys('postop:*')
medical_keys = r.keys('medical_knowledge:*')

print(f"📊 Found {len(postop_keys)} PostOp system keys")
print(f"📊 Found {len(medical_keys)} medical knowledge keys")
print("")

if postop_keys:
    print("🗂️  PostOp keys to be deleted:")
    for key in postop_keys[:10]:  # Show first 10
        key_str = key.decode() if isinstance(key, bytes) else key
        print(f"   • {key_str}")
    if len(postop_keys) > 10:
        print(f"   ... and {len(postop_keys) - 10} more")
    print("")

if medical_keys:
    print("🧠 Medical knowledge keys (will be refreshed):")
    for key in medical_keys[:5]:  # Show first 5
        key_str = key.decode() if isinstance(key, bytes) else key
        print(f"   • {key_str}")
    if len(medical_keys) > 5:
        print(f"   ... and {len(medical_keys) - 5} more")
EOF

echo ""
read -p "🤔 Continue with reset? This will delete all demo data (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Reset cancelled"
    exit 1
fi

echo ""
echo "🗑️  Clearing PostOp AI demo data..."

# Clear all PostOp AI data using Python
$PYTHON_CMD << EOF
import redis
import os

# Connect to Redis
redis_url = os.getenv('REDIS_URL', '$REDIS_URL_DEFAULT')
r = redis.from_url(redis_url)

# Get all PostOp AI keys
postop_keys = r.keys('postop:*')
medical_keys = r.keys('medical_knowledge:*')
all_keys = postop_keys + medical_keys

deleted_count = 0
if all_keys:
    deleted_count = r.delete(*all_keys)
    print(f'🗑️  Deleted {deleted_count} records')
else:
    print('ℹ️  No PostOp AI data found to delete')

# Verify cleanup
remaining_postop = r.keys('postop:*')
remaining_medical = r.keys('medical_knowledge:*')
print(f'📊 Remaining postop keys: {len(remaining_postop)}')
print(f'📊 Remaining medical keys: {len(remaining_medical)}')
EOF

echo ""
echo "🧠 Restoring medical knowledge for RAG..."

# Restore medical knowledge
$PYTHON_CMD << EOF
import redis
import os
import json
from datetime import datetime

# Connect to Redis
redis_url = os.getenv('REDIS_URL', '$REDIS_URL_DEFAULT')
r = redis.from_url(redis_url)

# Medical knowledge items for RAG
knowledge_items = [
    {
        'text': 'Remove compression bandages 24-48 hours after surgery. Keep wound clean and dry. Watch for signs of infection including redness, swelling, or discharge.',
        'category': 'wound_care',
        'keywords': ['compression', 'bandage', 'wound', 'infection', 'redness', 'swelling']
    },
    {
        'text': 'Take prescribed pain medication as directed. Ibuprofen 400mg every 6-8 hours is typical for post-operative pain. Do not exceed maximum daily dose.',
        'category': 'pain_management', 
        'keywords': ['pain', 'medication', 'ibuprofen', 'dosage', 'post-operative']
    },
    {
        'text': 'Resume normal activities gradually. Avoid heavy lifting over 10 pounds for first week. Listen to your body and rest when needed.',
        'category': 'activity_guidance',
        'keywords': ['activity', 'lifting', 'exercise', 'rest', 'gradual', 'recovery']
    },
    {
        'text': 'Call healthcare provider immediately if you experience: severe pain, signs of infection, fever over 101°F, excessive bleeding, or any concerning symptoms.',
        'category': 'emergency_signs',
        'keywords': ['emergency', 'fever', 'bleeding', 'severe pain', 'infection', 'healthcare provider']
    },
    {
        'text': 'Wear compression stockings as directed to prevent swelling and promote healing. Remove at night unless specifically instructed otherwise.',
        'category': 'compression_care',
        'keywords': ['compression stockings', 'swelling', 'healing', 'circulation']
    },
    {
        'text': 'Keep incision sites clean and dry. Shower after 48 hours but avoid baths or soaking for one week post-surgery.',
        'category': 'incision_care',
        'keywords': ['incision', 'clean', 'dry', 'shower', 'bath', 'soaking', 'hygiene']
    },
    {
        'text': 'Watch for warning signs of complications: increased pain, swelling, redness, warmth, pus, red streaking, or fever. Contact your doctor immediately if these occur.',
        'category': 'complications',
        'keywords': ['complications', 'warning signs', 'pus', 'red streaking', 'fever', 'doctor']
    },
    {
        'text': 'Follow up with your healthcare provider as scheduled. Typically 1-2 weeks for initial check, then as directed for your specific procedure.',
        'category': 'follow_up',
        'keywords': ['follow up', 'appointment', 'check up', 'healthcare provider', 'schedule']
    }
]

# Store each knowledge item
for i, item in enumerate(knowledge_items):
    key = f'medical_knowledge:{i}'
    
    # Store as hash with all fields
    r.hset(key, mapping={
        'text': item['text'],
        'category': item['category'],
        'keywords': json.dumps(item['keywords']),
        'id': str(i),
        'created_at': datetime.now().isoformat(),
        'source': 'demo_reset'
    })

print(f'✅ Added {len(knowledge_items)} medical knowledge entries')
print('🧠 Medical RAG system ready for demos')

# Verify the knowledge was added
verified_count = len(r.keys('medical_knowledge:*'))
print(f'🔍 Verified: {verified_count} knowledge entries in Redis')
EOF

echo ""
echo "✅ Demo reset complete!"
echo ""
echo "🎯 System is now ready for a fresh demo:"
echo "   • All previous call data cleared"
echo "   • Medical knowledge restored for RAG queries"
echo "   • Ready for new discharge instruction collection"
echo ""
echo "💡 Next steps:"
echo "   ./start_agent.sh                    # Start the agent"
echo "   ./show_pending_calls.sh             # Check call status"
echo "   ./trigger_outbound_call.sh create   # Create test calls"