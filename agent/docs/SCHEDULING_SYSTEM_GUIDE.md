# PostOp AI Scheduling System Guide

## Overview

The PostOp AI scheduling system provides automated patient follow-up calls based
on discharge orders. The system supports flexible timing, dynamic scheduling
during calls, and medical knowledge lookup via RAG.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Discharge Orders│────│ Call Scheduler   │────│ RQ Tasks        │
│ with Templates  │    │ (Timing Parser)  │    │ (Execute Calls) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Medical RAG     │────│ Followup Agents  │────│ LiveKit SIP     │
│ (Knowledge)     │    │ (Conversations)  │    │ (Outbound)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Key Components

### 1. Data Models (`scheduling/models.py`)

**CallScheduleItem**: Represents a scheduled call
- Contains LLM prompt defining conversation purpose
- Flexible timing and retry logic
- Patient phone number for outbound calling

**CallRecord**: Tracks call execution and outcomes
- Conversation summaries and patient responses
- Error handling and retry tracking
- Additional calls scheduled during conversation

### 2. Call Scheduler (`scheduling/scheduler.py`)

**Flexible Timing Specifications**:
- `24_hours_after_discharge` - Single reminder calls
- `daily_for_2_days_starting_12_hours_after_discharge` - Daily reminders
- `day_before_date:2025-06-23` - Specific date reminders
- `within_24_hours` - General wellness checks

**CallScheduler Class**:
- Generates calls from discharge orders
- Parses timing specs into scheduled dates
- Stores calls in Redis for execution

### 3. Enhanced Discharge Orders (`discharge/discharge_orders.py`)

Orders now have `call_template` fields:
```python
call_template = {
    "timing": "24_hours_after_discharge",
    "call_type": "discharge_reminder",
    "priority": 2,
    "prompt_template": "You are calling {patient_name} about their compression bandage..."
}
```

### 4. RQ Task System (`scheduling/tasks.py`)

**Task Types**:
- `execute_followup_call` - Execute individual calls via LiveKit
- `process_pending_calls` - Queue all due calls for execution
- `generate_patient_calls` - Create call schedule for new patients

### 5. LiveKit Integration (`followup/call_executor.py`)

**Outbound Calling**:
- Creates LiveKit agent dispatch with call metadata
- Dials patient using SIP trunk
- Handles busy signals, no answers, and errors
- Retry logic with exponential backoff

### 6. Enhanced Followup Agents (`followup/agents.py`)

**ScheduledFollowupAgent**:
- Uses CallScheduleItem.llm_prompt as conversation instructions
- Dynamic scheduling function tools
- Medical RAG integration for knowledge lookup
- Call outcome tracking

**Function Tools Available**:
- `end_call()` - Graceful call termination
- `detected_answering_machine()` - Voicemail handling
- `schedule_reminder_call(when, purpose)` - Dynamic scheduling
- `get_discharge_order_details()` - Order information lookup
- `record_patient_response(question, response)` - Response tracking

### 7. Medical RAG System (`discharge/medical_rag.py`)

**Function Tools for Agents**:
- `lookup_procedure_info(procedure, question)` - Procedure information
- `lookup_medication_info(medication, question)` - Medication guidance
- `lookup_symptom_guidance(symptom)` - Post-op symptom help
- `lookup_recovery_timeline(procedure, activity)` - Recovery timelines

### 8. Worker Management (`scheduling/worker.py`)

**PostOpCallWorker**: RQ worker for processing call execution jobs
**CallSchedulerDaemon**: Monitors pending calls and queues them

## Usage Examples

### Generate Calls for a Patient

```python
from scheduling.scheduler import CallScheduler
from datetime import datetime

scheduler = CallScheduler()

# Generate all follow-up calls for a patient
calls = scheduler.generate_calls_for_patient(
    patient_id="patient-123",
    patient_phone="+1234567890",
    patient_name="John Doe",
    discharge_time=datetime(2025, 1, 15, 10, 0, 0),
    selected_order_ids=["vm_compression", "vm_activity", "vm_school"]
)

# Schedule each call
for call in calls:
    scheduler.schedule_call(call)
```

### Start Worker Processes

```bash
# Start call execution worker
python -m scheduling.worker worker --redis-host localhost

# Start scheduler daemon
python -m scheduling.worker scheduler --check-interval 60

# Start both
python -m scheduling.worker both
```

### Agent Configuration

The new `postop-followup-agent` should be configured in LiveKit to use the `scheduled_followup_entrypoint`:

```python
# In your agent registration
cli.run_app(WorkerOptions(
    agent_name="postop-followup-agent",
    entrypoint_fnc=scheduled_followup_entrypoint
))
```

### Sample Call Flow

1. **Patient Discharged**: Calls generated based on selected discharge orders
2. **Scheduler Daemon**: Periodically checks for due calls and queues them
3. **RQ Worker**: Picks up queued calls and executes via LiveKit
4. **LiveKit**: Creates agent dispatch and dials patient
5. **Agent**: Conducts conversation using call-specific LLM prompt
6. **Dynamic Features**: Agent can schedule additional calls, lookup medical info
7. **Call Completion**: Status updated, record saved with outcomes

## Call Examples

### Compression Bandage Reminder (24 hours after discharge)
*Agent*: "Hi John, this is Sarah from PostOp AI. I'm calling to remind you about your compression bandage. You were instructed to leave the compression bandage on for 24 hours and then wear as much as can be tolerated for 7 days. It's been about 24 hours since your procedure. Have you removed the compression bandage as instructed?"

*Patient*: "Yes, I took it off this morning."

*Agent*: "Perfect! Do you have any questions about the next steps or wearing it as tolerated for the next 7 days?"

### School Return Reminder (day before 6/23/2025)
*Agent*: "Hi, this is a reminder call about returning to school. You were told your child may return to school or daycare on June 23rd, 2025. Tomorrow is the day they may return. Are you feeling ready, and do you have any concerns about returning?"

*Patient*: "Actually, could you remind me again the day of?"

*Agent*: "Of course! I can schedule a reminder call for tomorrow morning. Would that be helpful?"

### Dynamic Medical Lookup During Call
*Patient*: "I'm having some swelling at the procedure site. Is that normal?"

*Agent*: *(uses lookup_symptom_guidance)* "Let me look that up for you... Some swelling at the treatment site is normal after venous malformation procedures. However, if the swelling is severe, getting worse, or accompanied by increased pain, redness, or warmth, you should contact your healthcare provider..."

## Testing

Comprehensive test suite available in `tests/`:
```bash
# Run all tests
source .venv/bin/activate && uv run python3 -m pytest tests/ -v

# Run specific test categories
uv run python3 -m pytest tests/test_scheduler.py -v
uv run python3 -m pytest tests/test_models.py -v
```

## Configuration

### Environment Variables
```bash
# Required for outbound calling
SIP_OUTBOUND_TRUNK_ID=ST_your_trunk_id

# LiveKit connection
LIVEKIT_URL=your_livekit_url
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Optional: Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Medical RAG Database
Build sample database for testing:
```python
from discharge.medical_rag import build_sample_medical_rag_database
await build_sample_medical_rag_database("data/medical_rag")
```

## Integration with Existing System

The new scheduling system is designed to work alongside the existing callback-based system:

- **Legacy**: `patient_callback_entrypoint` for reactive callbacks
- **New**: `scheduled_followup_entrypoint` for proactive scheduled calls
- **Both** can coexist and use the same LiveKit infrastructure

## Monitoring and Management

### Worker Statistics
```python
worker = PostOpCallWorker()
stats = worker.get_worker_stats()
# Returns queue sizes, job counts, pending calls, etc.
```

### Call Status Tracking
```python
scheduler = CallScheduler()
scheduler.update_call_status(call_id, CallStatus.COMPLETED, "Success")
pending_calls = scheduler.get_pending_calls()
```

### Error Handling
- Failed calls are automatically retried with exponential backoff
- Permanent failures (wrong numbers, declined calls) are not retried  
- All call attempts and outcomes are logged and stored

This system provides a complete solution for automated, intelligent patient follow-up calls with dynamic scheduling and medical knowledge integration.