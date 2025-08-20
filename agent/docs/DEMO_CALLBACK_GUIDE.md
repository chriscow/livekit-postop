# PostOp AI Complete System Demo Guide

This guide walks you through a complete demonstration of the PostOp AI system, including both discharge instruction collection and automated callback functionality.

## Prerequisites

✅ **Verify all Docker services are running:**
```bash
docker compose ps
# All services should show "Up" status
```

✅ **Check that you have your phone ready** - you'll receive an actual call from the system!

---

## Part 1: Set Up Your Demo Callback Call (5 minutes)

### Step 1.1: Update Callback Call with Your Phone Number

**Replace `+1YOUR_PHONE_NUMBER` with your actual phone number:**

```bash
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
scheduler.redis_client.hset('postop:scheduled_calls:ee7c588e-eb45-45a3-b83e-e4829ba1146d', 'patient_phone', '+15551234567')  # ← Update this number
print('Phone number updated!')"
```

### Step 1.2: Verify Callback Call is Ready

```bash
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
call_data = scheduler.redis_client.hgetall('postop:scheduled_calls:ee7c588e-eb45-45a3-b83e-e4829ba1146d')
phone = call_data[b'patient_phone'].decode()
scheduled = call_data[b'scheduled_time'].decode()
print(f'✅ Callback ready for: {phone}')
print(f'⏰ Scheduled for: {scheduled}')
print('📞 This call will execute automatically in ~1 minute!')
"
```

**📝 Expected Output:**
```
✅ Callback ready for: +15551234567
⏰ Scheduled for: 2025-07-29T16:48:14.366720
📞 This call will execute automatically in ~1 minute!
```

---

## Part 2: Test Discharge Session (10 minutes)

### Step 2.1: Start Discharge Agent in Console Mode

Open a new terminal window and run:

```bash
docker compose exec postop-agent python main.py discharge console
```

### Step 2.2: Follow the Conversation Flow

The agent will guide you through the process. Respond exactly as shown:

**1. Recording Consent**
- Agent asks: *"Do you consent to having this session recorded?"*
- **You say:** `"Yes, you may record this session"`

**2. Patient Name**
- Agent asks: *"What is the patient's name?"*
- **You say:** `"John Smith"` (or your preferred test name)

**3. Language Preference** 
- Agent asks: *"What language would you prefer for the instructions?"*
- **You say:** `"English"`

**4. Discharge Instructions Reading**
- Agent says: *"I'm now ready to listen to the discharge instructions..."*
- **You read this text slowly and clearly:**

```
"Remove the compression bandage in 24 hours. Keep the wound clean and dry. 
Take ibuprofen 400mg every 6 hours for pain relief. You can return to school 
in 3 days. Call us immediately if you see any signs of infection like redness, 
swelling, or unusual discharge from the wound."
```

**5. End Instructions Signal**
- After reading, **you say:** `"That completes all the discharge instructions"`

**6. Verification**
- Agent will read back the collected instructions
- **You say:** `"Yes, that's correct"` or make corrections if needed

**7. Completion**
- Agent will confirm completion and may mention follow-up call scheduling
- The session should end automatically

### Step 2.3: Expected Agent Behavior

✅ **During instruction reading:** Agent should remain mostly silent, only responding if directly addressed  
✅ **During verification:** Agent should accurately read back all instructions  
✅ **Medical knowledge:** Agent can answer questions using the RAG system  
✅ **Professional tone:** Agent should maintain medical professionalism throughout

---

## Part 3: Monitor Your Callback Call (15 minutes)

### Step 3.1: Open Monitoring Terminal

In another terminal window, start monitoring:

```bash
# Watch worker logs for call execution
docker compose logs -f postop-worker
```

### Step 3.2: Check for Due Calls

Run this command every minute to see when your callback becomes due:

```bash
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
from datetime import datetime
scheduler = CallScheduler()

print(f'🕐 Current time: {datetime.now()}')
due_calls = scheduler.get_pending_calls(limit=5)
print(f'📞 Due calls: {len(due_calls)}')
for call in due_calls:
    print(f'  {call.id[:8]}...: {call.call_type.value} -> {call.patient_phone}')
    print(f'    Scheduled: {call.scheduled_time}')
"
```

### Step 3.3: Answer Your Phone!

**Within 1-2 minutes, you should receive a call:**

1. **Phone rings** - Answer it!
2. **Agent introduces:** *"Hello, this is Vince from PostOp AI..."*
3. **Agent delivers message:** About verifying the system is working
4. **Agent asks questions:** About discharge instructions or concerns
5. **Have a conversation:** Test the agent's medical knowledge by asking questions like:
   - "How should I care for my wound?"
   - "What pain medication should I take?"
   - "When can I return to normal activities?"

### Step 3.4: Expected Call Experience

✅ **Clear audio quality** using ElevenLabs voice synthesis  
✅ **Intelligent responses** powered by GPT-4 and medical RAG  
✅ **Natural conversation** with appropriate pauses and responses  
✅ **Medical accuracy** when answering wound care and medication questions

---

## Part 4: Verify System Integration (5 minutes)

### Step 4.1: Check Medical Knowledge System

```bash
docker compose exec postop-agent python -c "
import redis
import os
r = redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'))
keys = r.keys('medical_knowledge:*')
print(f'✅ Medical knowledge entries: {len(keys)}')
for key in keys[:2]:
    data = r.hgetall(key)
    category = data[b'category'].decode()
    text = data[b'text'].decode()[:60]
    print(f'  {category}: {text}...')
"
```

**📝 Expected Output:**
```
✅ Medical knowledge entries: 4
  wound_care: Remove compression bandages 24-48 hours after surgery. Keep...
  pain_management: Take prescribed pain medication as directed. Ibuprofen...
```

### Step 4.2: Check Call System Status

```bash
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
r = scheduler.redis_client
call_keys = [k for k in r.keys('postop:scheduled_calls:*') if b'-' in k]
print(f'✅ Total calls in system: {len(call_keys)}')

# Check your demo call status
call_data = r.hgetall('postop:scheduled_calls:ee7c588e-eb45-45a3-b83e-e4829ba1146d')
status = call_data[b'status'].decode()
print(f'📞 Demo call status: {status}')
"
```

### Step 4.3: Verify Agent Connection

```bash
docker compose logs postop-agent --tail 5
```

**📝 Look for:** Lines showing "registered worker" and LiveKit connection status

---

## Part 5: Generate Additional Test Calls (Optional)

### Step 5.1: Create More Patient Calls

```bash
# Generate calls for multiple patients
docker compose exec postop-scheduler python tools/call_scheduler_cli.py generate-test-calls \
    --patient-name "Jane Doe" \
    --phone "+15559876543" \
    --orders "vm_compression,vm_activity,vm_medication"
```

### Step 5.2: View All Scheduled Calls

```bash
docker compose exec postop-scheduler python -c "
from scheduling.scheduler import CallScheduler
scheduler = CallScheduler()
r = scheduler.redis_client

# Get all call keys and display details
call_keys = [k for k in r.keys('postop:scheduled_calls:*') if b'-' in k]
print(f'📞 All scheduled calls ({len(call_keys)}):')

for key in call_keys:
    call_data = r.hgetall(key)
    call_id = key.decode().split(':')[2]
    status = call_data[b'status'].decode()
    phone = call_data[b'patient_phone'].decode()
    call_type = call_data[b'call_type'].decode()
    scheduled = call_data[b'scheduled_time'].decode()
    
    print(f'  {call_id[:8]}...: {call_type} -> {phone} [{status}]')
    print(f'    Scheduled: {scheduled}')
    print()
"
```

---

## Expected Demo Results ✅

After completing this demo, you should have:

### ✅ **Successful Discharge Session**
- Agent collected discharge instructions accurately
- Agent provided verification and confirmation
- Session completed professionally without errors

### ✅ **Working Callback System**
- Received automated phone call within 1-2 minutes
- Clear voice quality and natural conversation
- Agent demonstrated medical knowledge when asked questions
- Call completed successfully

### ✅ **System Integration Verified**
- All Docker services healthy and running
- Medical knowledge RAG system functional
- Redis storage maintaining call data
- LiveKit agent connected and responsive

### ✅ **Production-Ready Features**
- Real-time call scheduling and execution
- Medical knowledge lookup during calls
- Professional voice synthesis
- Comprehensive error handling

---

## Troubleshooting

### 🚨 **Callback Call Not Received**

**Check if call is overdue:**
```bash
docker compose exec postop-scheduler python -c "
from datetime import datetime
print(f'Current time: {datetime.now()}')
print('Call was scheduled for 2025-07-29 16:48:14')
print('If current time is past scheduled time, call should have executed')
"
```

**Manually trigger call execution:**
```bash
docker compose exec postop-worker python -c "
from scheduling.tasks import execute_followup_call
execute_followup_call('ee7c588e-eb45-45a3-b83e-e4829ba1146d')
"
```

### 🚨 **Discharge Agent Won't Start**

**Check agent logs:**
```bash
docker compose logs postop-agent --tail 20
```

**Verify environment variables:**
```bash
docker compose exec postop-agent python -c "
import os
required_vars = ['LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'LIVEKIT_URL', 'DEEPGRAM_API_KEY', 'OPENAI_API_KEY', 'ELEVEN_API_KEY', 'AGENT_NAME']
for var in required_vars:
    value = os.getenv(var, 'NOT SET')
    print(f'{var}: {\"SET\" if value != \"NOT SET\" else \"NOT SET\"}')
"
```

### 🚨 **No Medical Knowledge Available**

**Re-add medical knowledge:**
```bash
docker compose exec postop-agent python -c "
import redis
import os

r = redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'))
knowledge_items = [
    ('Remove compression bandages 24-48 hours after surgery. Keep wound clean and dry.', 'wound_care'),
    ('Take prescribed pain medication as directed. Ibuprofen 400mg every 6-8 hours.', 'pain_management'),
    ('Resume normal activities gradually. Avoid heavy lifting over 10 pounds for first week.', 'activity_guidance'),
    ('Call healthcare provider immediately if you experience severe pain, signs of infection, or fever over 101°F.', 'emergency_signs')
]

for i, (text, category) in enumerate(knowledge_items):
    key = f'medical_knowledge:{i}'
    r.hset(key, mapping={'text': text, 'category': category, 'id': str(i)})

print('✅ Medical knowledge restored')
"
```

---

## Next Steps

After completing this demo successfully:

1. **📱 Production Phone Numbers**: Replace test numbers with real patient contacts
2. **🏥 EMR Integration**: Connect to hospital discharge systems
3. **📊 Dashboard**: Build web interface for call management
4. **📈 Monitoring**: Set up production logging and alerts
5. **🔧 Customization**: Adapt prompts and workflows for your specific needs

**Congratulations! You now have a fully operational PostOp AI system! 🎉**