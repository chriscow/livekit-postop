# PostOp AI Outbound Call Demo Guide

This guide demonstrates the complete outbound calling system with both automatic callbacks after discharge and manual test calls. You'll see real-time call scheduling, observability, and execution.

## Prerequisites

✅ **Local agent running:**
```bash
./start_agent.sh
# Should show "PostOp AI agent in development mode"
```

✅ **Your phone ready** - you'll receive real outbound calls  
✅ **Redis running** - for call scheduling and storage  
✅ **RQ workers active** - for background call execution

---

## Quick Demo Commands

### Essential Scripts
```bash
./reset_demo.sh                    # Clear all demo data, restore medical knowledge
./start_agent.sh                   # Start the unified agent system
./show_pending_calls.sh             # Real-time call status with countdown timers
./trigger_outbound_call.sh create +phone 'Name'  # Create test calls
./trigger_outbound_call.sh <call_id>              # Execute call immediately
```

---

## Part 1: Complete End-to-End Demo (15 minutes)

### Step 1.1: Reset and Start System

```bash
# 1. Clear any previous demo data
./reset_demo.sh
# Confirm: y

# 2. Start the unified agent
./start_agent.sh
```

You should see:
```
🚀 Starting PostOp AI agent in development mode...
📞 Inbound calls: +1 (844) 970-1900 → Discharge collection  
📱 Outbound calls: Automatic courtesy callbacks after discharge
```

### Step 1.2: Complete Discharge Demo

**📞 Call +1 (844) 970-1900** from your phone.

**Follow the conversation flow:**

1. **Recording Consent**
   - Agent: *"Hi there! I'm Vince from PostOp AI... May I record this call?"*
   - **You:** `"Yes, I consent to recording"`

2. **Patient Setup**
   - Agent: *"What's the patient's name?"*
   - **You:** `"Demo Patient"`
   - Agent: *"What language does Demo Patient prefer?"*
   - **You:** `"English"`
   - Agent: *"What's the best phone number to reach Demo Patient?"*
   - **You:** `"[YOUR_PHONE_NUMBER]"`

3. **Discharge Instructions**
   - Agent: *"Go ahead and read through the discharge instructions..."*
   
   **You read:**
   ```
   "Demo Patient had a minor surgical procedure today. Here are the discharge instructions:
   
   Remove the compression bandage in 24 hours. Keep the wound clean and dry.
   Take ibuprofen 400mg every 6 hours as needed for pain.
   Avoid heavy lifting for 48 hours, then gradually return to normal activities.
   Watch for signs of infection including redness, swelling, or fever over 101°F.
   Call our office if you have any concerns."
   ```

4. **Completion**
   - **You:** `"That completes all the discharge instructions"`
   - Agent: *"Let me read back what I collected..."*
   - **You:** Confirm accuracy
   - Agent: *"Perfect! I've confirmed all instructions are accurate... I've scheduled a quick courtesy call in 30 seconds..."*

### Step 1.3: Monitor Automatic Callback

**Immediately after the call ends:**

```bash
# Check for the scheduled courtesy call
./show_pending_calls.sh
```

You should see:
```
📞 PostOp AI - Pending Calls Status
================================
✅ Redis connection: OK

📋 Found 1 pending call(s):

1. 📞 Call ID: abc12345...
   👤 Patient: Demo Patient
   📱 Phone: +14258295443  
   📅 Scheduled: 2025-07-30 10:30:15 (in 25 seconds)
   🔄 Status: PENDING ⏱️  IN 25s
   🎯 Type: wellness_check
   ⭐ Priority: 2
   💬 Message: Hi Demo Patient, this is Vince from PostOp AI calling to check...
```

**Wait for the countdown** - your phone will ring automatically!

### Step 1.4: Answer the Courtesy Callback

Within 30 seconds, you should receive a call:

**Expected conversation:**
- **Agent:** *"Hi Demo Patient, this is Vince from PostOp AI calling to check how you're doing after your procedure. Do you have any questions about your discharge instructions that we just went over?"*

**Test the agent's knowledge by asking:**
- *"How should I care for my wound?"*
- *"What pain medication should I take?"*
- *"When can I return to normal activities?"*
- *"What are signs of infection?"*

The agent should provide relevant answers based on the medical knowledge and discharge instructions.

---

## Part 2: Manual Call Testing (10 minutes)

### Step 2.1: Create Test Calls

```bash
# Create a test call for immediate execution
./trigger_outbound_call.sh create +14258295443 'Test Patient' 5

# Create another call with default timing
./trigger_outbound_call.sh create +14258295443 'Another Patient'
```

### Step 2.2: Monitor Call Status

```bash
# Check all pending calls
./show_pending_calls.sh
```

You'll see multiple calls with different timing:
```
📋 Found 2 pending call(s):

1. 📞 Call ID: def67890...
   👤 Patient: Test Patient
   📱 Phone: +14258295443
   📅 Scheduled: 2025-07-30 10:35:20 (in 3 seconds)
   🔄 Status: PENDING ⏱️  IN 3s

2. 📞 Call ID: ghi12345...
   👤 Patient: Another Patient  
   📱 Phone: +14258295443
   📅 Scheduled: 2025-07-30 10:35:30 (in 13 seconds)
   🔄 Status: PENDING ⏱️  IN 13s
```

### Step 2.3: Manual Trigger

```bash
# Execute a specific call immediately (optional)
./trigger_outbound_call.sh def67890

# Or wait for automatic execution
```

---

## Part 3: Advanced Testing (5 minutes)

### Step 3.1: Multiple Call Management

```bash
# Create several test calls
./trigger_outbound_call.sh create +14258295443 'Patient A' 30
./trigger_outbound_call.sh create +14258295443 'Patient B' 60  
./trigger_outbound_call.sh create +14258295443 'Patient C' 90

# Monitor the queue
./show_pending_calls.sh
```

### Step 3.2: Real-Time Status Updates

```bash
# Watch calls progress from PENDING to execution
watch -n 5 ./show_pending_calls.sh
# Press Ctrl+C to stop watching
```

### Step 3.3: Reset for Another Demo

```bash
# Clear everything and start fresh
./reset_demo.sh
# Confirm: y

# Verify clean state
./show_pending_calls.sh
# Should show: "No pending calls found"
```

---

## Part 4: Demo Script Scenarios

### Scenario A: Quick Demo (5 minutes)
```bash
# 1. Reset system
./reset_demo.sh

# 2. Create immediate test call
./trigger_outbound_call.sh create +14258295443 'Quick Demo' 10

# 3. Show status
./show_pending_calls.sh

# 4. Answer the call when it comes
```

### Scenario B: Full Workflow Demo (15 minutes)
```bash
# 1. Reset system  
./reset_demo.sh

# 2. Start agent
./start_agent.sh

# 3. Call +1 (844) 970-1900 for discharge demo
# 4. Monitor automatic callback
./show_pending_calls.sh

# 5. Answer courtesy call
# 6. Create additional test calls
./trigger_outbound_call.sh create +14258295443 'Follow-up Test'
```

### Scenario C: Stress Test (10 minutes)
```bash
# 1. Reset system
./reset_demo.sh

# 2. Create multiple calls
for i in {1..5}; do
  ./trigger_outbound_call.sh create +14258295443 "Patient $i" $((i * 15))
done

# 3. Monitor execution
./show_pending_calls.sh

# 4. Watch them execute in sequence
```

---

## Expected Demo Results ✅

After completing this demo, you should have:

### ✅ **Automatic Callback System**
- Discharge call completion triggers automatic outbound call
- 30-second delay for demo timing
- Real-time status monitoring with countdown
- Professional courtesy call execution

### ✅ **Manual Call Control**
- Create test calls with custom timing
- Execute calls immediately when needed
- Multiple calls queued and managed automatically
- Complete observability into call status

### ✅ **Real-Time Observability**
- Live countdown timers showing when calls execute
- Complete call metadata and status tracking
- Patient information and prompt previews
- Management commands for full control

### ✅ **Clean Demo Environment**
- Reset script clears all demo data
- Medical knowledge automatically restored
- Fresh start for multiple demo runs
- No leftover test data between sessions

---

## Troubleshooting

### 🚨 **No Automatic Callback After Discharge**

Check if the courtesy call was scheduled:
```bash
./show_pending_calls.sh
# Should show a call scheduled 30 seconds after discharge completion
```

If no call appears, check the discharge agent logs for errors.

### 🚨 **Outbound Calls Not Executing**

Verify RQ workers are running:
```bash
docker-compose ps
# postop-worker and postop-scheduler should be "Up"
```

Check SIP configuration:
```bash
echo $SIP_OUTBOUND_TRUNK_ID
# Should show: ST_8zHmZFF2QGVW (or similar)
```

### 🚨 **Scripts Show Environment Errors**

Ensure .env is properly loaded:
```bash
source .env
echo $LIVEKIT_AGENT_NAME
# Should show: postop-ai
```

All scripts automatically load .env, but manual verification helps debugging.

### 🚨 **Redis Connection Issues**

Check Redis status:
```bash
redis-cli ping
# Should respond: PONG

# Or check Docker Redis
docker-compose ps redis
```

---

## Demo Tips & Best Practices

### 🎯 **For Live Presentations**
1. **Pre-demo**: Run `./reset_demo.sh` to ensure clean state
2. **Start**: Always begin with `./start_agent.sh` 
3. **Monitor**: Keep `./show_pending_calls.sh` ready for status checks
4. **Backup**: Have `./trigger_outbound_call.sh create` ready for manual calls

### 📱 **Phone Number Management**
- Use your real phone number for authentic demo experience
- System works with any valid phone number format
- International numbers supported with country codes

### ⏰ **Timing Control**
- Automatic callbacks: 30 seconds (perfect for demos)
- Manual calls: Configurable delay (5-120 seconds recommended)
- Real-time countdowns prevent "waiting around"

### 🔧 **Script Combinations**
```bash
# Reset → Start → Monitor (most common)
./reset_demo.sh && ./start_agent.sh

# Quick test call sequence  
./trigger_outbound_call.sh create +phone 'Test' 10 && ./show_pending_calls.sh

# Status monitoring during live demo
watch -n 2 ./show_pending_calls.sh
```

---

**Congratulations! You now have complete control over the PostOp AI outbound calling system! 🎉**

The system provides professional-grade observability and control perfect for impressive demonstrations.