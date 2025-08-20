#!/bin/bash

# Trigger Outbound Call - Manual execution script for PostOp AI Demo
# This script allows manual triggering of outbound calls for demo purposes
# Supports both local and Docker environments

set -e  # Exit on any error

# Function to show usage
show_usage() {
    echo "📞 PostOp AI - Outbound Call Trigger"
    echo "===================================="
    echo ""
    echo "Usage:"
    echo "  $0 [--docker|--local] <call_id>        # Execute specific call immediately"
    echo "  $0 [--docker|--local] list             # Show pending calls"
    echo "  $0 [--docker|--local] create <phone> <name>      # Create test call for demo"
    echo "  $0 [--docker|--local] create <phone> <name> <seconds>  # Create call scheduled in X seconds"
    echo ""
    echo "Environment Options:"
    echo "  --docker, -d     Force Docker environment"
    echo "  --local, -l      Force local environment"
    echo "  (no flag)        Auto-detect environment"
    echo ""
    echo "Examples:"
    echo "  $0 f02667fe                     # Execute call f02667fe immediately"
    echo "  $0 list                         # Show all pending calls"
    echo "  $0 create +14258295443 'Chris'  # Create courtesy call for Chris"
    echo "  $0 create +14258295443 'Chris' 60  # Create call in 60 seconds"
    echo "  $0 --docker list                # Force Docker mode"
    echo ""
}

# Check if .env file exists and load it
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Parse environment flags and shift arguments
USE_DOCKER=false
DOCKER_MODE_ARG=""
EXPLICIT_ENV_SET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --docker|-d)
            USE_DOCKER=true
            DOCKER_MODE_ARG="--docker"
            EXPLICIT_ENV_SET=true
            shift
            ;;
        --local|-l)
            USE_DOCKER=false
            EXPLICIT_ENV_SET=true
            shift
            ;;
        -*)
            echo "❌ Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            break  # First non-option argument is the command
            ;;
    esac
done

# Check arguments after parsing flags
if [ $# -lt 1 ]; then
    show_usage
    exit 1
fi

COMMAND=$1

# Auto-detect environment if not explicitly specified
if [[ "$EXPLICIT_ENV_SET" = false ]]; then
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
    REDIS_HOST="redis"
    echo "✅ Docker containers: Running"
else
    echo "💻 Operating in local environment"
    
    # Validate required environment variables for local mode
    if [ -z "$LIVEKIT_AGENT_NAME" ]; then
        echo "❌ Error: LIVEKIT_AGENT_NAME not set in .env"
        exit 1
    fi
    
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
    echo "✅ Local Redis: Running"
fi

echo ""

case $COMMAND in
    "list")
        echo "📋 Showing pending calls..."
        ./show_pending_calls.sh $DOCKER_MODE_ARG
        ;;
    
    "create")
        if [ $# -lt 3 ]; then
            echo "❌ Error: Missing arguments for create command"
            echo "Usage: $0 create <phone> <name> [seconds_delay]"
            exit 1
        fi
        
        PHONE=$2
        NAME=$3
        DELAY=${4:-10}  # Default to 10 seconds if not specified
        
        echo "🎬 Creating demo outbound call..."
        echo "   📱 Phone: $PHONE"
        echo "   👤 Name: $NAME"
        echo "   ⏱️  Delay: ${DELAY} seconds"
        echo ""
        
        # Create the call using Python
        $PYTHON_CMD << EOF
import sys
from datetime import datetime, timedelta
from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallType

try:
    # Create scheduler
    scheduler = CallScheduler(redis_host='$REDIS_HOST')
    
    # Create demo call
    call_item = CallScheduleItem(
        patient_id=f'demo-trigger-{int(datetime.now().timestamp())}',
        patient_phone='$PHONE',
        scheduled_time=datetime.now() + timedelta(seconds=$DELAY),
        call_type=CallType.WELLNESS_CHECK,
        priority=2,
        llm_prompt='Hi $NAME, this is Vince from PostOp AI calling for a quick courtesy check. How are you feeling today? Do you have any questions about your recent procedure or discharge instructions?',
        metadata={
            'demo_call': True,
            'created_via': 'trigger_script',
            'patient_name': '$NAME',
            'call_category': 'manual_demo'
        }
    )
    
    # Schedule the call
    if scheduler.schedule_call(call_item):
        print(f'✅ Demo call created: {call_item.id[:8]}')
        print(f'📞 Will call $PHONE in $DELAY seconds')
        print(f'🔍 Use "./show_pending_calls.sh" to monitor status')
        print(f'⚡ Use "./$0 {call_item.id[:8]}" to execute immediately')
    else:
        print('❌ Failed to schedule call')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Error creating call: {e}')
    sys.exit(1)
EOF
        ;;
    
    *)
        # Assume it's a call ID to execute
        CALL_ID=$1
        
        echo "🚀 Triggering outbound call: $CALL_ID"
        echo ""
        
        # Execute the call using Python
        $PYTHON_CMD << EOF
import sys
from scheduling.tasks import execute_followup_call
from scheduling.scheduler import CallScheduler

try:
    # Get the call details first
    scheduler = CallScheduler(redis_host='$REDIS_HOST')
    pending_calls = scheduler.get_pending_calls(limit=100)
    
    # Find matching call
    target_call = None
    for call in pending_calls:
        if call.id.startswith('$CALL_ID') or call.id == '$CALL_ID':
            target_call = call
            break
    
    if not target_call:
        print(f'❌ Call with ID "$CALL_ID" not found in pending calls')
        print('💡 Use "./show_pending_calls.sh" to see available calls')
        sys.exit(1)
    
    # Show call details
    patient_name = target_call.metadata.get('patient_name', 'Unknown') if target_call.metadata else 'Unknown'
    print(f'📞 Executing call to {patient_name} at {target_call.patient_phone}')
    print(f'🎯 Call type: {target_call.call_type.value}')
    print('')
    
    # Queue the call for execution
    job = execute_followup_call.delay(target_call.id)
    print(f'✅ Call queued for execution')
    print(f'🔧 Job ID: {job.id}')
    print(f'📱 Your phone should ring shortly at {target_call.patient_phone}!')
    print('')
    print('💡 Use "./show_pending_calls.sh" to monitor call status')
    
except Exception as e:
    print(f'❌ Error executing call: {e}')
    sys.exit(1)
EOF
        ;;
esac