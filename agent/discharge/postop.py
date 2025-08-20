from dotenv import load_dotenv
import os
import redis
import json
from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime, timedelta

from livekit import agents, api
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext, get_job_context, UserStateChangedEvent
from livekit.agents.llm import ChatContext, ChatMessage, StopResponse
import asyncio
from livekit.plugins import (
    openai,
    cartesia,
    elevenlabs,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.english import EnglishModel

load_dotenv()

@dataclass
class DischargeOrder:
    id: str
    label: str
    day_offset: int
    send_at_hour: int
    discharge_order: str

# Real discharge orders from venous malformation case
DISCHARGE_ORDERS = [
    DischargeOrder("vm_discharge", "Venous Malformation Discharge Order", 0, 18, "May discharge patient home under the care of a responsible parent/legal guardian after 1.5 hours if patient meets discharge criteria: Stable vital signs, Ambulatory or at pre-procedure status, Tolerating oral intake, Patient has voided at least once, Puncture site stable without bleeding."),
    DischargeOrder("vm_symptoms", "Symptoms to Report", 0, 20, "Contact Primary Care or Specialty Care Doctor for: Temperature over 100.5, Pain not relieved by medication, Difficulty breathing, Nausea/Vomiting, Drainage or foul odor from dressing/incision, painful swelling at the incision site, excessive discoloration of the skin. In Case of an urgent concern or emergency, call 911 or come to the Egleston Emergency Room."),
    DischargeOrder("vm_compression", "Compression Bandage Instructions", 1, 9, "Leave the compression bandage on for 24 hours and then wear as much as can be tolerated for 7 days."),
    DischargeOrder("vm_shower", "Bathing Instructions", 1, 10, "May shower tomorrow, no bathing or swimming for 5 days."),
    DischargeOrder("vm_activity", "Activity Restrictions", 1, 11, "Routine, Normal, Elevate the extremity whenever possible. Minimal weight-bearing for 48 hours. Walking only for 7 days. May resume normal activities after 7 days."),
    DischargeOrder("vm_school", "Return to School/Daycare", 7, 14, "May Return to School/Daycare: 6/23/2025"),
    DischargeOrder("vm_medication", "Medication Instructions", 0, 21, "Starting 8 hours from last Toradol dose (unless on anticoagulation therapy), take ibuprofen per the instructions on the medication bottle for 7 days, regardless of whether or not your child is having pain. Pain is usually more severe 5-15 days after the procedure. In approximately 14 days, you are likely to feel firm nodules in the area of the venous malformation. These represent scar tissue."),
    DischargeOrder("vm_bleomycin", "Bleomycin Precautions", 0, 22, "Please do not remove EKG leads and any other adhesive for 48 hours. Also, bleomycin can cause a transient rash. If your child develops a rash/skin discoloration, please notify the Vascular Anomalies Clinic (404 785-8926). The rash/skin discoloration can take weeks to months to resolve."),
]

# Doctor-selected orders for this specific patient (based on checked items in discharge orders)
SELECTED_DISCHARGE_ORDERS = [
    "vm_discharge",      # ✓ Venous Malformation (lower extremity) Discharge Order
    "vm_symptoms",       # ✓ Discharge Instruction (symptoms to report)
    "vm_compression",    # ✓ Discharge Instruction (compression bandage)
    "vm_shower",         # ✓ May Shower
    "vm_activity",       # ✓ Discharge Activity Instructions
    "vm_school",         # ✓ Discharge - Return To School Or Daycare
    "vm_medication",     # ✓ Discharge Instruction (medication)
    "vm_bleomycin",      # ✓ Discharge Instruction (bleomycin precautions)
]

class RedisMemory:
    def __init__(self):
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
    
    def store_patient_data(self, phone_number: str, key: str, value: Any):
        """Store patient data in Redis"""
        patient_key = f"patient:{phone_number}:{key}"
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        elif isinstance(value, bool):
            value = str(value)  # Convert boolean to string for Redis
        self.redis_client.set(patient_key, value)
    
    def get_patient_data(self, phone_number: str, key: str):
        """Retrieve patient data from Redis"""
        patient_key = f"patient:{phone_number}:{key}"
        value = self.redis_client.get(patient_key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Handle boolean conversion
                if value == "True":
                    return True
                elif value == "False":
                    return False
                return value
        return None
    
    def get_all_patient_data(self, phone_number: str):
        """Get all data for a patient"""
        pattern = f"patient:{phone_number}:*"
        keys = self.redis_client.keys(pattern)
        data = {}
        for key in keys:
            field = key.split(':')[-1]
            data[field] = self.get_patient_data(phone_number, field)
        return data
    
    def append_transcript_entry(self, phone_number: str, transcript_entry: dict):
        """Append a single transcript entry to the stored transcript"""
        existing_transcript = self.get_patient_data(phone_number, "nurse_transcript") or []
        existing_transcript.append(transcript_entry)
        self.store_patient_data(phone_number, "nurse_transcript", existing_transcript)
    
    def get_patient_summary(self, phone_number: str):
        """Get a summary of all patient data for review"""
        data = self.get_all_patient_data(phone_number)
        summary = {
            "basic_info": {
                "nurse_id": data.get("nurse_id"),
                "record_number": data.get("record_number"),
                "consent": data.get("consent"),
                "language": data.get("language"),
                "phone": phone_number
            },
            "discharge_tracking": {
                "completed_orders": data.get("completed_orders", []),
                "additional_instructions": data.get("additional_instructions", []),
                "transcript_entries": len(data.get("nurse_transcript", []))
            },
            "timeline": {
                "setup_date": data.get("setup_date"),
                "consent_date": data.get("consent_date"),
                "listening_started": data.get("listening_started")
            }
        }
        return summary

async def hangup_call():
    """End the phone call by deleting the room"""
    ctx = get_job_context()
    if ctx is None:
        return
    
    try:
        await ctx.api.room.delete_room(
            api.DeleteRoomRequest(
                room=ctx.room.name,
            )
        )
    except Exception:
        # Room might already be deleted, ignore the error
        pass

class PostOpAssistant(Agent):
    def __init__(self):
        self.memory = RedisMemory()
        self.current_patient_phone = None
        self.current_language = "English"
        self.in_passive_mode = False  # Use session audio control instead of custom listening_mode
        self.transcript_buffer = []
        self.translation_enabled = False
        self.last_speaker = None  # Track who spoke last for translation context
        self.demo_state = "setup"  # "setup", "listening", "review", "complete"
        self._agent_session = None  # Store session reference for state management
        self.setup_checklist = {
            "nurse_id": False,
            "record_number": False,
            "consent": False,
            "phone_number": False,
            "language": False
        }
        
        super().__init__(instructions="""
You are Kenta, a post-operative care assistant.

COMMUNICATION STYLE:
- Be brief, warm, and conversational
- Only ask for ONE piece of information at a time
- Keep responses to 1-2 sentences maximum
- Use natural, human-like language
- Don't explain the whole process upfront

SETUP PHASE:
Start by saying: "Hi! I'm Kenta, your post-op care assistant. To get started, could you please give me your nurse ID number?"

Then collect ONE item at a time in this order:
1. Nurse ID (use store_nurse_id)
2. Patient record number (use store_patient_record) 
3. Patient phone number (use store_patient_phone)
4. Patient language preference (use set_patient_language)
5. Patient consent (use store_patient_consent)

After each item, just say "Got it, thanks!" and ask for the next item.

PASSIVE LISTENING PHASE:
When setup is complete, say: "Perfect! I'm ready to listen in on your discharge instructions. Should I start passive listening mode now?"

Then use start_passive_listening and stay completely silent unless directly addressed by name.

REVIEW PHASE:
Provide a concise summary focusing on what was covered vs. what might have been missed.

CRITICAL: Keep every response under 20 words except during final review.
""")
        
    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Handle user speech completion - control response based in passive mode"""
        print(f"[DEBUG] on_user_turn_completed called. in_passive_mode: {self.in_passive_mode}")
        print(f"[DEBUG] transcript: '{new_message.text_content}'")
        
        if self.in_passive_mode:
            # During passive listening, process the speech but don't generate automatic responses
            transcript_text = new_message.text_content or ""
            print(f"[DEBUG] Processing passive transcript: '{transcript_text}'")

            # Process speech through our custom handler
            await self._process_speech_automatically_from_turn(transcript_text)

            # Prevent automatic response by raising StopResponse
            raise StopResponse()

        # Normal mode - let the agent respond automatically
        # (default behavior continues)

    async def _process_speech_automatically_from_turn(self, transcript_text: str):
        """Process speech from turn completion during passive listening"""
        print(f"[DEBUG] _process_speech_automatically_from_turn called with: '{transcript_text}'")
        print(f"[DEBUG] in_passive_mode: {self.in_passive_mode}")
        
        if not self.in_passive_mode:
            print("[DEBUG] Not in passive mode, returning")
            return

        # Store the transcript silently
        self.transcript_buffer.append({
            "text": transcript_text,
            "timestamp": datetime.now().isoformat(),
            "speaker": "user"
        })
        print(f"[DEBUG] Stored transcript. Buffer size: {len(self.transcript_buffer)}")

        # Check for completion keywords that should trigger review
        text_lower = transcript_text.lower()
        completion_phrases = [
            "that's all", "we're done", "finished", "complete", "wrap up",
            "summary", "summarize", "done with", "that covers everything",
            "kenta, summarize", "kenta summary", "postop summary", "kenta. summarize"
        ]

        print(f"[DEBUG] Checking for completion phrases in: '{text_lower}'")
        for phrase in completion_phrases:
            if phrase in text_lower:
                print(f"[DEBUG] Found completion phrase: '{phrase}' - triggering review")
                asyncio.create_task(self._trigger_review_from_turn_completion(transcript_text))
                return

        # Check if AI is being directly addressed by name
        if any(name in text_lower for name in ["kenta", "postop", "post-op", "ai"]):
            print(f"[DEBUG] Detected direct addressing in: '{text_lower}'")
            # Note: Direct addressing will be handled by generating a response
            # But we still want to stay in passive mode
            pass
        else:
            # Continue silent processing - auto-detect discharge orders
            print(f"[DEBUG] Auto-detecting orders in: '{transcript_text}'")
            await self._auto_detect_orders(transcript_text)

    @function_tool()
    async def store_nurse_id(self, ctx: RunContext, nurse_id: str):
        """Store the nurse's ID number"""
        if self.current_patient_phone:
            self.memory.store_patient_data(self.current_patient_phone, "nurse_id", nurse_id)
        self.setup_checklist["nurse_id"] = True
        await self._check_demo_progress(ctx)
        return f"Nurse ID {nurse_id} recorded"

    @function_tool()
    async def store_patient_record(self, ctx: RunContext, record_number: str):
        """Store the patient's record number"""
        if self.current_patient_phone:
            self.memory.store_patient_data(self.current_patient_phone, "record_number", record_number)
        self.setup_checklist["record_number"] = True
        await self._check_demo_progress(ctx)
        return f"Patient record {record_number} recorded"

    @function_tool()
    async def store_patient_consent(self, ctx: RunContext, has_consent: bool):
        """Record patient consent for post-op care assistance"""
        if self.current_patient_phone:
            self.memory.store_patient_data(self.current_patient_phone, "consent", has_consent)
            self.memory.store_patient_data(self.current_patient_phone, "consent_date", datetime.now().isoformat())
        self.setup_checklist["consent"] = True
        await self._check_demo_progress(ctx)
        return f"Patient consent recorded: {has_consent}"

    @function_tool()
    async def set_patient_language(self, ctx: RunContext, language: str):
        """Set the patient's preferred language"""
        self.current_language = language
        if self.current_patient_phone:
            self.memory.store_patient_data(self.current_patient_phone, "language", language)
        
        # If language is not English, note it for summary translation
        if language.lower() != "english":
            await ctx.session.generate_reply(
                instructions=f"The patient's preferred language is {language}. Tell the nurse: 'I've noted that the patient prefers {language}. When I provide the summary at the end, I can translate it into {language} for the patient. I won't interrupt during your conversation - I'll provide the translation only when you ask for the summary.'"
            )
        
        self.setup_checklist["language"] = True
        await self._check_demo_progress(ctx)
        return f"Patient language set to {language}"

    @function_tool()
    async def enable_translation_mode(self, ctx: RunContext, enable_translation: bool):
        """Enable or disable real-time translation during discharge instructions"""
        if self.current_patient_phone:
            self.memory.store_patient_data(self.current_patient_phone, "translation_enabled", enable_translation)
        
        if enable_translation:
            return f"Translation mode enabled. I will translate instructions into {self.current_language} and patient questions into English."
        else:
            return "Translation mode disabled. Proceeding in English only."

    @function_tool()
    async def check_off_discharge_order(self, ctx: RunContext, order_id: str):
        """Mark a discharge order as covered by the nurse"""
        if self.current_patient_phone:
            completed_orders = self.memory.get_patient_data(self.current_patient_phone, "completed_orders") or []
            if order_id not in completed_orders:
                completed_orders.append(order_id)
                self.memory.store_patient_data(self.current_patient_phone, "completed_orders", completed_orders)
        
        # Find the order for confirmation
        order = next((o for o in DISCHARGE_ORDERS if o.id == order_id), None)
        if order:
            return f"Checked off: {order.label} - {order.discharge_order}"
        return f"Discharge order {order_id} marked as completed"

    @function_tool()
    async def get_selected_orders(self, ctx: RunContext):
        """Get the list of discharge orders selected by the doctor for this patient"""
        selected_orders = []
        for order_id in SELECTED_DISCHARGE_ORDERS:
            order = next((o for o in DISCHARGE_ORDERS if o.id == order_id), None)
            if order:
                selected_orders.append({
                    "id": order.id,
                    "label": order.label,
                    "instruction": order.discharge_order,
                    "day_offset": order.day_offset,
                    "send_at_hour": order.send_at_hour
                })
        return f"Doctor selected {len(selected_orders)} discharge orders for this patient: {', '.join([o['label'] for o in selected_orders])}"

    @function_tool()
    async def check_coverage_status(self, ctx: RunContext):
        """Check which doctor-selected orders have been covered by the nurse"""
        if not self.current_patient_phone:
            return "No patient phone number set"
        
        completed_orders = self.memory.get_patient_data(self.current_patient_phone, "completed_orders") or []
        
        covered = []
        missing = []
        
        for order_id in SELECTED_DISCHARGE_ORDERS:
            order = next((o for o in DISCHARGE_ORDERS if o.id == order_id), None)
            if order:
                if order_id in completed_orders:
                    covered.append(order.label)
                else:
                    missing.append(order.label)
        
        status = f"Coverage Status:\nCovered ({len(covered)}): {', '.join(covered)}\nMissing ({len(missing)}): {', '.join(missing)}"
        return status

    @function_tool()
    async def add_additional_instruction(self, ctx: RunContext, instruction: str):
        """Record additional instructions given by the nurse"""
        if self.current_patient_phone:
            additional_instructions = self.memory.get_patient_data(self.current_patient_phone, "additional_instructions") or []
            additional_instructions.append({
                "instruction": instruction,
                "timestamp": datetime.now().isoformat()
            })
            self.memory.store_patient_data(self.current_patient_phone, "additional_instructions", additional_instructions)
        return f"Additional instruction recorded: {instruction}"

    @function_tool()
    async def store_patient_phone(self, ctx: RunContext, phone_number: str):
        """Store the patient's phone number for future contact"""
        self.current_patient_phone = phone_number
        self.memory.store_patient_data(phone_number, "setup_date", datetime.now().isoformat())
        self.setup_checklist["phone_number"] = True
        await self._check_demo_progress(ctx)
        return f"Patient phone number {phone_number} recorded for future reminders"

    @function_tool()
    async def start_passive_listening(self, ctx: RunContext):
        """Switch to passive listening mode to hear discharge instructions"""
        # Check if setup is complete before starting listening
        incomplete_items = [key for key, completed in self.setup_checklist.items() if not completed]
        if incomplete_items:
            remaining = ", ".join(incomplete_items).replace("_", " ")
            await ctx.session.generate_reply(
                instructions=f"Cannot start listening yet. We still need to collect: {remaining}. Please complete the setup first."
            )
            return f"Setup incomplete. Still need: {remaining}"
        
        # Use LiveKit session management instead of custom state
        self.in_passive_mode = True
        self.demo_state = "listening"
        self.transcript_buffer = []
        print(f"[DEBUG] Entered passive listening mode. in_passive_mode: {self.in_passive_mode}")
        
        # Switch to manual turn detection for passive listening control
        # Note: This requires the session to handle turn detection changes
        # For now, we'll use audio control and rely on our custom processing
        
        # Check if translation is enabled
        self.translation_enabled = self.memory.get_patient_data(self.current_patient_phone, "translation_enabled") or False
        
        # Store that we're now in listening mode
        if self.current_patient_phone:
            self.memory.store_patient_data(self.current_patient_phone, "listening_started", datetime.now().isoformat())
        
        # Brief confirmation of passive listening mode
        instructions = "Say exactly: 'Okay, I'm now listening quietly. I'll track everything and stay silent unless you call my name. Go ahead!'"
        await ctx.session.generate_reply(instructions=instructions)
        return "Switched to passive listening mode with automatic transcript capture and order detection"

    @function_tool()
    async def capture_transcript(self, ctx: RunContext, transcript_text: str):
        """Capture and store transcript text during passive listening"""
        if self.in_passive_mode:
            self.transcript_buffer.append({
                "text": transcript_text,
                "timestamp": datetime.now().isoformat()
            })
            
            # Auto-detect discharge orders mentioned
            await self._auto_detect_orders(transcript_text)
            
        return f"Captured: {transcript_text[:50]}..."

    async def _process_speech_automatically(self, ctx: RunContext, transcript_text: str, speaker_identity: str = "unknown"):
        """Automatically process speech during passive listening mode - SILENT UNLESS DIRECTLY ADDRESSED"""
        if not self.in_passive_mode:
            return
        
        # Store the transcript silently
        self.transcript_buffer.append({
            "text": transcript_text,
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker_identity
        })
        
        # Check for completion keywords that should trigger review
        text_lower = transcript_text.lower()
        completion_phrases = [
            "that's all", "we're done", "finished", "complete", "wrap up", 
            "summary", "summarize", "done with", "that covers everything",
            "kenta, summarize", "kenta summary", "postop summary"
        ]
        
        if any(phrase in text_lower for phrase in completion_phrases):
            # Trigger automatic review
            await self._auto_trigger_review_from_keywords(ctx, transcript_text)
            return
        
        # Check if AI is being directly addressed by name
        if any(name in text_lower for name in ["kenta", "postop", "post-op", "ai"]):
            # AI is being directly addressed - respond appropriately
            await ctx.session.generate_reply(
                instructions=f"Someone just addressed you directly during passive listening with: '{transcript_text}'. Respond briefly and helpfully, then remind them you're in listening mode. Keep it concise."
            )
        else:
            # Continue silent processing
            # Auto-detect discharge orders silently
            await self._auto_detect_orders(transcript_text)
        
        # Store speaker for context
        self.last_speaker = speaker_identity

    async def _handle_translation_during_summary(self, ctx: RunContext, text_to_translate: str):
        """Handle translation ONLY during summary phase when specifically requested"""
        if self.current_language.lower() != "english":
            await ctx.session.generate_reply(
                instructions=f"Now translate this summary into {self.current_language} for the patient. Keep it natural and clear. Say 'In {self.current_language}:' and then provide the translation of: '{text_to_translate}'"
            )
        else:
            # Patient prefers English, no translation needed
            return

    @function_tool()
    async def provide_summary_with_translation(self, ctx: RunContext):
        """Provide summary of discharge instructions, with translation if needed"""
        # First provide the summary in English
        await self.trigger_review(ctx)
        
        # Then provide translation if patient's language is not English
        if self.current_language.lower() != "english":
            # Get key summary points for translation
            completed_orders = self.memory.get_patient_data(self.current_patient_phone, "completed_orders") or []
            covered_order_names = []
            for order in DISCHARGE_ORDERS:
                if order.id in completed_orders:
                    covered_order_names.append(order.label)
            
            summary_for_translation = f"We reviewed {len(covered_order_names)} discharge instructions: {', '.join(covered_order_names)}. Please follow all instructions carefully and call if you have questions."
            
            await self._handle_translation_during_summary(ctx, summary_for_translation)
        
        return "Summary completed with translation if needed"

    @function_tool()
    async def respond_when_addressed(self, ctx: RunContext, message: str):
        """Use this when someone directly addresses PostOp AI during passive listening"""
        if self.in_passive_mode:
            await ctx.session.generate_reply(
                instructions=f"Someone addressed you directly during passive listening with: '{message}'. Respond briefly and helpfully, then remind them you're continuing to listen quietly to track the discharge orders."
            )
            return "Responded to direct address during passive listening"
        else:
            return "Not in passive listening mode"

    async def _check_demo_progress(self, ctx: RunContext):
        """Check demo setup progress and guide the nurse through next steps"""
        if self.demo_state != "setup":
            return
        
        completed_items = [key for key, completed in self.setup_checklist.items() if completed]
        remaining_items = [key for key, completed in self.setup_checklist.items() if not completed]
        
        if len(remaining_items) == 0:
            # All setup complete, ready for listening phase
            await ctx.session.generate_reply(
                instructions="Say exactly: 'Perfect! I'm ready to listen in on your discharge instructions. Should I start passive listening mode now?'"
            )
        elif len(remaining_items) > 0:
            # Guide to next item step by step
            next_prompts = {
                "record_number": "Great! Now, what's the patient's record number?",
                "phone_number": "Got it! What's the patient's phone number?", 
                "language": "Thanks! What language does the patient prefer?",
                "consent": "Perfect! Does the patient consent to post-op care assistance?"
            }
            next_item = remaining_items[0]
            prompt = next_prompts.get(next_item, "What's the next piece of information?")
            await ctx.session.generate_reply(
                instructions=f"Say exactly: '{prompt}'"
            )

    @function_tool()
    async def get_demo_status(self, ctx: RunContext):
        """Get current demo progress status for troubleshooting"""
        status = {
            "demo_state": self.demo_state,
            "setup_checklist": self.setup_checklist,
            "translation_enabled": self.translation_enabled,
            "current_language": self.current_language,
            "in_passive_mode": self.in_passive_mode,
            "transcript_entries": len(self.transcript_buffer)
        }
        return f"Demo Status: {json.dumps(status, indent=2)}"

    @function_tool()
    async def advance_to_listening_phase(self, ctx: RunContext):
        """Manually advance demo to listening phase if setup is complete"""
        incomplete_items = [key for key, completed in self.setup_checklist.items() if not completed]
        
        if incomplete_items:
            remaining = ", ".join(incomplete_items).replace("_", " ")
            return f"Cannot advance to listening phase. Still need: {remaining}"
        
        self.demo_state = "listening"
        await ctx.session.generate_reply(
            instructions="Setup phase complete! Tell the nurse: 'All setup information collected successfully. I'm ready to switch to passive listening mode. When you're ready to begin reviewing the discharge orders with the patient, just ask me to start listening.'"
        )
        return "Advanced to listening phase"

    @function_tool()
    async def trigger_review(self, ctx: RunContext):
        """Generate comprehensive review of heard discharge instructions with translation showcase"""
        print(f"[DEBUG] trigger_review called. Transcript buffer size: {len(self.transcript_buffer)}")
        print(f"[DEBUG] Transcript entries: {[entry['text'][:50] for entry in self.transcript_buffer]}")
        
        self.in_passive_mode = False
        self.demo_state = "review"
        
        # Disable audio input during review
        if self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
        
        # Store full transcript
        if self.current_patient_phone and self.transcript_buffer:
            self.memory.store_patient_data(self.current_patient_phone, "nurse_transcript", self.transcript_buffer)
        
        # Get comprehensive patient summary
        patient_summary = self.memory.get_patient_summary(self.current_patient_phone)
        completed_orders = patient_summary["discharge_tracking"]["completed_orders"]
        additional_instructions = patient_summary["discharge_tracking"]["additional_instructions"]
        auto_detections = self.memory.get_patient_data(self.current_patient_phone, "auto_detections") or []
        
        # Find which doctor-selected orders were NOT covered
        missed_orders = [order_id for order_id in SELECTED_DISCHARGE_ORDERS if order_id not in completed_orders]
        covered_selected = [order_id for order_id in SELECTED_DISCHARGE_ORDERS if order_id in completed_orders]
        
        # Get order names for better readability
        covered_order_names = []
        missed_order_names = []
        for order in DISCHARGE_ORDERS:
            if order.id in covered_selected:
                covered_order_names.append(order.label)
            elif order.id in missed_orders:
                missed_order_names.append(order.label)
        
        # Create detailed review instructions showcasing all capabilities
        review_instructions = f"""
        Provide a comprehensive and caring review of the discharge instructions. This is a DEMO SHOWCASE - highlight all the AI capabilities that were demonstrated.

        DEMO SHOWCASE SUMMARY:
        - Patient phone: {self.current_patient_phone}
        - Preferred language: {self.current_language}
        - Translation enabled: {self.translation_enabled}
        - Nurse ID: {patient_summary["basic_info"]["nurse_id"]}
        - Record number: {patient_summary["basic_info"]["record_number"]}
        - Transcript entries captured: {len(self.transcript_buffer)}
        - Automatic detections made: {len(auto_detections)}

        DISCHARGE ORDERS TRACKING:
        - Doctor-selected orders covered: {len(covered_selected)} out of {len(SELECTED_DISCHARGE_ORDERS)}
        - Orders successfully covered: {', '.join(covered_order_names) if covered_order_names else 'None'}
        - Orders potentially missed: {', '.join(missed_order_names) if missed_order_names else 'None'}
        - Additional instructions given: {len(additional_instructions)}

        DEMO STRUCTURE YOUR RESPONSE:
        1. Thank the nurse and patient for demonstrating the PostOp AI system
        2. Showcase what information was automatically collected during setup
        3. Highlight the passive listening and automatic order detection capabilities
        4. Demonstrate the discharge order tracking by listing what was covered
        5. Mention any gaps for completeness (showing the validation feature)
        6. If translation was enabled, provide a sample translation of a key instruction in {self.current_language}
        7. Explain the future reminder system that would now activate
        8. Provide clear next steps for the patient

        Be warm, professional, and highlight how this technology improves patient care. This is a STAKEHOLDER DEMO - make sure they see the value proposition clearly.
        """
        
        await ctx.session.generate_reply(instructions=review_instructions)
        
        # Mark demo as complete
        self.demo_state = "complete"
        
        return "Comprehensive demo review completed with translation showcase"

    @function_tool()
    async def reset_demo(self, ctx: RunContext):
        """Reset the demo for a new stakeholder presentation"""
        # Reset all demo state
        self.demo_state = "setup"
        self.in_passive_mode = False
        self.setup_checklist = {
            "nurse_id": False,
            "record_number": False,
            "consent": False,
            "phone_number": False,
            "language": False
        }
        self.transcript_buffer = []
        self.translation_enabled = False
        self.current_language = "English"
        self.current_patient_phone = None
        self.last_speaker = None
        
        await ctx.session.generate_reply(
            instructions="Demo has been reset! Tell the nurse: 'Demo reset complete. I'm ready for a new demonstration. Please begin by providing the nurse ID number to start the setup process.'"
        )
        return "Demo reset successful. Ready for new presentation."

    @function_tool()
    async def get_patient_summary(self, ctx: RunContext):
        """Get a summary of all collected patient data for reference"""
        if not self.current_patient_phone:
            return "No patient phone number set"
        
        summary = self.memory.get_patient_summary(self.current_patient_phone)
        return json.dumps(summary, indent=2)

    async def _auto_detect_orders(self, transcript_text: str):
        """Automatically detect and check off discharge orders from transcript using medical terminology"""
        text_lower = transcript_text.lower()
        
        # Enhanced medical terminology matching for venous malformation orders
        order_detection_map = {
            "vm_discharge": ["discharge", "stable vital", "ambulatory", "oral intake", "voided", "puncture site", "bleeding"],
            "vm_symptoms": ["temperature", "fever", "pain", "medication", "breathing", "nausea", "vomiting", "drainage", "odor", "swelling", "discoloration", "emergency", "911"],
            "vm_compression": ["compression", "bandage", "24 hours", "7 days", "tolerated"],
            "vm_shower": ["shower", "bathing", "swimming", "5 days"],
            "vm_activity": ["activity", "elevate", "extremity", "weight-bearing", "48 hours", "walking", "7 days", "normal activities"],
            "vm_school": ["school", "daycare", "return"],
            "vm_medication": ["ibuprofen", "toradol", "anticoagulation", "pain", "medication", "bottle", "nodules", "scar tissue"],
            "vm_bleomycin": ["ekg", "leads", "adhesive", "bleomycin", "rash", "skin", "discoloration", "vascular anomalies", "clinic"]
        }
        
        # Check each order for keyword matches
        for order_id, keywords in order_detection_map.items():
            # Require at least 2 keywords to match to reduce false positives
            matches = sum(1 for keyword in keywords if keyword in text_lower)
            if matches >= 2:
                # Auto-check off the order
                completed_orders = self.memory.get_patient_data(self.current_patient_phone, "completed_orders") or []
                if order_id not in completed_orders:
                    completed_orders.append(order_id)
                    self.memory.store_patient_data(self.current_patient_phone, "completed_orders", completed_orders)
                    
                    # Find the order for logging
                    order = next((o for o in DISCHARGE_ORDERS if o.id == order_id), None)
                    if order:
                        # Log the automatic detection
                        detection_log = self.memory.get_patient_data(self.current_patient_phone, "auto_detections") or []
                        detection_log.append({
                            "order_id": order_id,
                            "order_label": order.label,
                            "detected_keywords": [kw for kw in keywords if kw in text_lower],
                            "transcript_snippet": transcript_text[:100],
                            "timestamp": datetime.now().isoformat()
                        })
                        self.memory.store_patient_data(self.current_patient_phone, "auto_detections", detection_log)

    async def _trigger_review_from_turn_completion(self, trigger_text: str):
        """Trigger review from turn completion when keywords detected"""
        print(f"[DEBUG] _trigger_review_from_turn_completion called with: '{trigger_text}'")
        
        if not self.in_passive_mode:
            print("[DEBUG] Not in passive mode, returning from trigger_review")
            return
            
        # Exit passive mode
        self.in_passive_mode = False
        print("[DEBUG] Exited passive mode, about to generate review")
        
        if self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
            print("[DEBUG] Disabled audio input")
            
            # Generate completion acknowledgment and trigger review  
            await self._agent_session.generate_reply(
                instructions=f"Someone said '{trigger_text}' which means they want a summary. Say 'Got it! Let me provide a summary of what I heard.' then call the trigger_review function tool."
            )
            print("[DEBUG] Generated acknowledgment reply")
        else:
            print("[DEBUG] No _agent_session available")
    
    async def _auto_trigger_review_from_silence(self):
        """Auto-trigger review when user has been silent during passive listening"""
        if not self.in_passive_mode:
            return
            
        # Exit passive mode and trigger review
        self.in_passive_mode = False
        if self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
            
        # Generate a gentle prompt to offer summary
        if self._agent_session:
            await self._agent_session.generate_reply(
                instructions="The conversation has been quiet for a while during passive listening. Gently offer to provide a summary of what was covered. Say something like: 'I noticed it's been quiet for a bit. Would you like me to provide a summary of the discharge orders we've covered so far?'"
            )
    
    async def _auto_trigger_review_from_keywords(self, ctx: RunContext, trigger_text: str):
        """Auto-trigger review when completion keywords are detected"""
        if not self.in_passive_mode:
            return
            
        # Exit passive mode
        self.in_passive_mode = False
        if self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
            
        # Acknowledge the trigger and provide review
        await ctx.session.generate_reply(
            instructions=f"Someone just indicated completion with: '{trigger_text}'. Acknowledge this and automatically proceed to provide the comprehensive discharge instruction review and summary."
        )
        
        # Trigger the review automatically
        await self.trigger_review(ctx)
    
    @function_tool()
    async def exit_passive_listening(self, ctx: RunContext):
        """Manually exit passive listening mode and provide summary"""
        print(f"[DEBUG] exit_passive_listening called. in_passive_mode: {self.in_passive_mode}")
        print(f"[DEBUG] Current transcript buffer size: {len(self.transcript_buffer)}")
        
        if not self.in_passive_mode:
            return "Not currently in passive listening mode"
            
        self.in_passive_mode = False
        if self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
            
        # If no transcripts captured, provide a fallback message
        if len(self.transcript_buffer) == 0:
            await ctx.session.generate_reply(
                instructions="The transcript buffer is empty. Say: 'I'm sorry, I didn't capture any discharge instructions during passive listening. Could you please repeat the key points you covered, or would you like me to ask specific questions about the discharge orders?'"
            )
            return "No transcripts captured during passive listening"
        else:
            await self.trigger_review(ctx)
            return "Exited passive listening mode and provided summary"
    
    @function_tool()
    async def end_call(self, ctx: RunContext):
        """Called when the discharge instruction session is complete"""
        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()
        
        await hangup_call()
        return "Discharge instruction session completed"

async def entrypoint(ctx: agents.JobContext):
    agent_instance = PostOpAssistant()
    
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM(model="gpt-4.1"),
        tts=elevenlabs.TTS(
            voice_id=os.getenv("POSTOP_VOICE_ID", "tnSpp4vdxKPjI9w0GnoV"),
            model="eleven_turbo_v2_5"
        ),
        vad=silero.VAD.load(),
        turn_detection="vad",  # Start with VAD, switch to manual during passive listening
        user_away_timeout=30.0,  # Detect silence after 30 seconds
    )
    
    # Store session reference in agent for state management
    agent_instance._agent_session = session

    # Add session event handlers before starting
    @session.on("user_state_changed")
    def on_user_state_changed(ev: UserStateChangedEvent):
        if agent_instance.in_passive_mode and ev.new_state == "away":
            # User has been silent for 30 seconds during passive listening
            # Trigger automatic review
            asyncio.create_task(agent_instance._auto_trigger_review_from_silence())
    
    await session.start(
        room=ctx.room,
        agent=agent_instance,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(), 
        ),
    )

    await ctx.connect()

    await session.generate_reply(
        instructions="Say exactly: 'Hi! I'm Kenta, your post-op care assistant. To get started, could you please give me your nurse ID number?'"
    )

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="telephony-agent"
    ))