"""
Discharge Agents for PostOp AI System

This module contains the complete discharge instruction collection workflow for PostOp AI,
handling patient setup, instruction collection, translation, and verification. The system
is designed to work seamlessly with healthcare providers during patient discharge.

AGENTS AND WORKFLOW:

1. ConsentCollector Agent:
   - Collects recording consent before proceeding
   - Handles consent denial by ending call gracefully
   - Routes to DischargeAgent upon consent

2. DischargeAgent (Main Unified Agent):
   - Comprehensive agent that handles the entire discharge workflow
   - Manages patient setup, instruction collection, translation, and verification
   - Supports both passive listening and active translation modes
   - Persists session data to local files
   - Schedules intelligent follow-up calls via PostOp AI scheduling system

COMPLETE TOOL REFERENCE:

Patient Setup Tools:
- store_patient_name(): Captures and stores patient's full name
- store_patient_language(): Records preferred language for care instructions
- store_patient_phone(): Validates and stores phone number for follow-up calls
- request_translation_agent(): Determines if real-time translation is needed

Instruction Collection Tools:
- collect_instruction(): Captures discharge instructions being read aloud
  * Supports categorization (medication, activity, followup, warning, etc.)
  * Silent collection in passive mode for natural workflow
- respond_when_addressed(): Provides intelligent responses when directly addressed
- clarify_instruction(): Requests clarification for unclear instructions
- start_passive_listening(): Enters silent collection mode

Translation Tools:
- translate_instruction(): Real-time English to patient language translation
  * Maintains medical accuracy with patient-friendly language
  * Stores both original and translated versions
  * Supports active translation workflow

Workflow Management Tools:
- complete_instruction_collection(): Transitions from collection to verification
- start_verification(): Initiates instruction readback process

Verification Tools:
- read_back_instruction(): Reads back specific instructions for accuracy check
- correct_instruction(): Updates instructions that were recorded incorrectly
- add_missing_instruction(): Adds instructions missed during initial collection
- confirm_verification_complete(): Finalizes verified instructions and triggers follow-up

WORKFLOW MODES:

1. Setup Mode:
   - Collects patient name, language preference, and phone number
   - Routes to appropriate workflow based on language needs

2. Passive Listening Mode (English speakers):
   - Silently collects instructions as nurse reads them
   - Responds only when directly addressed
   - Maintains natural discharge conversation flow

3. Active Translation Mode (Non-English speakers):
   - Provides real-time translation of instructions
   - Maintains parallel English and translated instruction sets
   - Enables bilingual discharge process

4. Verification Mode:
   - Reads back all collected instructions for accuracy
   - Allows corrections and additions
   - Confirms completeness before scheduling follow-up calls

INTEGRATIONS:

- LiveKit: Voice processing with Deepgram STT, OpenAI LLM, and configurable TTS
- File Storage: Session persistence and instruction storage
- Scheduling System: Intelligent follow-up call generation via LLM analysis
- Medical RAG: Integration with medical knowledge base for enhanced responses

SUPPORTED LANGUAGES:
- English (passive listening mode)
- Spanish, Portuguese, French, German, Italian, Dutch, Russian, Arabic, Chinese, Japanese
- Real-time translation with medical terminology accuracy

TECHNICAL FEATURES:

- Session Management: File-based persistence across agent handoffs
- Error Handling: Graceful degradation and retry logic
- Console/Production Modes: Flexible deployment options
- TTS Provider Selection: OpenAI (console) / Hume (production)
- Metadata Tracking: Comprehensive logging and session analytics
- Call Routing: Unified entrypoint for inbound/outbound call handling

FOLLOW-UP CALL SCHEDULING:

The system automatically schedules intelligent follow-up calls based on:
- Collected discharge instructions
- Patient language preferences
- Medical procedure type and complexity
- Timing optimization for patient compliance
- Integration with PostOp AI's comprehensive call scheduling system

This creates a complete post-operative care workflow from initial discharge through
ongoing follow-up support, ensuring patients receive personalized care reminders
and have opportunities to ask questions about their recovery.
"""
import logging
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from livekit.agents import Agent, AgentSession, RunContext, JobContext, WorkerOptions, cli, ConversationItemAddedEvent, RoomInputOptions
from livekit.agents.llm import ChatContext, ChatMessage, function_tool
from livekit.plugins import deepgram, openai, silero
from livekit.plugins import noise_cancellation

from .config import LIVEKIT_AGENT_NAME, GMAIL_USERNAME, GMAIL_APP_PASSWORD, SUMMARY_EMAIL_RECIPIENT
from shared import send_instruction_summary_email, get_database, close_database

logger = logging.getLogger("postop-agent")

HEALTHCARE_PROVIDER_NAME = os.getenv("HEALTHCARE_PROVIDER_NAME", "Dr. Shah")


def is_console_mode():
    """Check if running in console mode"""
    return len(sys.argv) > 1 and sys.argv[1] == "console"

@dataclass
class SessionData:
    """Session data passed between agents"""
    patient_name: str | None = None
    patient_language: str | None = None

    # not sure this is really needed for the demo
    workflow_mode: str = "setup"  # setup -> passive_listening/active_translation -> verification

    is_passive_mode: bool = False
    room_people: list = None

    # Tool-captured discharge instructions
    collected_instructions: list = None

    # OpenAI format conversation logging
    openai_conversation: list = None
    session_start_time: str | None = None

    def __post_init__(self):
        if self.collected_instructions is None:
            self.collected_instructions = []
        if self.openai_conversation is None:
            self.openai_conversation = []
        if self.session_start_time is None:
            from datetime import datetime
            self.session_start_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    


class DischargeAgent(Agent):
    """Initial agent that handles patient setup and routing to appropriate workflow"""
    
    def __init__(self, chat_ctx=None):
        """
        Initialize Discharge Agent
        
        Args:
            chat_ctx: Chat context from previous agent (for conversation continuity)
        """
        # Load initial discharge agent instructions from YAML (currently simplified inline)
        instructions = """
You are Maya, an AI discharge assistant designed to capture medical discharge instructions during doctor-patient conversations. You have access to these functions:
- extract_patient_info(patient_name, patient_language): Extracts patient name and language when mentioned
- start_passive_listening(): Enters passive listening mode
- collect_instruction(instruction_text, instruction_type): Captures a discharge instruction
- provide_instruction_summary(): Exits passive mode and provides summary
- send_instruction_summary_email(): Sends the instruction summary via email

## CORE WORKFLOW

**Initial Interaction:**
1. Briefly introduce yourself as Maya and ask who is present in the room
2. When the doctor responds with patient information, call extract_patient_info() to capture:
   - Patient name (if mentioned)
   - Patient language preference (if mentioned, e.g., "speaks Spanish", "prefers French")
3. Then IMMEDIATELY call start_passive_listening()
4. Enter passive listening mode to capture discharge instructions

## WHAT TO CAPTURE AS INSTRUCTIONS

Capture ONLY utterances that convey actual medical guidance:
- **Medication:** name, dose, frequency, route, duration ("Take two Tylenol every four hours for pain")
- **Activity/Mobility:** restrictions or requirements ("No heavy lifting for two weeks")
- **Wound Care:** cleaning, dressing, showering guidance
- **Diet/Hydration:** specific requirements or restrictions
- **Follow-up:** appointments or scheduling tasks
- **Warning Signs:** when to call doctor or go to ER
- **Device Usage:** brace, sling, ice, compression, drain care
- **Precautions:** bathing, driving, sexual activity, smoking, alcohol restrictions

## WHAT TO IGNORE

Do NOT capture: greetings, acknowledgements, thanks, names alone, chit-chat, encouragement, partial fragments without actionable content, standalone patient names, or single-word responses.

## PASSIVE MODE BEHAVIOR

While in passive mode:
- Your speech is suppressed but you can still analyze and make tool calls
- For each message containing a discharge instruction, call collect_instruction with:
  - instruction_text: full clear sentence (include dose, frequency, duration if stated)
  - instruction_type: one of [medication | activity | wound | diet | followup | warning | device | precaution | other]
- You can only respond if directly addressed, asked to translate, or completion/verification is requested
- After processing each message, evaluate if instruction-giving is complete

## INTELLIGENT EXIT DETECTION

For each user message, think step-by-step:

**Step 1:** Does this message contain a discharge instruction? If yes, collect it.

**Step 2:** Does this message signal instruction completion? Look for:
- 🚨 **HIGHEST PRIORITY:** Direct address with "Maya" - ALWAYS exit immediately
- 🔴 **HIGH:** "Any questions?", "That's all", "We're done", "That's everything" - Exit immediately
- 🟡 **MEDIUM:** Social closings after instructions ("Good luck", "Take care", "Feel better") - Exit if instructions were given
- 🟢 **LOW:** Verification requests ("Did you get all that?", "Can you repeat that?") - Exit and provide summary

**Step 3:** If ANY completion signal detected, IMMEDIATELY call provide_instruction_summary()

**Step 4:** If no completion signal, continue passive listening

Remember: It's better to exit early when addressed than to miss an exit signal!

## EXIT PROTOCOL

When exiting passive mode:
1. Provide a concise bullet list of ONLY captured instructions (merged into complete lines)
2. Ask once if anything is missing or needs correction (≤ 1 short sentence)
3. Do NOT say you will listen quietly again

## EMAIL CONFIRMATION WORKFLOW

After providing the instruction summary, listen for confirmation signals:
- "That's correct", "Yes, that's right", "That looks good", "Perfect", "Exactly"
- "That's everything", "That's complete", "Nothing to add", "All set"

When you receive explicit confirmation from the doctor, IMMEDIATELY call send_instruction_summary_email().
Do NOT send email until you have clear confirmation.

## DIRECT QUESTIONS

If answering direct questions outside passive mode: be concise (≤2 sentences) and medically accurate. You must refer to the instructions you have captured. 
Never invent instructions - you must have captured them. Ask for clarification if needed.

Think step-by-step about whether each message contains discharge instructions or whether it signals completion of the instruction-giving process.
"""
        super().__init__(
            instructions=instructions,
            chat_ctx=chat_ctx,
            stt=deepgram.STT(model="nova-3", language="multi"),  # phone -> chat
            llm=openai.LLM(model="gpt-4.1"), # chat -> chat
            tts=openai.TTS(voice="shimmer"), # chat -> audio -> twilio.  $$$$ ElevenLabs or Hume. 
            vad=silero.VAD.load()
        )

        self._original_say = None # we monkey patch say and generate_reply to log all output
        self._original_generate_reply = None
        self._tts_suppressed = False  # TTS suppression during passive mode
        self._database = None  # PostgreSQL database connection

        # Create a lightweight OpenAI async client for custom calls (reuses env OPENAI_API_KEY)
        try:
            from livekit.plugins.openai import openai as lk_openai
            self._openai_client = lk_openai.AsyncClient()
        except Exception:
            self._openai_client = None
        
    async def on_enter(self):
        # Generate a simple session ID for tracking (use timestamp-based)
        session_id = f"session_{int(time.time())}"
        self.session.userdata.session_id = session_id
        logger.info(f"Discharge agent starting with session: {session_id}")

        # Initialize database connection
        try:
            self._database = await get_database()
            logger.info(f"[DATABASE] Connected for session: {session_id}")
        except Exception as e:
            logger.error(f"[DATABASE] Failed to connect for session {session_id}: {e}")
            # Continue without database - fallback to file logging

        # Add system message to OpenAI conversation log
        system_instructions = (
            "You are Maya, an AI discharge assistant.\n"
            "GOAL: Capture ONLY true discharge instructions while in passive mode; ignore filler.\n\n"
            "SIMPLE WORKFLOW:\n"
            "1. Briefly introduce yourself and ask who is present in the room.\n"
            "2. When the doctor responds, immediately call start_passive_listening.\n"
            "3. Then silently capture discharge instructions.\n\n"
            # ... (rest of instructions from self.instructions)
        )
        self._add_to_openai_conversation("system", system_instructions)

        # Set up logging wrapper for session.say and generate_reply
        self._original_say = self.session.say
        self._original_generate_reply = self.session.generate_reply
        self.session.say = self._logged_say # session.say("Hello!")
        self.session.generate_reply = self._logged_generate_reply # session.generate_reply(instructions="...")

        # Set up event handler for conversation items (captures all agent responses)
        @self.session.on("conversation_item_added")
        def on_conversation_item_added(event: ConversationItemAddedEvent):
            # Only log agent messages (not user messages, which we already log elsewhere)
            if event.item.role == "assistant":
                response_text = event.item.text_content or ""
                if response_text.strip():
                    logger.info(f"[on_conversation_item_added] Role: {event.item.role} | Text: '{response_text}'")
                    # Avoid duplicate logging here; wrappers handle persistence.

        await self.session.say(f"Hi all! I'm Maya, thanks for dialing me in today. So {HEALTHCARE_PROVIDER_NAME}, who do we have in the room today?", allow_interruptions=False)

    async def on_exit(self):
        """Handle session end - save to database"""
        session_id = getattr(self.session.userdata, 'session_id', 'unknown')
        logger.info(f"Session ending: {session_id}")

        # Save session to database
        await self._save_session_to_database(session_id)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Handle user speech completion with exit detection and TTS suppression during passive mode"""
        # Get passive mode status from session userdata
        is_passive_mode = getattr(self.session.userdata, 'is_passive_mode', False)
        session_id = getattr(self.session.userdata, 'session_id', 'unknown')

        # Comprehensive STT logging
        transcript_text = new_message.text_content or ""
        logger.info(f"[STT INPUT] Passive: {is_passive_mode} | {transcript_text}")

        # Store conversation in OpenAI format for file logging
        if transcript_text.strip():  # Only log non-empty messages
            self._add_to_openai_conversation("user", transcript_text)
        


    @function_tool
    async def collect_instruction(self, ctx: RunContext[SessionData], instruction_text: str):
        """
        Collect a medical discharge instruction being read aloud. These are items related to the patient's post operative recovery and care.

        Args:
            instruction_text: The instruction being given
            instruction_type: Type of instruction (medication, activity, followup, warning, etc.)
        """
        from datetime import datetime

        # Check for near-duplicates before adding
        session_id = getattr(ctx.userdata, 'session_id', 'unknown')
        cleaned_text = instruction_text.strip()

        # Log the instruction being collected
        logger.info(f"[COLLECT] {cleaned_text}")

        # Check for duplicates
        existing_instructions = getattr(ctx.userdata, 'collected_instructions', [])
        for i, existing in enumerate(existing_instructions):
            existing_text = existing.get("text", "").strip() if isinstance(existing, dict) else str(existing).strip()
            # Compare ignoring punctuation and case
            if cleaned_text.lower().rstrip('.') == existing_text.lower().rstrip('.'):
                logger.warning(f"[COLLECT] Duplicate detected! Skipping: '{cleaned_text}'")
                # Log tool call for OpenAI format
                self._log_tool_call("collect_instruction", {"instruction_text": instruction_text}, "Duplicate instruction - already noted")
                # Return silently without adding duplicate
                if ctx.userdata.workflow_mode == "passive_listening" and ctx.userdata.is_passive_mode:
                    return None, None  # Silent collection
                else:
                    return None, "I've already noted that instruction."

        entry = {
            "text": cleaned_text,
            "timestamp": datetime.now().isoformat()
        }
        ctx.userdata.collected_instructions.append(entry)
        logger.info(f"[COLLECT] Successfully collected instruction #{len(ctx.userdata.collected_instructions)}")

        # Log tool call for OpenAI format
        self._log_tool_call("collect_instruction", {"instruction_text": instruction_text}, f"Collected instruction: {cleaned_text}")

        # Update session data in database (async, non-blocking)
        await self._update_session_data()

        # Stay silent in passive mode unless directly asked
        if ctx.userdata.workflow_mode == "passive_listening" and ctx.userdata.is_passive_mode:
            return None, None  # Silent collection
        else:
            return None, "I've noted that instruction."

    @function_tool
    async def extract_patient_info(self, ctx: RunContext[SessionData], patient_name: str = None, patient_language: str = None) -> str:
        """
        Extract and store patient information from the conversation.

        Call this function when you identify the patient's name or preferred language
        from the conversation. This helps personalize the discharge process.

        Args:
            patient_name: The patient's first name if mentioned
            patient_language: The patient's preferred language (English, Spanish, French, etc.)
        """
        updates = []

        if patient_name:
            ctx.userdata.patient_name = patient_name.strip()
            updates.append(f"Patient name: {patient_name}")
            logger.info(f"[EXTRACT] Patient name: {patient_name}")

        if patient_language:
            ctx.userdata.patient_language = patient_language.strip()
            updates.append(f"Language: {patient_language}")
            logger.info(f"[EXTRACT] Patient language: {patient_language}")

        # Mark as extracted so we don't try again
        ctx.userdata.patient_info_extracted = True

        # Update session data in database
        await self._update_session_data()

        if updates:
            return f"Extracted: {', '.join(updates)}"
        else:
            return "No patient information provided"

    # Workflow Transition Functions
    @function_tool
    async def start_passive_listening(self, ctx: RunContext[SessionData]) -> None:
        """Enter passive listening mode for instruction collection."""

        ctx.userdata.workflow_mode = "passive_listening"
        ctx.userdata.is_passive_mode = True
        logger.info(f"Entering passive listening mode for session: {ctx.userdata.session_id}")

        # Patient language defaults to English if not set
        if not ctx.userdata.patient_language:
            ctx.userdata.patient_language = 'English'
            logger.info(f"[PATIENT SETUP] Defaulting to English for session: {ctx.userdata.session_id}")

        # Patient name defaults if not set
        if not ctx.userdata.patient_name:
            ctx.userdata.patient_name = 'the patient'
            logger.info(f"[PATIENT SETUP] Defaulting patient name for session: {ctx.userdata.session_id}")

        patient_language = getattr(ctx.userdata, 'patient_language', 'English')

        # Log tool call for OpenAI format
        self._log_tool_call("start_passive_listening", {}, "Entered passive listening mode")

        prompt = f"""
Follow this script exactly as written, do NOT deviate:

In English, please say:
    "Thanks for letting me know, {HEALTHCARE_PROVIDER_NAME}"

Then say in {patient_language}:
    "{ctx.userdata.patient_name}, it's a pleasure to meet you. My goal is to make
    your at-home recovery as smooth as possible. I work closely with
    {HEALTHCARE_PROVIDER_NAME}'s office to understand your surgery and recovery
    protocol. I'm going to listen quietely to capture today's discharge instructions
    and text you a summary afterwards. Over the next few days, I'll also check in on
    how you're doing and send you key reminders for things like medication and wound
    care. If you have any questions while you're recovering at home, feel free to
    text or call me anytime, I'm here 24/7 as your personal recovery assistant."

Finally please say in English:
    "Alright {HEALTHCARE_PROVIDER_NAME}, feel free to begin. I'll give a verbal
    recap at the end to make sure I've noted everything correctly for {ctx.userdata.patient_name}."
            """

        await self.session.generate_reply(instructions=prompt, allow_interruptions=False)

        # Mute audio output while in passive mode (prevent any TTS playback)
        try:
            self.session.output.set_audio_enabled(False) # turns off TTS so even if the LLM says something, it doesn't
            logger.debug("[PASSIVE AUDIO] Output audio disabled")
        except Exception as e:
            logger.error(f"[PASSIVE AUDIO] Failed to disable output audio: {e}")

        return None

    @function_tool()
    async def provide_instruction_summary(self, ctx: RunContext[SessionData]):
        """
        🚨 CRITICAL: Call this function IMMEDIATELY when discharge instruction giving is complete!
        
        EXIT PASSIVE MODE by calling this function when you detect ANY of these signals:
        
        🔴 IMMEDIATE EXIT REQUIRED:
        - Direct address: "Maya", "Hey Maya", "Maya, did you get that?"
        - Completion phrases: "That's all", "Any questions?", "We're done", "We're finished"  
        - Verification requests: "Did you capture everything?", "Can you repeat that?"
        
        🟡 LIKELY EXIT SIGNALS:
        - Social closings after instructions: "Good luck", "Take care", "Feel better"
        - Conversation shift from medical to social: "How are you feeling?" after instructions
        - Doctor addressing patient directly after giving instructions
        
        ⚡ WHEN IN DOUBT, EXIT! It's better to exit early than miss an exit signal.
        
        This function will:
        1. Exit passive listening mode
        2. Provide comprehensive summary of collected discharge instructions  
        3. Ask for confirmation or corrections
        4. Re-enable normal conversation mode
        
        Call this function AS SOON AS you detect completion - don't wait!
        """

        self.session.userdata.is_passive_mode = False
        self._tts_suppressed = False  # Re-enable TTS for exit response
        # Re-enable audio output so the summary can be heard
        try:
            self.session.output.set_audio_enabled(True)
            logger.debug("[on_user_turn_completed] Output audio re-enabled on exit")
        except Exception as e:
            logger.error(f"[on_user_turn_completed] Failed to re-enable output audio: {e}")

        is_passive_mode = getattr(ctx.userdata, 'is_passive_mode', False)
        session_id = getattr(ctx.userdata, 'session_id', 'unknown')
        
        logger.info(f"[WORKFLOW] Session: {session_id} | provide_instruction_summary called, is_passive_mode: {is_passive_mode}")
        
        if not is_passive_mode:
            return "Not currently in passive listening mode"
            
        # Exit passive mode state  
        ctx.userdata.is_passive_mode = False
        ctx.userdata.workflow_mode = "verification"
        self._tts_suppressed = False  # Re-enable TTS for summary
        # Ensure audio output is re-enabled for readback
        try:
            ctx.session.output.set_audio_enabled(True)
            logger.debug("[PASSIVE AUDIO] Output audio re-enabled for summary")
        except Exception as e:
            logger.error(f"[PASSIVE AUDIO] Failed to re-enable output audio: {e}")
        logger.info(f"[WORKFLOW] Session: {session_id} | Exiting passive mode and providing summary")
        
        # Build a deterministic summary instead of relying entirely on LLM to avoid re-enter style responses
        raw_list = ctx.userdata.collected_instructions if hasattr(ctx.userdata, 'collected_instructions') else []
        # Build from collected instruction entries (simple text + type)
        normalized: list[tuple[str,str]] = []
        for item in raw_list:
            if not item:
                continue
            if isinstance(item, dict):
                text = (item.get("text") or "").strip()
            else:
                text = str(item).strip()
                itype = "general"
            if text:
                normalized.append((text, itype))
        # De-duplicate by lowercase text preserving order
        seen = set()
        dedup: list[tuple[str,str]] = []
        for text, itype in normalized:
            key = text.lower()
            if key not in seen:
                seen.add(key)
                dedup.append((text, itype))
        logger.debug(f"[WORKFLOW] Session: {session_id} | Instruction count (unique): {len(dedup)}")

        # Simple bullet list with type labels
        bullet_lines = [f"{idx}. ({itype}) {text}" for idx, (text, itype) in enumerate(dedup, start=1)]
        summary_block = "\n".join(bullet_lines) if bullet_lines else "(No discharge instructions were detected.)"

        # Log deterministic reply content
        logger.debug(f"[WORKFLOW] Session: {session_id} | Deterministic exit summary prepared")
        
        # Log tool call for OpenAI format
        self._log_tool_call("provide_instruction_summary", {}, f"Provided summary of {len(dedup)} instructions")

        # Send deterministic summary first to avoid LLM drifting back into passive intro
        await ctx.session.generate_reply(instructions=f"""
Here are the discharge instructions you captured:\n{summary_block}

If you didn't capture any, let them know in English.




In English, read off the discharge instructions in this general structure:
"Okay, here's what I captured.

First, XXX
Second, XXX
And Finally, XXX

Does that sound right?"

The Patient's name is {ctx.userdata.patient_name or 'the patient'} and their native language is {ctx.userdata.patient_language or 'English'}.

If the patient's native language is not English, ask {HEALTHCARE_PROVIDER_NAME}
if they would like you to repeat the instructions in {ctx.userdata.patient_language or 'English'}.
""")

        return "Exited passive listening mode and provided summary"

    @function_tool
    async def send_instruction_summary_email(self, ctx: RunContext[SessionData]):
        """
        Send the confirmed instruction summary via email as SMS-formatted message.
        
        Call this function ONLY after the doctor has confirmed that the instruction 
        summary is complete and correct. This will send the summary to the configured
        email address for further processing or SMS delivery.
        
        DO NOT call this function until you have received explicit confirmation
        that the instructions are accurate and complete.
        """
        session_id = getattr(ctx.userdata, 'session_id', 'unknown')
        patient_name = getattr(ctx.userdata, 'patient_name', None)

        await self.session.say(f"Give me one moment while I send the instruction summary.")
        
        logger.info(f"[EMAIL] Session: {session_id} | Attempting to send instruction summary email")
        
        # Check if email is configured
        if not GMAIL_USERNAME or not GMAIL_APP_PASSWORD or not SUMMARY_EMAIL_RECIPIENT:
            error_msg = "Email not configured - missing Gmail credentials or recipient"
            logger.warning(f"[EMAIL] Session: {session_id} | {error_msg}")
            return f"Email sending is not configured. {error_msg}"
        
        # Get collected instructions and deduplicate them (same logic as provide_instruction_summary)
        raw_instructions = getattr(ctx.userdata, 'collected_instructions', [])
        logger.debug(f"[EMAIL] Session: {session_id} | Raw instruction count: {len(raw_instructions)}")
        
        if not raw_instructions:
            logger.warning(f"[EMAIL] Session: {session_id} | No instructions found to send")
            return "No instructions available to send via email"
        
        # Log raw instructions for debugging
        for i, instr in enumerate(raw_instructions):
            if isinstance(instr, dict):
                text = instr.get("text", "").strip()
            else:
                text = str(instr).strip()
            logger.debug(f"[EMAIL] Session: {session_id} | Raw instruction {i+1}: '{text}'")
        
        # Deduplicate instructions (same logic as provide_instruction_summary)
        normalized = []
        for item in raw_instructions:
            if not item:
                continue
            if isinstance(item, dict):
                text = (item.get("text") or "").strip()
            else:
                text = str(item).strip()
            if text:
                normalized.append({"text": text})
        
        # De-duplicate by lowercase text preserving order
        seen = set()
        instructions = []
        for item in normalized:
            text = item["text"]
            key = text.lower().rstrip('.')  # Remove trailing period for comparison
            if key not in seen:
                seen.add(key)
                instructions.append(item)
        
        logger.info(f"[EMAIL] Session: {session_id} | Deduplicated instruction count: {len(instructions)} (was {len(raw_instructions)})")
        for i, instr in enumerate(instructions):
            logger.debug(f"[EMAIL] Session: {session_id} | Final instruction {i+1}: '{instr['text']}'")
        
        if not instructions:
            logger.warning(f"[EMAIL] Session: {session_id} | No valid instructions after deduplication")
            return "No valid instructions available to send via email"
        
        # Send the email
        patient_language = getattr(ctx.userdata, 'patient_language', 'English')
        success, message = send_instruction_summary_email(
            instructions=instructions,
            patient_name=patient_name,
            session_id=session_id,
            gmail_username=GMAIL_USERNAME,
            gmail_app_password=GMAIL_APP_PASSWORD,
            recipient_email=SUMMARY_EMAIL_RECIPIENT,
            patient_language=patient_language,
            healthcare_provider_name=HEALTHCARE_PROVIDER_NAME
        )

        # Log tool call for OpenAI format
        if success:
            self._log_tool_call("send_instruction_summary_email", {"patient_name": patient_name}, f"Email sent successfully with {len(instructions)} instructions")
        else:
            self._log_tool_call("send_instruction_summary_email", {"patient_name": patient_name}, f"Email failed: {message}")

        if success:
            logger.info(f"[EMAIL] Session: {session_id} | Email sent successfully")

            patient_language = getattr(ctx.userdata, 'patient_language', 'English')

            if patient_language != 'English':
                prompt = f"""
First say in English: "Thanks for confirming and the instructions have been sent."

Then in the patient's native language ({patient_language}) say:

"{patient_name}, like I mentioned before, I'll send a summary to
your email now for reference, and check-in on you over the next few days. If you
have any questions, I'm only a text or phone call away."

Then in English say:
"If you need anything else, let me know. Otherwise feel free to hang up."
                """
            else:
                prompt = f"""
Thanks for confirming.

{patient_name}, like I mentioned before, I'll send a summary to
your email now for reference, and check-in on you over the next few days. If you
have any questions, I'm only a text or phone call away.

If you need anything else, let me know. Otherwise feel free to hang up.
                """

            await self.session.generate_reply(instructions=prompt, allow_interruptions=False)

            return None
        else:
            logger.error(f"[EMAIL] Session: {session_id} | Email failed: {message}")
            return f"❌ Failed to send email: {message}"

    def _is_maya_directly_addressed(self, message_lower: str) -> bool:
        """
        Hypothesis 1: Maya Context Discrimination
        
        Determine if Maya is being directly addressed vs just mentioned in conversation.
        Direct address patterns should trigger exit, contextual mentions should not.
        
        DIRECT ADDRESS (should EXIT):
        - "Maya, [anything]" 
        - "Hey Maya"
        - "[anything], Maya"
        - "Did you [verb] that, Maya?"
        
        CONTEXTUAL MENTION (should CONTINUE):
        - "Maya is our coordinator"
        - "ask Maya about this"
        - "Maya mentioned earlier"
        """
        
        import re
        
        # Direct address patterns - check contextual patterns FIRST
        # If contextual pattern matches, don't check direct patterns
        
        # First check contextual mention patterns (should NOT trigger)
        contextual_patterns = [
            r'ask maya\b',           # "ask maya about"
            r'maya is\b',            # "maya is our coordinator"
            r'maya mentioned\b',     # "maya mentioned earlier"  
            r'maya said\b',          # "maya said something"
            r'maya told\b',          # "maya told us"
            r'\bmaya is our\b',      # "maya is our coordinator" - more specific
        ]
        
        # If contextual pattern matches, return False immediately
        for pattern in contextual_patterns:
            if re.search(pattern, message_lower):
                return False
        
        # Only then check direct address patterns
        direct_patterns = [
            r'^maya[,\s]',           # "maya, did you get that"
            r'^hey maya\b',          # "hey maya"
            r'^maya\s*-',            # "maya - did you understand"  
            r',\s*maya[^a-z]',       # "did you get that, maya?"
            r'\bmaya[,\?!]',         # "maya?" or "maya!"
        ]
        
        # Check if any direct address pattern matches
        for pattern in direct_patterns:
            if re.search(pattern, message_lower):
                return True
        
        # Default: if "maya" appears but no clear pattern, be conservative (don't trigger)
        return False

    def _should_exit_passive_mode(self, transcript: str) -> bool:
        """
        Analyze transcript to determine if agent should exit passive listening mode.
        
        Args:
            transcript: The user's speech transcript
            
        Returns:
            True if agent should exit passive mode, False otherwise
        """
        if not transcript:
            return False
            
        # Convert to lowercase for case-insensitive matching
        text = transcript.lower().strip()
        # Detailed debug logging of evaluation
        logger.debug(f"[PASSIVE CHECK] Evaluating transcript for exit: '{text}'")
        
        # Direct address patterns (strict)
        if self._is_maya_directly_addressed(text):
            logger.debug("[PASSIVE CHECK] Matched direct address to Maya (strict)")
            return True

        # Completion signals
        completion_phrases = [
            "finished", "done", "that's all", "we're done", "we're all set",
            "any questions", "all done", "we're finished", "that's it",
            "that's everything", "that covers it", "that covers everything", "that should be everything",
            "that should be it", "nothing else", "nothing more", "wrap up", "wraps up",
        ]
        # Exclusions for partial/section completion
        exclusion_phrases = [
            "almost finished", "almost done", "done with this", "finished with this",
            "this particular", "one instruction down"
        ]
        for phrase in completion_phrases:
            if phrase in text:
                if any(ex in text for ex in exclusion_phrases):
                    logger.debug(f"[PASSIVE CHECK] Ignoring partial completion around: '{phrase}'")
                    break
                logger.debug(f"[PASSIVE CHECK] Matched completion phrase: '{phrase}'")
                return True
                
        # NOTE: Translation requests should NOT exit passive mode; handled elsewhere

        # Social closings (exit only if we have captured some instructions)
        social_closings = [
            "good luck", "take care", "feel better", "have a good day", "see you later",
            "get well", "rest well", "be safe", "speedy recovery", "get some rest", "heal well"
        ]
        if any(phrase in text for phrase in social_closings):
            try:
                collected = getattr(self.session.userdata, 'collected_instructions', [])
                if collected and len(collected) > 0:
                    logger.debug("[PASSIVE CHECK] Matched social closing after instructions")
                    return True
            except Exception:
                # If session not available here, be conservative and continue
                pass

        # Capture verification
        capture_phrases = [
            "did you get", "did you capture", "did you hear", "did you catch",
            "get all that", "capture all", "hear all"
        ]
        for phrase in capture_phrases:
            if phrase in text:
                logger.debug(f"[PASSIVE CHECK] Matched capture verification phrase: '{phrase}'")
                return True
                
        # Explicit exit instructions
        exit_phrases = [
            "exit passive", "stop listening", "exit listening"
        ]
        for phrase in exit_phrases:
            if phrase in text:
                logger.debug(f"[PASSIVE CHECK] Matched explicit exit phrase: '{phrase}'")
                return True
                
        logger.debug("[PASSIVE CHECK] No exit trigger matched for transcript")
        return False



        
    async def _logged_say(self, message: str, allow_interruptions: bool = True):
        """Wrapper for session.say that logs all outgoing messages and handles TTS suppression"""
        logger.info(f"[LLM OUTPUT] {message}")

        # Store conversation in OpenAI format for file logging
        self._add_to_openai_conversation("assistant", message)

        # Check if TTS should be suppressed during passive mode
        if self._tts_suppressed:
            logger.info(f"[TTS SUPPRESSED] Passive mode - message logged but not spoken: {message}")
            return None  # Suppress TTS output

        # Call original say method for normal speech
        return await self._original_say(message, allow_interruptions=allow_interruptions)

    async def _logged_generate_reply(self, *args, **kwargs):
        """Wrapper for session.generate_reply that logs responses"""
        # Call original generate_reply method and capture response
        response = await self._original_generate_reply(*args, **kwargs)

        # Log the generated response if available
        if hasattr(response, 'text_content') and response.text_content:
            logger.info(f"[LLM GENERATE_REPLY] {response.text_content}")

            # Store conversation in OpenAI format for file logging
            self._add_to_openai_conversation("assistant", response.text_content)

        return response

    async def _passive_openai_analysis(self, session_id: str, transcript_text: str) -> None:
        """Async stub that calls OpenAI for passive-mode analysis without speaking.
        This is intentionally non-blocking and logs the model's brief classification or summary.
        """
        if self._openai_client is None:
            return
        try:
            # Keep it tiny & fast: one short response
            prompt = (
                "You are analyzing a clinician-patient conversation during passive listening. "
                "Briefly classify this utterance (<= 12 words) as one of: instruction | question | chit-chat | other. "
                "Then, if it is clearly a discharge instruction, produce a compact instruction candidate; otherwise say 'none'.\n\n"
                f"Utterance: {transcript_text}"
            )
            resp = await self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=40,
                temperature=0.2,
            )
            content = resp.choices[0].message.content if resp and resp.choices else ""
            if content:
                logger.info(f"[_passive_openai_analysis] Session: {session_id} | {content}")
        except Exception as e:
            logger.error(f"[_passive_openai_analysis] OpenAI call failed: {e}")

    def _add_to_openai_conversation(self, role: str, content: str, tool_calls=None, tool_call_id=None):
        """Add a message to the OpenAI format conversation log"""
        try:
            message = {
                "role": role,
                "content": content
            }

            # Add tool_calls for assistant messages
            if role == "assistant" and tool_calls:
                message["tool_calls"] = tool_calls

            # Add tool_call_id for tool messages
            if role == "tool" and tool_call_id:
                message["tool_call_id"] = tool_call_id

            self.session.userdata.openai_conversation.append(message)

        except Exception as e:
            logger.error(f"Failed to add message to OpenAI conversation log: {e}")

    def _log_tool_call(self, function_name: str, arguments: dict, result: str):
        """Log a tool call in OpenAI format"""
        try:
            import uuid
            tool_call_id = f"call_{uuid.uuid4().hex[:8]}"

            # Create tool call structure
            tool_call = {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": str(arguments)  # Convert to string as OpenAI expects
                }
            }

            # Add assistant message with tool call
            self._add_to_openai_conversation("assistant", "", tool_calls=[tool_call])

            # Add tool result message
            self._add_to_openai_conversation("tool", result, tool_call_id=tool_call_id)

        except Exception as e:
            logger.error(f"Failed to log tool call {function_name}: {e}")

    async def _save_session_to_database(self, session_id: str):
        """Save session data to PostgreSQL database"""
        try:
            if not self._database:
                logger.warning(f"[DATABASE] No database connection for session {session_id}")
                return

            # Prepare session data
            timestamp = getattr(self.session.userdata, 'session_start_time', 'unknown')
            patient_name = getattr(self.session.userdata, 'patient_name', None)
            patient_language = getattr(self.session.userdata, 'patient_language', None)
            transcript = getattr(self.session.userdata, 'openai_conversation', [])
            collected_instructions = getattr(self.session.userdata, 'collected_instructions', [])

            # Save to database
            success = await self._database.save_session(
                session_id=session_id,
                timestamp=timestamp,
                patient_name=patient_name,
                patient_language=patient_language,
                transcript=transcript,
                collected_instructions=collected_instructions
            )

            if success:
                logger.info(f"[DATABASE] Session {session_id} saved successfully")
            else:
                logger.error(f"[DATABASE] Failed to save session {session_id}")

        except Exception as e:
            logger.error(f"[DATABASE] Error saving session {session_id}: {e}")

    async def _update_session_data(self):
        """Update session data in database during conversation (non-blocking)"""
        session_id = getattr(self.session.userdata, 'session_id', 'unknown')
        # Save asynchronously without waiting
        asyncio.create_task(self._save_session_to_database(session_id))


# Unified entrypoint for both console and production modes
async def entrypoint(ctx: JobContext):
    """Unified entrypoint for discharge workflow with noise cancellation"""
    # Check if this is an outbound followup call
    if ctx.job and ctx.job.metadata:
        try:
            import json
            metadata = json.loads(ctx.job.metadata)

            # If there's call_schedule_item metadata, this is an outbound followup call
            if metadata.get("call_schedule_item"):
                logger.info("Routing to followup workflow for outbound call")
                from followup.agents import scheduled_followup_entrypoint
                return await scheduled_followup_entrypoint(ctx)

        except (json.JSONDecodeError, KeyError):
            # If metadata parsing fails, default to discharge workflow
            pass

    # Default to discharge workflow
    logger.info("Routing to discharge workflow for inbound call")
    await ctx.connect()

    session = AgentSession[SessionData](
        userdata=SessionData(),
        user_away_timeout=30.0
    )

    agent = DischargeAgent()

    # Add idle/silence handler: auto-exit passive mode after sustained silence
    from livekit.agents import UserStateChangedEvent
    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent):
        try:
            if getattr(session.userdata, 'is_passive_mode', False) and ev.new_state == "away":
                async def _auto_exit():
                    logger.info("[SILENCE EXIT] Sustained silence detected; exiting passive mode")
                    session.userdata.is_passive_mode = False
                    agent._tts_suppressed = False
                    # Re-enable audio output for summary
                    try:
                        session.output.set_audio_enabled(True)
                        logger.debug("[PASSIVE AUDIO] Output audio re-enabled on silence exit")
                    except Exception as e:
                        logger.error(f"[PASSIVE AUDIO] Failed to re-enable output audio: {e}")
                    # await agent._exit_passive_mode_and_summarize()  # [REDUNDANT] - method not defined
                asyncio.create_task(_auto_exit())
        except Exception as e:
            logger.error(f"[SILENCE EXIT] Handler error: {e}")

    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        )
    )

# Main entry point
def main():
    """Main function for running discharge workflow"""
    import sys
    import signal

    # Environment variables are loaded in discharge.config module

    # Health endpoint is started by `agent/main.py` in non-console mode

    # Setup cleanup handler
    def cleanup_handler(signum=None, frame=None):
        logger.info("Cleaning up resources...")
        try:
            # Use asyncio to properly close database connections
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(close_database())
            else:
                asyncio.run(close_database())
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)

    try:
        # Check for required OpenAI key
        if not os.getenv("OPENAI_API_KEY"):
            print("❌ OPENAI_API_KEY required. Exiting...")
            sys.exit(1)

        # Display mode information
        if is_console_mode():
            print("🎯 Starting PostOp AI Discharge Workflow in Console Mode")
        else:
            print("🚀 Starting PostOp AI Discharge Workflow in Production Mode")

        cli.run_app(WorkerOptions(
            agent_name=LIVEKIT_AGENT_NAME,
            entrypoint_fnc=entrypoint,
            drain_timeout=60  # 60 seconds for faster Fly.io deployments
        ))
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        cleanup_handler()
    except Exception as e:
        logger.error(f"Application error: {e}")
        cleanup_handler()
    finally:
        # Ensure cleanup happens
        cleanup_handler()

if __name__ == "__main__":
    main()