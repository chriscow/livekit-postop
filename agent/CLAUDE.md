# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# PostOp AI System - Automated Patient Follow-up Calls

## Project Overview

PostOp AI is a comprehensive system for automated patient follow-up calls after medical procedures. It combines voice telephony integration, intelligent call scheduling, hybrid RAG medical knowledge system, and Redis-based task management to provide personalized post-operative care.

## System Architecture

**Complete Flow**: Patient Discharge → Call Generation → Scheduling → Execution → Follow-up

- **Discharge Orders**: Procedure-specific instructions with call templates
- **Call Scheduler**: Generates personalized calls based on discharge orders
- **Redis Storage**: Persistent call storage and status tracking
- **RQ Task Queue**: Asynchronous call execution
- **Voice Integration**: Voice agent execution via SIP
- **Hybrid RAG**: Medical knowledge retrieval for dynamic responses

## Core Components

### 1. Discharge Orders System (`discharge/`)

- **`discharge_orders.py`**: Medical discharge order definitions with call templates
- **`hybrid_rag.py`**: Hybrid RAG system supporting Redis and Annoy backends
- **`medical_rag.py`**: Medical knowledge base management

**Key Features**:

- Procedure-specific discharge orders (compression, activity, medication, etc.)
- Flexible timing specifications (`24_hours_after_discharge`, `daily_for_3_days`, etc.)
- Integrated call templates with personalized prompts

### 2. Call Scheduling System (`scheduling/`)

- **`scheduler.py`**: Core call scheduling and Redis operations
- **`models.py`**: CallScheduleItem and CallRecord data models
- **`tasks.py`**: RQ tasks for call execution and generation

**Key Features**:

- Intelligent call generation from discharge orders
- Redis-based persistent storage
- Status tracking (PENDING → IN_PROGRESS → COMPLETED/FAILED)
- Retry logic with configurable attempts

### 3. Medical Knowledge System

- **Hybrid RAG**: Supports both Redis and Annoy vector backends
- **Function Tools**: Agent integration for real-time knowledge lookup
- **CLI Management**: Tools for medical knowledge CRUD operations

### 4. Voice Telephony Integration

- **SIP Integration**: Inbound and outbound call capabilities
- **Agent Dispatch**: Automatic agent assignment for calls
- **Voice Processing**: Optimized for telephony with `BVCTelephony()`

## Environment Variables Required

```bash
# Voice Service Configuration
LIVEKIT_API_KEY=<your_key>
LIVEKIT_API_SECRET=<your_secret>
LIVEKIT_URL=<your_livekit_url>

# AI Services
DEEPGRAM_API_KEY=<your_key>
OPENAI_API_KEY=<your_key>
ELEVEN_API_KEY=<your_key>

# Redis Configuration
REDIS_URL=redis://localhost:6379
```

## Development Commands

### Python Execution

- **Always use `uv run python`** for all Python commands
- **Always set `PYTHONPATH=.`** when running scripts from project root
- Use `freezegun` for time-dependent testing

### Docker Development

```bash
# Start all services (recommended for development)
docker compose up --build -d

# Check service status
docker compose ps

# View logs
docker compose logs -f postop-agent
docker compose logs -f postop-scheduler
docker compose logs -f postop-worker

# Execute commands in containers
docker compose exec postop-scheduler python <command>
docker compose exec postop-agent python <command>
```

### Local Development Scripts

```bash
# Start agent locally (preferred for demos)
./start_agent.sh

# Reset demo data and restore medical knowledge
./reset_demo.sh

# Show pending calls
./show_pending_calls.sh

# Trigger outbound call
./trigger_outbound_call.sh <call-id>
./trigger_outbound_call.sh create +phone 'Name'  # Create test call
```

### Testing

```bash
# Run basic integration tests
PYTHONPATH=. uv run python tests/integration/test_basic_rag_integration.py

# Run medium integration tests (scheduling)
PYTHONPATH=. uv run python tests/integration/test_simple_medium_integration.py

# Run advanced integration tests (full workflow)
PYTHONPATH=. uv run python tests/integration/test_advanced_integration.py

# Run with pytest (has specific configuration in pytest.ini)
PYTHONPATH=. uv run python -m pytest tests/integration/ -v

# Run unit tests vs integration tests
PYTHONPATH=. uv run python -m pytest -m "unit" tests/
PYTHONPATH=. uv run python -m pytest -m "integration" tests/
```

### Medical Knowledge Management

```bash
# Comprehensive CLI tool (recommended)
PYTHONPATH=. uv run python tools/medical_knowledge_cli.py --help
PYTHONPATH=. uv run python tools/medical_knowledge_cli.py list --limit 10
PYTHONPATH=. uv run python tools/medical_knowledge_cli.py search "pain management"
PYTHONPATH=. uv run python tools/medical_knowledge_cli.py add --text "Medical knowledge here"

# Direct RAG operations
PYTHONPATH=. uv run python discharge/medical_rag.py add-redis "Medical knowledge text" "Category"
PYTHONPATH=. uv run python discharge/medical_rag.py search-redis "query" --max-results 5

# Test hybrid RAG backend
PYTHONPATH=. uv run python -c "
from discharge.hybrid_rag import create_hybrid_rag_handler
handler = create_hybrid_rag_handler(backend='auto')
print(handler.get_backend_info())
"
```

### Call Scheduling

```bash
# Use CLI tools (recommended)
PYTHONPATH=. uv run python tools/call_scheduler_cli.py generate-test-calls --patient-name "John Doe" --phone "+1234567890"
PYTHONPATH=. uv run python tools/call_scheduler_cli.py list-pending --limit 10
PYTHONPATH=. uv run python tools/call_scheduler_cli.py stats

# Demo call trigger (for live demos)
PYTHONPATH=. uv run python tools/demo_call_trigger.py create-demo-call --name "Demo Patient" --execute-now

# Test call generation (inline)
PYTHONPATH=. uv run python -c "
from scheduling.scheduler import CallScheduler
from datetime import datetime
scheduler = CallScheduler()
calls = scheduler.generate_calls_for_patient(
    patient_id='test-001',
    patient_phone='+1234567890',
    patient_name='Test Patient',
    discharge_time=datetime.now(),
    selected_order_ids=['vm_compression', 'vm_activity']
)
print(f'Generated {len(calls)} calls')
"

# Check pending calls (inline)
PYTHONPATH=. uv run python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
calls = scheduler.get_pending_calls()
print(f'Found {len(calls)} pending calls')
"
```

### LiveKit Agent

```bash
# Agent entry point routes to discharge workflow by default
# Test agent locally (console mode)
uv run python agent.py console

# Run agent for telephony (connects to voice service)
uv run python agent.py dev

# Alternative: Use start script (recommended)
./start_agent.sh  # Handles environment validation and conflicts

# Check dispatch rules
lk sip dispatch list

# Direct workflow access (if needed)
PYTHONPATH=. uv run python discharge_main.py console
PYTHONPATH=. uv run python followup_main.py console
```

## System Status & Integration Test Results

### ✅ Completed Components

- **Medical Knowledge System**: Hybrid RAG with Redis/Annoy backends
- **Call Scheduling**: Complete Redis-based scheduling system
- **Discharge Orders**: 7 procedure-specific orders with call templates
- **Task Queue**: RQ-based asynchronous call execution
- **Integration Testing**: Progressive testing (Basic → Medium → Advanced)

### 🧪 Integration Test Coverage

- **Basic Integration**: RAG system + mock agents ✅
- **Medium Integration**: Scheduling + Redis + tasks ✅
- **Advanced Integration**: Full workflow end-to-end ✅

### 📊 Test Results Summary

- **RAG Queries**: 8+ successful medical knowledge retrievals
- **Call Generation**: 7 calls from 4 discharge orders
- **Redis Operations**: 100% success rate for scheduling
- **Status Tracking**: Complete lifecycle management
- **Error Handling**: Retry logic and failure recovery

## Voice Telephony Configuration

### SIP Integration Setup

**Call Flow**: Phone → Twilio → SIP Trunk → LiveKit SIP → Agent Dispatch → PostOp Agent

### Dispatch Configuration (via Voice Service Dashboard)

- **Rule Name**: "PostOp AI Calls"
- **Agent**: `postop-agent`
- **Room Pattern**: `call-{caller}-{random}`
- **SIP Trunks**: `<any>`

### Twilio Configuration

- **Phone Number**: Configured for SIP Trunk (not webhooks)
- **SIP Domain**: `postop.sip.twilio.com`
- **Trunk URI**: `sip:2jw5aqolil4.sip.livekit.cloud`

## Data Models

### CallScheduleItem

```python
@dataclass
class CallScheduleItem:
    id: str
    patient_id: str
    patient_phone: str
    scheduled_time: datetime
    call_type: CallType  # DISCHARGE_REMINDER, WELLNESS_CHECK, etc.
    priority: int  # 1=urgent, 2=important, 3=routine
    llm_prompt: str  # Personalized conversation instructions
    status: CallStatus  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    related_discharge_order_id: Optional[str]
    # ... additional fields for retry logic, metadata, etc.
```

### Discharge Order Structure

```python
discharge_order: str  # Human-readable instructions
call_template: Dict = {
    "timing": "24_hours_after_discharge",
    "call_type": "discharge_reminder",
    "priority": 2,
    "prompt_template": "Personalized prompt with {patient_name} and {discharge_order}"
}
```

## Supported Timing Specifications

- `24_hours_after_discharge`, `48_hours_after_discharge`
- `daily_for_X_days_starting_Y_hours_after_discharge`
- `day_before_date:YYYY-MM-DD`
- `within_24_hours`

## Current Discharge Orders

1. **vm_compression**: Compression bandage removal (24h after)
2. **vm_activity**: Activity restrictions (48h after)
3. **vm_medication**: Medication reminders (daily for 3 days)
4. **vm_school**: School/daycare return reminder
5. **vm_bleomycin**: Bleomycin injection follow-up
6. **vm_followup**: General follow-up appointment
7. **vm_emergency**: Emergency contact instructions

## Production Deployment

### Redis Setup

- **Production**: Redis instance with persistence enabled
- **Development**: Local Redis on port 6379
- **Keys**: Namespaced with `postop:` prefix

### Scaling Considerations

- **RQ Workers**: Multiple workers for call execution
- **Voice Service**: Distributed agent deployment
- **Redis**: Cluster setup for high availability

## Troubleshooting

### Common Issues

- **"list index out of range"**: Redis list operation error during bulk scheduling
- **Call not found**: Verify call exists in Redis with correct key format
- **Agent not joining**: Check dispatch rule agent name matches exactly
- **RAG no results**: Verify medical knowledge is loaded in backend

### Debug Commands

```bash
# Check Redis keys
redis-cli keys "postop:*"

# Verify RAG backend
PYTHONPATH=. uv run python -c "
from discharge.hybrid_rag import create_hybrid_rag_handler
handler = create_hybrid_rag_handler(backend='auto')
print(handler.get_backend_info())
"

# Test call scheduling
PYTHONPATH=. uv run python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
scheduler.redis_client.ping()
print('Redis connection OK')
"
```

## Architecture Notes

### Project Structure

- **`agent.py`**: Main entry point, routes to workflows (defaults to discharge)
- **`discharge/`**: Discharge instruction collection and LLM analysis
- **`followup/`**: Follow-up call execution and business logic
- **`scheduling/`**: Redis-based call scheduling and task management
- **`tools/`**: CLI utilities for demos and management
- **`shared/`**: Common utilities (memory, prompts, TTS)
- **`prompts/`**: YAML-based prompt templates

### Data Flow Architecture

1. **Discharge Collection**: `discharge/agents.py` → LLM analysis → Personalized calls
2. **Call Scheduling**: `scheduling/scheduler.py` → Redis storage → RQ task queue
3. **Call Execution**: `scheduling/tasks.py` → `followup/call_executor.py` → LiveKit SIP
4. **Medical RAG**: Hybrid Redis/Annoy backends for real-time knowledge lookup

### Key Design Patterns

- **Dependency Injection**: Used throughout for testability (see testing guidelines)
- **Pure Business Logic**: Separated from infrastructure concerns
- **Redis Namespacing**: All keys prefixed with `postop:`
- **Status Tracking**: PENDING → IN_PROGRESS → COMPLETED/FAILED
- **Hybrid Backends**: Auto-detection between Redis and Annoy for RAG

### Integration Points

- **LiveKit**: Voice agents via SIP with automatic dispatch
- **Redis**: Task queues, call storage, and vector embeddings
- **RQ**: Asynchronous task execution with retry logic
- **OpenAI**: LLM analysis and conversation generation

## Development Tips

- Use `uv` for all Python execution
- Set `PYTHONPATH=.` when running scripts
- Use `freezegun` for time-dependent testing
- Clean up Redis test keys after testing
- Use Docker for consistent development environment
- Prefer CLI tools over inline Python for common tasks

## CLI Tools Reference

### Available Tools

- **`tools/demo_call_trigger.py`**: Live demonstrations and immediate call execution
- **`tools/call_scheduler_cli.py`**: Production call scheduling and management
- **`tools/medical_knowledge_cli.py`**: Medical RAG knowledge base management
- **Helper scripts**: `start_agent.sh`, `reset_demo.sh`, `show_pending_calls.sh`, `trigger_outbound_call.sh`

### Common Workflows

```bash
# Fresh demo setup
./reset_demo.sh
./start_agent.sh

# Call management
./show_pending_calls.sh
./trigger_outbound_call.sh create +15551234567 "Test Patient"

# Development workflow
docker compose up -d  # Start services
PYTHONPATH=. uv run python -m pytest tests/integration/ -v  # Run tests
```

## Production Deployment

### Environment Variables Required

- **LiveKit**: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- **AI Services**: `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVEN_API_KEY`
- **SIP**: `SIP_OUTBOUND_TRUNK_ID`
- **Redis**: `REDIS_URL` (defaults to localhost:6379)
- **Agent**: `AGENT_NAME`, `LIVEKIT_AGENT_NAME`

### Deployment Options

1. **DigitalOcean**: Droplet + ValKey (managed Redis)
2. **Fly.io**: Auto-scaling with GitHub Actions (configured)
3. **Docker Compose**: Local/VPS deployment

## Next Steps

- [ ] Fix bulk call scheduling Redis error
- [ ] Add outbound calling via LiveKit SIP
- [ ] Implement call recording and transcription
- [ ] Add patient response analysis
- [ ] Build web dashboard for call management
- [ ] Add SMS integration for call confirmations
- all of the livekit agents documentation is available locally here: /Users/chris/dev/livekit-postop/.local/ai_docs/livekit-agents.md
- Do not deploy unless I explicitly ask you do.
