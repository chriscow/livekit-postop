#!/bin/bash

# Show Pending Calls - Observability Script for PostOp AI Demo
# This script shows all scheduled calls with timing and status information
# Supports both local and Docker environments

set -e  # Exit on any error

echo "📞 PostOp AI - Pending Calls Status"
echo "=================================="

# Check if .env file exists and load it
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Auto-detect environment (Docker vs Local)
USE_DOCKER=false

# Check command line arguments
if [[ "$1" == "--docker" ]] || [[ "$1" == "-d" ]]; then
    USE_DOCKER=true
elif [[ "$1" == "--local" ]] || [[ "$1" == "-l" ]]; then
    USE_DOCKER=false
else
    # Auto-detect: if Docker containers are running, prefer Docker
    if docker-compose ps postop-scheduler 2>/dev/null | grep -q "Up"; then
        USE_DOCKER=true
    else
        USE_DOCKER=false
    fi
fi

# Set execution context based on environment
if [ "$USE_DOCKER" = true ]; then
    # Check if Docker containers are running
    if ! docker-compose ps postop-scheduler 2>/dev/null | grep -q "Up"; then
        echo "❌ Error: Docker containers are not running"
        echo "Please start them with: docker-compose up -d"
        exit 1
    fi
    
    PYTHON_CMD="docker-compose exec -T postop-scheduler python"
    REDIS_HOST="redis"
    echo "✅ Docker containers: Running"
else
    # Check if Redis is running locally
    if ! redis-cli ping > /dev/null 2>&1; then
        echo "❌ Error: Local Redis is not running"
        echo "Please start Redis or use Docker mode: $0 --docker"
        exit 1
    fi
    
    # Set environment variables for local mode
    export LIVEKIT_AGENT_NAME=${LIVEKIT_AGENT_NAME:-postop-ai}
    export PYTHONPATH=.
    PYTHON_CMD="uv run python"
    REDIS_HOST="localhost"
    echo "✅ Redis connection: OK"
fi

echo ""

# Show pending calls using Python
$PYTHON_CMD << EOF
import os
import sys
from datetime import datetime, timedelta
from scheduling.scheduler import CallScheduler
from scheduling.models import CallStatus

try:
    # Create scheduler
    scheduler = CallScheduler(redis_host='$REDIS_HOST')
    
    # Get pending calls
    pending_calls = scheduler.get_pending_calls(limit=20)
    
    if not pending_calls:
        print("📋 No pending calls found")
        print("")
        print("💡 To create a test call:")
        print("   ./trigger_outbound_call.sh create +14258295443 'Test Patient'")
        sys.exit(0)
    
    print(f"📋 Found {len(pending_calls)} pending call(s):")
    print("")
    
    now = datetime.now()
    
    for i, call in enumerate(pending_calls, 1):
        # Calculate time until call
        time_diff = call.scheduled_time - now
        
        if time_diff.total_seconds() <= 0:
            time_status = "⏰ DUE NOW"
            time_str = "overdue"
        elif time_diff.total_seconds() <= 60:
            time_status = f"⏱️  IN {int(time_diff.total_seconds())}s"
            time_str = f"in {int(time_diff.total_seconds())} seconds"
        elif time_diff.total_seconds() <= 3600:
            minutes = int(time_diff.total_seconds() / 60)
            time_status = f"⏱️  IN {minutes}m"
            time_str = f"in {minutes} minutes"
        else:
            hours = int(time_diff.total_seconds() / 3600)
            time_status = f"⏱️  IN {hours}h"
            time_str = f"in {hours} hours"
        
        # Get patient name from metadata
        patient_name = call.metadata.get('patient_name', 'Unknown') if call.metadata else 'Unknown'
        
        print(f"{i}. 📞 Call ID: {call.id[:8]}...")
        print(f"   👤 Patient: {patient_name}")
        print(f"   📱 Phone: {call.patient_phone}")
        print(f"   📅 Scheduled: {call.scheduled_time.strftime('%Y-%m-%d %H:%M:%S')} ({time_str})")
        print(f"   🔄 Status: {call.status.value.upper()} {time_status}")
        print(f"   🎯 Type: {call.call_type.value}")
        print(f"   ⭐ Priority: {call.priority}")
        
        # Show first part of prompt
        prompt_preview = call.llm_prompt[:80] + "..." if len(call.llm_prompt) > 80 else call.llm_prompt
        print(f"   💬 Message: {prompt_preview}")
        print("")
    
    print("🔧 Management commands:")
    print("   ./trigger_outbound_call.sh <call_id>     # Execute call immediately")
    print("   ./trigger_outbound_call.sh list          # Show this list again")
    print("   ./trigger_outbound_call.sh create <phone> <name>  # Create test call")
    
except Exception as e:
    print(f"❌ Error getting pending calls: {e}")
    sys.exit(1)
EOF

echo ""
echo "🔄 This information updates in real-time. Run this script again to refresh."