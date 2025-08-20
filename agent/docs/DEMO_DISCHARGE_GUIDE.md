# PostOp AI Discharge Process Demo Guide

This guide demonstrates the complete discharge instruction collection and analysis workflow. You'll call the system with your real phone, provide discharge instructions, and see how the AI analyzes them to generate personalized follow-up calls.

## Prerequisites

✅ **All Docker services running:**
```bash
docker compose ps
# All services should show "Up" status
```

✅ **Your phone ready** - you'll be making a real call to the LiveKit system  
✅ **LiveKit SIP configured** - your system should be able to receive inbound calls

## Enhanced Shell Scripts

All PostOp AI shell scripts now support both Docker and local environments:

```bash
# Auto-detect environment (recommended)
./reset_demo.sh
./show_pending_calls.sh
./trigger_outbound_call.sh list

# Force specific environment
./reset_demo.sh --docker
./show_pending_calls.sh --local
./trigger_outbound_call.sh --docker create +14258295443 'Test Patient'
```

**Auto-detection logic:**
- If Docker containers are running → uses Docker mode
- If local Redis is running → uses local mode
- Validates environment health before proceeding


---

## Demo Reset Command

### Clear All PostOp AI Data and Restore Medical Knowledge

When you want to reset for another demo:

```bash
# Complete PostOp AI data reset with medical knowledge restoration
./reset_demo.sh
```

This script will:
- Auto-detect Docker vs local environment 
- Show you what data will be deleted
- Clear all PostOp call data
- Restore medical knowledge for RAG queries
- Verify the reset was successful

**Manual environment selection:**
```bash
./reset_demo.sh --docker   # Force Docker mode
./reset_demo.sh --local    # Force local mode
```

---

## Part 1: Understand the Discharge Workflow (2 minutes)

### What This Demo Shows

1. **📞 Inbound Call**: You call the PostOp AI system using your real phone
2. **🎤 Instruction Collection**: Agent listens as you provide discharge instructions for a patient
3. **🧠 LLM Analysis**: System analyzes the transcript and identifies key medical instructions
4. **📅 Call Generation**: AI automatically generates personalized follow-up calls based on the content
5. **💾 Storage**: All calls are scheduled and stored in Redis for execution

### Sample Patient Scenario

**Patient:** Sarah Johnson, age 35  
**Procedure:** Varicose vein removal surgery  
**Phone:** Your real phone number (for demo follow-up calls)  
**Discharge Time:** Current time

---

## Part 2: Place Your Discharge Call (10 minutes)

### Step 2.1: Get Your LiveKit Phone Number

Check your LiveKit dashboard or SIP configuration for the inbound phone number. The system should be pre-configured with your phone number routing to the PostOp agent.

### Step 2.2: Call the System

**📞 Dial the LiveKit phone number** from your phone.

The system should:
- Answer within 2-3 rings
- Agent "Vince" introduces himself
- Ask for consent to record
- Begin the discharge instruction collection process

### Step 2.3: Follow the Conversation Flow

**1. Recording Consent**
- Agent: *"Hello, this is Vince from PostOp AI. Do you consent to having this session recorded for quality and training purposes?"*
- **You:** `"Yes, I consent to recording"`

**2. Patient Information**
- Agent: *"Thank you. What is the patient's name?"*
- **You:** `"Sarah Johnson"`

**3. Language Preference**
- Agent: *"What language would you prefer for the discharge instructions?"*
- **You:** `"English"`

**4. Discharge Instructions**
- Agent: *"I'm now ready to listen to the discharge instructions. Please proceed."*

**You read the following discharge instructions clearly:**

```
"Sarah had varicose vein removal surgery today. Here are her discharge instructions:

Remove the compression bandages in 24 hours. After removing the bandages, 
keep the incision sites clean and dry for the first 48 hours. You can shower 
after 48 hours but avoid soaking in baths for one week.

For pain management, take ibuprofen 400mg every 6 hours as needed. You can 
also use acetaminophen 500mg every 8 hours if additional pain relief is needed. 
Avoid aspirin for the first week as it can increase bleeding risk.

Wear the compression stockings for 2 weeks during the day, but you can remove 
them at night while sleeping. This helps prevent swelling and promotes healing.

You can return to light office work in 3 days, but avoid standing for long 
periods. Wait one full week before resuming exercise or heavy lifting. No 
lifting over 15 pounds for the first week.

Watch for signs of infection including increased redness, swelling, warmth, 
or pus from the incision sites. Also call immediately if you develop a fever 
over 101 degrees, severe pain that doesn't improve with medication, or any 
unusual leg swelling.

Schedule a follow-up appointment in 2 weeks to check healing progress. We'll 
also want to see you in 6 weeks for a final evaluation.

Call our office at 555-0123 if you have any questions or concerns. For 
emergencies after hours, go to the nearest emergency room."
```

**5. End Signal**
- **You:** `"That completes all the discharge instructions for Sarah Johnson"`

**6. Verification**
- Agent will read back the key instructions collected
- **You:** Confirm accuracy or make corrections

**7. Patient Contact Information**
- Agent: *"What is the best phone number to reach Sarah for follow-up calls?"*
- **You:** `"Use my number, [YOUR_PHONE_NUMBER], for this demonstration"`

**8. Completion**
- Agent will confirm completion and mention that follow-up calls will be scheduled
- The call should end professionally

---

## Part 3: Monitor LLM Analysis and Call Generation (5 minutes)

### Step 3.1: Check for Transcript Processing

After your call ends, monitor the discharge analysis:

```bash
# Watch for transcript processing in the logs
docker compose logs -f postop-scheduler
```

### Step 3.2: Verify Call Generation

Check what follow-up calls were generated:

```bash
# Show all pending calls (auto-detects Docker/local)
./show_pending_calls.sh
```

### Step 3.3: Expected AI-Generated Calls

The LLM analysis should generate calls like:

✅ **Compression Bandage Removal** (24 hours) - Reminder to remove bandages  
✅ **Wound Care Check** (48 hours) - Verify proper wound care  
✅ **Pain Management** (Day 1) - Check pain levels and medication effectiveness  
✅ **Activity Restrictions** (Day 3) - Confirm return to work guidelines  
✅ **Compression Stockings** (Weekly) - Ensure proper use  
✅ **Follow-up Appointment** (2 weeks) - Appointment reminder  

---

## Part 4: Test Generated Follow-Up Call (10 minutes)

### Step 4.1: Create an Immediate Test Call

Create a demo call that will execute immediately:

```bash
# Create a test call (replace with your phone number)
./trigger_outbound_call.sh create +14258295443 'Sarah Johnson' 30

# Or trigger an existing call immediately using its ID
./trigger_outbound_call.sh f02667fe
```

### Step 4.2: Answer the Follow-Up Call

Within 1-2 minutes, you should receive a call:

**Expected conversation:**
1. **Agent:** *"Hello Sarah, this is Vince from PostOp AI calling about your varicose vein surgery..."*
2. **Agent:** Delivers personalized message based on the specific call type
3. **Agent:** Asks relevant questions about your recovery
4. **You:** Can test the agent's medical knowledge by asking questions

**Try asking:**
- "How should I care for my incision sites?"
- "What pain medication is safe to take?"
- "When can I return to exercise?"
- "What are signs of infection I should watch for?"

---

## Part 5: Verify Complete Workflow (5 minutes)

### Step 5.1: Check Call Execution Status

```bash
# Show all calls with their current status
./show_pending_calls.sh
```

### Step 5.2: Review LLM Analysis Results

The transcript analysis data is automatically stored during call processing. You can check the logs for analysis details:

```bash
# Check processing logs
docker compose logs postop-scheduler --tail 20
```

---

## Expected Demo Results ✅

After completing this demo, you should have:

### ✅ **Successful Discharge Call**
- Made real phone call to LiveKit system
- Agent collected complete discharge instructions
- Professional conversation flow throughout
- Proper patient information capture

### ✅ **AI Analysis and Call Generation**
- LLM analyzed transcript for medical content
- Multiple follow-up calls automatically generated
- Calls personalized based on specific instructions
- Appropriate timing for each call type

### ✅ **Follow-Up Call Execution**
- Received actual phone call from the system
- Personalized message based on discharge content
- Agent demonstrated medical knowledge during Q&A
- Professional call completion

### ✅ **End-to-End Workflow Verified**
- Discharge → Analysis → Generation → Scheduling → Execution
- All data properly stored in Redis
- System handled real phone integration
- Complete audit trail maintained


---

## Troubleshooting

### 🚨 **Can't Connect to LiveKit Phone Number**

**Check SIP configuration:**
```bash
# Verify LiveKit connection
docker compose logs postop-agent --tail 10
```

### 🚨 **Agent Doesn't Answer**

**Check agent dispatch rules in LiveKit dashboard:**
- Rule should route calls to "PostOp-AI" agent
- SIP trunk should be properly configured
- Agent should show as "registered" in LiveKit

### 🚨 **No Follow-Up Calls Generated**

**Check transcript processing:**
```bash
# Look for transcript analysis errors
docker compose logs postop-scheduler --tail 20
```

### 🚨 **Medical Knowledge Not Available**

**Re-run the medical knowledge setup:**
```bash
# Reset demo data and restore medical knowledge
./reset_demo.sh
```

---

## Next Steps

After successful discharge demo:

1. **🔗 Integrate with EMR**: Connect to hospital discharge workflows
2. **📊 Build Dashboard**: Create web interface for managing discharge sessions
3. **📞 Scale Calling**: Configure multiple concurrent call handling
4. **📈 Analytics**: Add reporting on discharge instruction compliance
5. **🎯 Customize**: Adapt for different procedure types and specialties

**Congratulations! You've demonstrated the complete PostOp AI discharge workflow! 🎉**