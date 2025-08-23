# PostOp AI - Automated Patient Follow-up System

An intelligent system for automated post-operative patient follow-up calls using voice telephony, LLM-powered transcript analysis, Redis task management, and medical knowledge RAG.

## Key Features

- **🎯 LLM Transcript Analysis**: Automatically analyzes discharge instructions and generates personalized follow-up calls
- **📞 Voice Telephony**: Voice agents for inbound/outbound patient calls
- **🧠 Medical Knowledge RAG**: Hybrid Redis/Annoy vector database for medical question answering
- **⚡ Demo System**: Comprehensive CLI tools for live demonstrations and testing
- **🔄 Task Management**: Redis-based call scheduling with retry logic
- **🌐 Multi-language**: Real-time translation support for patient instructions

## Development Setup

### Local Development

1. **Copy environment variables**: `cp .env.example .env`
2. **Fill in your API keys** in `.env`:

   ```bash
   # Required for local development
   LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
   LIVEKIT_API_KEY=your_api_key
   LIVEKIT_API_SECRET=your_api_secret
   DEEPGRAM_API_KEY=your_deepgram_key
   OPENAI_API_KEY=your_openai_key
   ELEVEN_API_KEY=your_elevenlabs_key

   # Redis Configuration (automatically handled by docker-compose)
   REDIS_URL=redis://localhost:6379/0
   REDIS_HOST=redis  # Docker service name
   REDIS_PORT=6379
   ```

3. **Start all services**: `docker compose up --build`
4. **Access services**:
   - Voice agent: Connects to voice server automatically
   - Redis: `localhost:6379`
   - Logs: `docker compose logs -f`

### Local Development Features

- **Hot reload**: Code changes trigger rebuilds
- **Local Redis**: Runs in Docker container with persistent volume
- **Service isolation**: Each component runs in separate container
- **Easy debugging**: Access all logs via `docker compose logs`

## Local Testing Guide

This section walks you through testing both the discharge instruction collection workflow and the follow-up call scheduling system.

### Prerequisites for Testing

1. **Services Running**: Ensure all Docker services are up and healthy:

   ```bash
   docker compose ps
   # All services should show "Up" status
   ```

2. **Environment Variables**: Verify your `.env` file has all required keys:
   ```bash
   # Required for testing
   LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
   LIVEKIT_API_KEY=your_api_key
   LIVEKIT_API_SECRET=your_api_secret
   DEEPGRAM_API_KEY=your_deepgram_key
   OPENAI_API_KEY=your_openai_key
   ELEVEN_API_KEY=your_elevenlabs_key
   AGENT_NAME=PostOp-AI
   SIP_OUTBOUND_TRUNK_ID=ST_your_trunk_id
   ```

### Testing the Discharge Agent with LLM Analysis

The discharge agent collects discharge instructions from medical staff, then uses advanced LLM analysis to automatically generate personalized follow-up calls. Supports multiple languages with real-time translation.

#### 1. Start Console Mode

```bash
# Run the discharge agent in interactive console mode
docker compose exec postop-agent python discharge_main.py console
```

#### 2. Test Scenarios

**Basic English Workflow:**

1. Agent asks for recording consent → Say "Yes, you may record"
2. Agent asks for patient name → Say "John Smith"
3. Agent asks for language preference → Say "English"
4. Agent enters passive listening mode → Read sample discharge instructions
5. Agent collects instructions silently
6. Say "That's all the instructions" to trigger verification
7. Agent reads back collected instructions for confirmation

**Translation Workflow:**

1. Follow steps 1-2 above
2. When asked for language → Say "Spanish" (or another language)
3. Agent asks if you want real-time translation → Say "Yes"
4. Read instructions in English → Agent translates to Spanish
5. Continue with verification process

**Sample Discharge Instructions to Read:**

```
"Take the compression bandage off in 24 hours. Keep the area clean and dry.
Take ibuprofen 400mg every 6 hours for pain. Return to school in 3 days.
Call us immediately if you see signs of infection like redness or swelling."
```

#### 3. Expected Behavior

- ✅ Agent should remain mostly silent during instruction collection
- ✅ Agent should respond when directly addressed
- ✅ Agent should translate in real-time if requested
- ✅ Agent should read back all collected instructions accurately
- ✅ Agent should allow corrections during verification

### Testing Follow-up Call Scheduling

Test the system's ability to schedule and manage follow-up calls based on discharge orders.

#### 1. Generate Sample Calls

You can generate test calls using the CLI tool or inline Python:

**Using the CLI Tool (Recommended):**

```bash
# Generate calls for a specific test patient
docker compose exec postop-scheduler python tools/call_scheduler_cli.py generate-test-calls \
    --patient-name "John Doe" \
    --phone "+1234567890" \
    --orders "vm_compression,vm_activity,vm_medication"

# Simulate multiple patient discharges
docker compose exec postop-scheduler python tools/call_scheduler_cli.py simulate-discharge \
    --patient-count 5
```

**Using Inline Python:**

```bash
# Create test calls for a sample patient
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
from datetime import datetime
import json

scheduler = CallScheduler()

# Generate calls for a test patient
calls = scheduler.generate_calls_for_patient(
    patient_id='test-patient-001',
    patient_phone='+1234567890',
    patient_name='Test Patient',
    discharge_time=datetime.now(),
    selected_order_ids=['vm_compression', 'vm_activity', 'vm_medication']
)

print(f'Generated {len(calls)} follow-up calls')
for call in calls:
    print(f'- {call.call_type.value} scheduled for {call.scheduled_time}')
"
```

#### 2. Check Scheduled Calls

**Using the CLI Tool (Recommended):**

```bash
# View pending calls with patient grouping
docker compose exec postop-scheduler python tools/call_scheduler_cli.py list-pending --limit 10

# View all calls with status filtering
docker compose exec postop-scheduler python tools/call_scheduler_cli.py list-all-calls --status PENDING

# Get comprehensive statistics
docker compose exec postop-scheduler python tools/call_scheduler_cli.py stats
```

**Using Inline Python:**

```bash
# View all pending calls in Redis
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
calls = scheduler.get_pending_calls()
print(f'Found {len(calls)} pending calls:')
for call in calls:
    print(f'- ID: {call.id}')
    print(f'  Type: {call.call_type.value}')
    print(f'  Patient: {call.patient_phone}')
    print(f'  Scheduled: {call.scheduled_time}')
    print(f'  Status: {call.status.value}')
    print()
"
```

#### 3. Test Call Execution (Mock)

**Using the CLI Tool (Recommended):**

```bash
# Execute a specific call with mock mode
docker compose exec postop-scheduler python tools/call_scheduler_cli.py execute-call <call-id> --mock

# Or list calls first to get an ID
docker compose exec postop-scheduler python tools/call_scheduler_cli.py list-pending --limit 1
# Then use the displayed call ID
```

**Using Inline Python:**

```bash
# Test the call execution workflow (without actually making calls)
docker compose exec postop-worker python -c "
from scheduling.tasks import execute_followup_call
from scheduling.scheduler import CallScheduler
from scheduling.models import CallStatus

scheduler = CallScheduler()
calls = scheduler.get_pending_calls(limit=1)

if calls:
    call = calls[0]
    print(f'Testing execution of call: {call.id}')

    # Update call status to simulate execution
    scheduler.update_call_status(call.id, CallStatus.IN_PROGRESS, 'Test execution started')
    print('Call marked as IN_PROGRESS')

    # Simulate completion
    scheduler.update_call_status(call.id, CallStatus.COMPLETED, 'Test execution completed')
    print('Call marked as COMPLETED')
else:
    print('No pending calls found. Generate some calls first.')
"
```

### Testing Medical Knowledge RAG

Test the medical knowledge retrieval system that agents use to answer patient questions.

#### 1. Test Knowledge Search

```bash
# Search for medical knowledge
docker compose exec postop-agent python -c "
from discharge.medical_rag import MedicalRAGHandler
import os

try:
    rag = MedicalRAGHandler(
        index_path='data/medical_rag',
        data_path='data/medical_rag/knowledge.pkl'
    )

    # Test search queries
    queries = [
        'compression bandage care',
        'post operative pain management',
        'wound infection signs',
        'activity restrictions after surgery'
    ]

    for query in queries:
        print(f'Query: {query}')
        results = rag.search_knowledge(query, max_results=2)
        for i, result in enumerate(results, 1):
            print(f'  {i}. {result[:100]}...')
        print()

except Exception as e:
    print(f'RAG system not available: {e}')
    print('This is normal if medical knowledge hasn\'t been loaded yet.')
"
```

#### 2. Add Test Knowledge

```bash
# Add sample medical knowledge
docker compose exec postop-agent python discharge/medical_rag.py add-redis \
    "Remove compression bandages 24-48 hours after surgery. Keep the wound clean and dry. Watch for signs of infection including redness, swelling, or discharge." \
    "wound_care"

docker compose exec postop-agent python discharge/medical_rag.py add-redis \
    "Take prescribed pain medication as directed. Ibuprofen 400mg every 6-8 hours is typical for post-operative pain. Do not exceed maximum daily dose." \
    "pain_management"
```

### Testing Redis Data Storage

Verify that call data is being stored and retrieved correctly from Redis.

#### 1. Check Redis Keys

```bash
# View all PostOp-related keys in Redis
docker compose exec postop-redis redis-cli keys "postop:*"
```

#### 2. Inspect Call Data

```bash
# Look at stored call data
docker compose exec postop-redis redis-cli --scan --pattern "postop:calls:*" | head -5 | while read key; do
    echo "Key: $key"
    docker compose exec postop-redis redis-cli get "$key" | python -m json.tool
    echo "---"
done
```

### Integration Testing Workflow

Test the complete end-to-end workflow:

#### 1. Complete Patient Journey

```bash
# Run the advanced integration test
docker compose exec postop-scheduler python -c "
import sys
sys.path.append('/home/appuser')
exec(open('tests/integration/test_advanced_integration.py').read())
"
```

#### 2. Monitor System Activity

```bash
# Watch logs in real-time while testing
docker compose logs -f --tail=20

# In another terminal, monitor Redis activity
docker compose exec postop-redis redis-cli monitor
```

### Troubleshooting Test Issues

**Agent won't start:**

```bash
# Check agent logs
docker compose logs postop-agent --tail=20

# Verify environment variables
docker compose exec postop-agent env | grep -E "(LIVEKIT|DEEPGRAM|OPENAI|ELEVENLABS|AGENT_NAME)"
```

**No calls being generated:**

```bash
# Check scheduler logs
docker compose logs postop-scheduler --tail=20

# Verify Redis connection
docker compose exec postop-scheduler python -c "
from config.redis import test_redis_connection
print('Redis connected:', test_redis_connection())
"
```

**Medical RAG not working:**

```bash
# Check if medical knowledge exists
docker compose exec postop-agent ls -la data/medical_rag/

# Test Redis vector backend
docker compose exec postop-agent python discharge/medical_rag.py search-redis "test query"
```

### Expected Test Results

After successful testing, you should see:

- ✅ Discharge agent collects and verifies instructions accurately
- ✅ Follow-up calls are scheduled and stored in Redis
- ✅ Call execution workflow updates statuses correctly
- ✅ Medical knowledge RAG returns relevant results
- ✅ All services maintain healthy Redis connections
- ✅ No error messages in service logs

### Next Steps After Testing

Once local testing is successful:

1. **Production Deployment**: Follow the production deployment guide below
2. **SIP Integration**: Configure your SIP trunk for actual phone calls
3. **Monitoring Setup**: Implement logging and monitoring for production use
4. **Load Testing**: Test with multiple concurrent calls if needed

### CLI Tools Available

The project includes comprehensive CLI tools for testing and management:

#### Demo Call Trigger CLI (`tools/demo_call_trigger.py`) 🎬

**Purpose**: Live demonstration and immediate call execution

```bash
# List available calls for demo
python tools/demo_call_trigger.py list-calls --demo-ready-only

# Execute a call immediately (mock or real)
python tools/demo_call_trigger.py execute <call-id> --mock

# Create demo calls with instant execution
python tools/demo_call_trigger.py create-demo-call --name "Sarah Johnson" --type compression_reminder --execute-now

# Test LLM analysis flow with demo data
python tools/demo_call_trigger.py test-llm-flow --patient-name "Demo Patient"

# Run complete demo scenario (discharge → analysis → call)
python tools/demo_call_trigger.py demo-scenario

# Clear all demo data
python tools/demo_call_trigger.py clear-demo-data --confirm
```

#### Call Scheduler CLI (`tools/call_scheduler_cli.py`)

**Purpose**: Production call scheduling and management

```bash
# Available commands
python tools/call_scheduler_cli.py --help

# Common usage examples
python tools/call_scheduler_cli.py generate-test-calls --patient-name "Jane Doe" --phone "+15551234567"
python tools/call_scheduler_cli.py simulate-discharge --patient-count 10
python tools/call_scheduler_cli.py list-pending --upcoming-only
python tools/call_scheduler_cli.py stats
python tools/call_scheduler_cli.py clear-test-data
python tools/call_scheduler_cli.py redis-status
```

#### Medical Knowledge CLI (`tools/medical_knowledge_cli.py`)

**Purpose**: Medical RAG knowledge base management

```bash
# Available commands
python tools/medical_knowledge_cli.py --help

# Common usage examples
python tools/medical_knowledge_cli.py list --limit 10
python tools/medical_knowledge_cli.py search "pain management"
python tools/medical_knowledge_cli.py add --text "Medical knowledge here"
python tools/medical_knowledge_cli.py stats
```

### Production Call Generation

In production, follow-up calls are generated when patients are discharged from medical facilities. Here's how the system is designed to work:

#### Integration Options

**Option 1: EMR/EHR Integration (Recommended)**

- **Hospital Integration**: EMR system calls PostOp API when patient is discharged
- **Data Passed**: Patient ID, phone, discharge orders, discharge time
- **Authentication**: API key or OAuth integration
- **Example Integration**:

```python
# Called by hospital EMR system when patient is discharged
from scheduling.scheduler import CallScheduler

def handle_patient_discharge(patient_data):
    scheduler = CallScheduler()

    calls = scheduler.generate_calls_for_patient(
        patient_id=patient_data['patient_id'],
        patient_phone=patient_data['phone'],
        patient_name=patient_data['name'],
        discharge_time=patient_data['discharge_time'],
        selected_order_ids=patient_data['discharge_orders']
    )

    # Schedule all generated calls
    for call in calls:
        scheduler.schedule_call(call)

    return {"status": "success", "calls_scheduled": len(calls)}
```

**Option 2: Manual Scheduling Interface**

- **Web Dashboard**: Hospital staff manually enter patient information
- **Batch Upload**: CSV/Excel import for multiple patients
- **Verification**: Staff review and approve call schedules

**Option 3: HL7 FHIR Integration**

- **Standard Protocol**: Receive discharge summaries via FHIR
- **Automated Processing**: Parse FHIR documents for relevant discharge orders
- **Compliance**: Maintains healthcare data standards

#### Production Workflow

```mermaid
graph TD
    A[Patient Discharged] --> B[EMR System]
    B --> C[PostOp API Call]
    C --> D[Call Scheduler]
    D --> E[Generate Calls from Discharge Orders]
    E --> F[Store in Redis]
    F --> G[Scheduler Daemon Picks Up]
    G --> H[Execute Calls via LiveKit]
    H --> I[Update Call Status]
    I --> J[Generate Reports]
```

#### Required Integration Points

**For Production Deployment, you'll need:**

1. **API Endpoint** (not yet implemented):

   ```bash
   # Future endpoint structure
   POST /api/v1/patients/discharge
   {
     "patient_id": "PAT123456",
     "patient_name": "John Smith",
     "patient_phone": "+15551234567",
     "discharge_time": "2025-01-15T14:30:00Z",
     "discharge_orders": ["vm_compression", "vm_activity", "vm_medication"],
     "facility_id": "HOSP001"
   }
   ```

2. **Authentication System**:
   - API keys for hospital systems
   - Role-based access control
   - Audit logging for all discharge events

3. **Webhook Endpoints** (optional):
   - Call status updates back to EMR
   - Patient response summaries
   - Emergency escalation alerts

4. **Data Validation**:
   - Phone number formatting and validation
   - Discharge order validation against available templates
   - Patient consent verification

**Current Status**:

- ✅ **Core System Complete**: Scheduling engine, LLM analysis, Redis storage, LiveKit integration
- ✅ **Demo System**: Comprehensive CLI tools for live demonstrations and testing
- ✅ **Medical RAG**: Hybrid Redis/Annoy knowledge base with function tools
- 🚧 **Production APIs**: REST endpoints for EMR integration (planned)
- 🚧 **Web Dashboard**: Patient call management interface (planned)

**LLM-Powered Features**:

- **Transcript Analysis**: Automatically analyzes discharge instructions and generates personalized call schedules
- **Dynamic Call Types**: LLM determines optimal call types based on medical complexity
- **Intelligent Scheduling**: Context-aware timing based on procedure requirements and patient needs
- **Medical Knowledge Integration**: Real-time RAG lookup during calls for accurate medical guidance

## System Architecture

The system consists of six integrated components:

### Core Components

- **PostOp Agent**: LiveKit voice agent with medical RAG integration for intelligent call handling
- **LLM Analysis Engine**: GPT-4 powered transcript analysis that generates personalized call schedules
- **Call Scheduler**: Redis-based scheduling with intelligent timing and retry logic
- **Task Worker**: RQ-based asynchronous call execution with LiveKit SIP integration
- **Medical RAG**: Hybrid Redis/Annoy knowledge base for real-time medical question answering
- **Demo System**: Comprehensive CLI tools for live demonstrations and testing

### Data Flow

```
[Discharge Instructions] → [LLM Analysis] → [Personalized Calls] → [Redis Storage] → [Scheduled Execution] → [LiveKit Voice Agent] → [Patient Interaction]
                                                                                                                                    ↓
[Follow-up Analysis] ← [Call Recording] ← [Conversation Summary] ← [Medical RAG Lookup] ← [Dynamic Response Generation]
```

### Integration Points

- **LiveKit SIP**: Inbound/outbound telephony with automatic agent dispatch
- **Redis Storage**: Persistent call data, task queues, and vector embeddings
- **OpenAI GPT-4**: Discharge instruction analysis and conversation generation
- **Medical Knowledge**: Real-time RAG retrieval for accurate patient guidance

## Production Deployment

### Production vs Development

| Component      | Development      | Production                    |
| -------------- | ---------------- | ----------------------------- |
| **Redis**      | Docker container | DigitalOcean ValKey (managed) |
| **Compute**    | Local Docker     | DigitalOcean Droplet          |
| **Scaling**    | Fixed containers | Manual/vertical scaling       |
| **Backups**    | None             | Automated daily backups       |
| **Monitoring** | Docker logs      | System monitoring + logs      |
| **SSL/TLS**    | Not required     | Required for ValKey           |

### Prerequisites

- DigitalOcean account
- LiveKit account with SIP trunk configured
- API keys for OpenAI, Deepgram, ElevenLabs

### 1. Create DigitalOcean Droplet

**Recommended Configuration:**

- **Size**: 8GB RAM, 4 CPU ($48/month)
- **Region**: Choose closest to your users for voice latency
- **Image**: Ubuntu 22.04 LTS
- **Authentication**: Add your SSH keys

### 2. Initial Server Setup

SSH into your droplet and run:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
sudo apt install -y docker.io docker-compose-plugin git

# Add user to docker group (logout/login required)
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker installation
docker --version
docker compose version
```

### 3. Set Up DigitalOcean ValKey (Managed Redis)

1. **Create ValKey Database**:
   - Go to DigitalOcean Databases → Create Database
   - Select **ValKey** as engine
   - Choose region close to your droplet
   - Select appropriate size (starts at $15/month)

2. **Get Connection Details**:
   - Copy the connection string (format: `rediss://username:password@host:port/db`)
   - Note: Uses SSL/TLS encryption

### 4. Deploy Application

```bash
# Clone the repository
git clone <your-repository-url> postop-ai
cd postop-ai

# Set up environment variables
cp .env.example .env
nano .env  # Fill in your actual API keys and configuration
```

**Production Environment Variables:**

```bash
# LiveKit Configuration
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# AI Services
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key
ELEVEN_API_KEY=your_elevenlabs_key

# SIP Trunk for outbound calls
SIP_OUTBOUND_TRUNK_ID=ST_your_trunk_id

# DigitalOcean ValKey (replace with your connection string)
REDIS_URL=rediss://username:password@your-valkey-cluster.db.ondigitalocean.com:25061/defaultdb?ssl_cert_reqs=CERT_REQUIRED
```

### 5. Update Docker Compose for Production

Remove the Redis service since you're using managed ValKey:

```bash
# Create production docker-compose override
cat > docker-compose.prod.yml << EOF
version: '3.8'
services:
  # Remove Redis service - using managed ValKey instead
  postop-scheduler:
    environment:
      - REDIS_HOST=  # ValKey connection handled by REDIS_URL
  postop-worker:
    environment:
      - REDIS_HOST=  # ValKey connection handled by REDIS_URL
  postop-agent:
    environment:
      - REDIS_HOST=  # ValKey connection handled by REDIS_URL
EOF
```

### 6. Start Services

```bash
# Build and start all services in background (production mode)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# Verify all services are running
docker compose ps

# Check service logs
docker compose logs -f postop-agent    # Voice agent logs
docker compose logs -f postop-scheduler # Scheduler logs
docker compose logs -f postop-worker   # Worker logs
# Note: No Redis logs since using managed ValKey

# Test ValKey connectivity
docker compose exec postop-scheduler python -c "import redis; r=redis.from_url('$REDIS_URL'); print('ValKey connected:', r.ping())"
```

### 7. Configure Auto-Start on Boot

Create a systemd service to automatically start services on server reboot:

```bash
# Create systemd service file
sudo tee /etc/systemd/system/postop-ai.service << EOF
[Unit]
Description=PostOp AI Services
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/$USER/postop-ai
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml down
TimeoutStartSec=0
User=$USER
Group=docker

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable postop-ai
sudo systemctl start postop-ai

# Check service status
sudo systemctl status postop-ai
```

### 8. Backups (Managed by ValKey)

**Automatic Backups**: DigitalOcean ValKey handles backups automatically:

- **Daily backups**: Retained for 7 days
- **Point-in-time recovery**: Available through DO dashboard
- **Manual snapshots**: Can be created on-demand

**No backup scripts needed** - ValKey manages data persistence and recovery.

### 9. Configure Firewall

```bash
# Enable UFW firewall
sudo ufw enable

# Allow SSH
sudo ufw allow ssh

# Allow HTTP/HTTPS (if you add a web interface later)
sudo ufw allow 80
sudo ufw allow 443

# Check firewall status
sudo ufw status
```

## Service Management

### Common Commands

```bash
# View all service status
docker compose ps

# Restart specific service
docker compose restart postop-agent

# View real-time logs
docker compose logs -f

# Update and redeploy
git pull
docker compose up --build -d

# Stop all services
docker compose down

# Clean up unused Docker resources
docker system prune -f
```

### Monitoring Service Health

```bash
# Check ValKey connectivity
docker compose exec postop-scheduler python -c "import redis; r=redis.from_url('$REDIS_URL'); print('Connected:', r.ping())"

# Check scheduled calls in ValKey (from any service container)
docker compose exec postop-scheduler python -c "import redis; r=redis.from_url('$REDIS_URL'); print('Keys:', r.keys('postop:*'))"

# Monitor system resources
htop
df -h

# Check ValKey metrics in DigitalOcean dashboard
# - Memory usage
# - Connection count
# - Operations per second
```

### Troubleshooting

**Service won't start:**

```bash
# Check service logs
docker compose logs service-name

# Rebuild containers
docker compose down
docker compose up --build -d
```

**Out of disk space:**

```bash
# Clean up Docker
docker system prune -a -f

# Check disk usage
df -h
du -sh /var/lib/docker
```

**High memory usage:**

```bash
# Check container memory usage
docker stats

# Restart services if needed
docker compose restart
```

## Scaling Considerations

As your call volume grows, consider:

1. **Vertical Scaling**: Upgrade to larger droplet (16GB RAM, 8 CPU)
2. **Horizontal Scaling**: Add additional worker instances with `docker compose up --scale postop-worker=3`
3. **ValKey Scaling**: Upgrade ValKey cluster size in DigitalOcean dashboard
4. **Load Balancing**: Distribute voice agents across multiple servers
5. **Migration to Fly.io**: For auto-scaling and global distribution
6. **Multi-Region**: Deploy ValKey clusters in multiple regions

## Security Notes

- Keep all API keys in `.env` file (never commit to Git)
- Regularly update Docker images and system packages
- Monitor logs for suspicious activity
- Use strong SSH keys and disable password authentication
- Consider setting up fail2ban for additional protection

## Support

For issues and questions, check the troubleshooting section above or review service logs using `docker compose logs -f`.
