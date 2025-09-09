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
   - Integrates with Redis memory for session persistence
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
- Redis Memory: Session persistence and instruction storage
- Scheduling System: Intelligent follow-up call generation via LLM analysis
- Medical RAG: Integration with medical knowledge base for enhanced responses

SUPPORTED LANGUAGES:
- English (passive listening mode)
- Spanish, Portuguese, French, German, Italian, Dutch, Russian, Arabic, Chinese, Japanese
- Real-time translation with medical terminology accuracy

TECHNICAL FEATURES:

- Session Management: Redis-based persistence across agent handoffs
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
import livekit.api as api
from livekit.agents import Agent, AgentSession, RunContext, JobContext, WorkerOptions, cli, ConversationItemAddedEvent
from livekit.agents.llm import ChatContext, ChatMessage, StopResponse, function_tool
from livekit.plugins import deepgram, openai, silero
from livekit.plugins import hume

# Health check endpoint is handled by `agent/main.py`
# Import configuration and utilities
from .config import AGENT_NAME, LIVEKIT_AGENT_NAME, POSTOP_VOICE_ID, GMAIL_USERNAME, GMAIL_APP_PASSWORD, SUMMARY_EMAIL_RECIPIENT
# Removed unused imports
from shared import RedisMemory, prompt_manager
from shared.email_service import send_instruction_summary_email

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
    workflow_mode: str = "setup"  # setup -> passive_listening/active_translation -> verification
    is_passive_mode: bool = False
    collected_instructions: list = None
    room_people: list = None
    # Tool-captured discharge instructions
    instructions_map: dict | None = None  # normalized_instruction -> category
    
    def __post_init__(self):
        if self.collected_instructions is None:
            self.collected_instructions = []
        if self.room_people is None:
            self.room_people = []
        if self.instructions_map is None:
            self.instructions_map = {}
    


class DischargeAgent(Agent):
    """Initial agent that handles patient setup and routing to appropriate workflow"""
    
    def __init__(self, chat_ctx=None):
        """
        Initialize Discharge Agent
        
        Args:
            chat_ctx: Chat context from previous agent (for conversation continuity)
        """
        # Load initial discharge agent instructions from YAML (currently simplified inline)
        instructions = (
            "You are Maya, an AI discharge assistant.\n"
            "GOAL: Capture ONLY true discharge instructions while in passive mode; ignore filler.\n\n"
            "SIMPLE WORKFLOW:\n"
            "1. Briefly introduce yourself and ask who is present in the room.\n"
            "2. When the doctor responds, immediately call start_passive_listening.\n"
            "3. Then silently capture discharge instructions.\n\n"
            "Capture IF the utterance conveys actual medical guidance (examples):\n"
            "- Medication: name, dose, frequency, route, duration (\"Take two Tylenol every four hours for pain\")\n"
            "- Activity / mobility restrictions (\"No heavy lifting for two weeks\")\n"
            "- Wound or incision care (cleaning, dressing, showering guidance)\n"
            "- Diet / hydration requirements\n"
            "- Follow-up appointments or scheduling tasks\n"
            "- Warning signs / when to call doctor / ER triggers\n"
            "- Device usage or care (brace, sling, ice, compression, drains)\n"
            "- Explicit precautions (bathing, driving, sexual activity, smoking, alcohol)\n\n"
            "IGNORE (do NOT capture): greetings, acknowledgements, thanks, names/vocatives alone, chit-chat, encouragement, partial fragments without actionable content, standalone patient name, or single-word responses.\n\n"
            
            "During passive mode, you can only respond if directly addressed, asked to translate, or completion/verification is requested.\n\n"
            "On exit (triggered by name or completion phrase):\n"
            "1. Provide concise bullet list of ONLY captured instructions (merged into complete lines; no filler numbers if none captured).\n"
            "2. Ask once if anything is missing or needs correction (<= 1 short sentence).\n"
            "3. Do NOT say you will now listen quietly again.\n"
            "4. After the doctor confirms instructions are complete and correct, call send_instruction_summary_email to send the summary via email.\n\n"
            "If answering a direct question (outside passive): concise (<=2 sentences), medically accurate.\n"
            "Never invent an instruction; if uncertain, ask for clarification instead of guessing.\n\n"
            "CRITICAL PASSIVE MODE RULES:\n"
            "While passive, your speech is suppressed but you can still analyze and make tool calls:\n"
            "* If it contains a discharge instruction, call collect_instruction with:\n"
            "    instruction_text: full clear sentence (add dose, frequency, duration if stated)\n"
            "    instruction_type: one of medication | activity | wound | diet | followup | warning | device | precaution | other\n"
            "* IMPORTANT: After processing each user message, think step-by-step if discharge instruction giving is complete\n"
            "* If complete, IMMEDIATELY call provide_instruction_summary to exit passive mode\n"
            "* If it is NOT an instruction (greeting, acknowledgement, chit‑chat), you may respond but your speech will be suppressed.\n\n"
            "INTELLIGENT EXIT DETECTION - THINK STEP BY STEP:\n"
            "For each user message, ask yourself:\n"
            "Step 1: Does this message contain a discharge instruction? If yes, collect it.\n"
            "Step 2: Does this message signal instruction completion? Look for:\n"
            "   - DIRECT ADDRESS: \"Maya\", \"Hey Maya\", \"Maya, are you there?\", \"Maya, did you get that?\"\n"
            "   - COMPLETION SIGNALS: \"That's all\", \"That's everything\", \"Any questions?\", \"We're done\", \"We're finished\", \"That covers it\"\n"
            "   - VERIFICATION REQUESTS: \"Did you get all that?\", \"Did you capture everything?\", \"Can you repeat that?\"\n"
            "   - SOCIAL CLOSINGS: \"Good luck\", \"Take care\", \"Feel better\", \"Have a good day\", \"See you later\"\n"
            "   - CONVERSATION SHIFTS: Moving from medical instructions to social pleasantries\n"
            "Step 3: If ANY completion signal detected, IMMEDIATELY call provide_instruction_summary\n"
            "Step 4: If no completion signal, continue passive listening\n\n"
            "EXIT SIGNAL PRIORITY (call provide_instruction_summary if ANY detected):\n"
            "🚨 HIGHEST: Direct address with \"Maya\" - ALWAYS exit immediately\n"
            "🔴 HIGH: \"Any questions?\", \"That's all\", \"We're done\" - Exit immediately  \n"
            "🟡 MEDIUM: Social closings after instructions - Exit if instructions were given\n"
            "🟢 LOW: Verification requests - Exit and provide summary\n"
            "Remember: It's better to exit early when addressed than to miss an exit signal!\n\n"
            "EMAIL SENDING WORKFLOW:\n"
            "After providing the instruction summary, listen for confirmation signals:\n"
            "- \"That's correct\", \"Yes, that's right\", \"That looks good\", \"Perfect\", \"Exactly\"\n"
            "- \"That's everything\", \"That's complete\", \"Nothing to add\", \"All set\"\n"
            "When you receive confirmation, IMMEDIATELY call send_instruction_summary_email.\n"
            "Do NOT send email until you have explicit confirmation from the doctor."
        )

        tts = openai.TTS(voice="shimmer", instructions="Middle-age black woman, clear Atlanta accent, that exudes warmth, care and confidence. Speaks at a measured pace and is conversational - like a friend, a caring nurse, or your mother.")

        # if is_console_mode():
        #     tts = openai.TTS(voice="shimmer")
        # else:
        #     tts = hume.TTS(
        #         voice=hume.VoiceById(id=POSTOP_VOICE_ID),
        #         description="Middle-age black woman, clear Atlanta accent, that exudes warmth, care and confidence. Speaks at a measured pace and is conversational - like a friend, a caring nurse, or your mother."
        #     )

        super().__init__(
            instructions=instructions,
            chat_ctx=chat_ctx,
            stt=deepgram.STT(model="nova-3", language="multi"),
            llm=openai.LLM(model="gpt-4.1"),
            tts=tts,
            vad=silero.VAD.load()
        )

        self.memory = RedisMemory()

        import redis
        import os
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

        self._original_say = None # we monkey patch say and generate_reply to log all output
        self._original_generate_reply = None
        self._tts_suppressed = False  # TTS suppression during passive mode
        
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
        
        # Set up logging wrapper for session.say and generate_reply
        self._original_say = self.session.say
        self._original_generate_reply = self.session.generate_reply
        self.session.say = self._logged_say
        self.session.generate_reply = self._logged_generate_reply
        
        # Set up event handler for conversation items (captures all agent responses)
        @self.session.on("conversation_item_added")
        def on_conversation_item_added(event: ConversationItemAddedEvent):
            # Only log agent messages (not user messages, which we already log elsewhere)
            if event.item.role == "assistant":
                session_id = getattr(self.session.userdata, 'session_id', 'unknown')
                response_text = event.item.text_content or ""
                if response_text.strip():
                    logger.info(f"[on_conversation_item_added] Session: {session_id} | Role: {event.item.role} | Text: '{response_text}'")
                    print(f"[on_conversation_item_added] Session: {session_id} | Role: {event.item.role} | Text: '{response_text}'")
                    # Avoid writing to Redis here to prevent duplicates; wrappers handle persistence.

        await self.session.say(f"Hi all! I'm Maya, thanks for dialing me in today. So {HEALTHCARE_PROVIDER_NAME}, who do we have in the room today?", allow_interruptions=False)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Handle user speech completion with exit detection and TTS suppression during passive mode"""
        # Get passive mode status from session userdata
        is_passive_mode = getattr(self.session.userdata, 'is_passive_mode', False)
        session_id = getattr(self.session.userdata, 'session_id', 'unknown')
        
        # Comprehensive STT logging with session tracking
        transcript_text = new_message.text_content or ""
        logger.info(f"[STT INPUT] Session: {session_id} | Passive: {is_passive_mode} | Text: '{transcript_text}'")
        print(f"[CONVERSATION LOG] Session: {session_id} | USER INPUT: '{transcript_text}'")
        
        # Store conversation in Redis
        if transcript_text.strip():  # Only log non-empty messages
            self._log_conversation_message(session_id, "user", transcript_text)
        
        # Extract patient info quietly in the background (only once)
        if not getattr(self.session.userdata, 'patient_info_extracted', False):
            self._extract_patient_info_quietly(transcript_text, session_id)
        


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
        logger.info(f"[COLLECT] Session: {session_id} | Collecting: '{cleaned_text}'")
        
        # Check for duplicates
        existing_instructions = getattr(ctx.userdata, 'collected_instructions', [])
        for i, existing in enumerate(existing_instructions):
            existing_text = existing.get("text", "").strip() if isinstance(existing, dict) else str(existing).strip()
            # Compare ignoring punctuation and case
            if cleaned_text.lower().rstrip('.') == existing_text.lower().rstrip('.'):
                logger.warning(f"[COLLECT] Session: {session_id} | Duplicate detected! Skipping: '{cleaned_text}' (matches #{i+1}: '{existing_text}')")
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
        logger.info(f"[COLLECT] Session: {session_id} | Successfully collected instruction #{len(ctx.userdata.collected_instructions)}: '{entry['text'][:60]}...'")
        
        # Stay silent in passive mode unless directly asked
        if ctx.userdata.workflow_mode == "passive_listening" and ctx.userdata.is_passive_mode:
            return None, None  # Silent collection
        else:
            return None, "I've noted that instruction."

    # Workflow Transition Functions
    @function_tool
    async def start_passive_listening(self, ctx: RunContext[SessionData]):
        """Enter passive listening mode for instruction collection."""
        
        ctx.userdata.workflow_mode = "passive_listening"
        ctx.userdata.is_passive_mode = True
        logger.info(f"Entering passive listening mode for session: {ctx.userdata.session_id}")
        
        # Also store in memory for persistence
        self.memory.store_session_data(ctx.userdata.session_id, "workflow_mode", "passive_listening")
        self.memory.store_session_data(ctx.userdata.session_id, "is_passive_mode", True)

        # Patient language defaults to English if not set
        if not ctx.userdata.patient_language:
            ctx.userdata.patient_language = 'English'
            logger.info(f"[PATIENT SETUP] Defaulting to English for session: {ctx.userdata.session_id}")
        
        # Patient name defaults if not set
        if not ctx.userdata.patient_name:
            ctx.userdata.patient_name = 'the patient'
            logger.info(f"[PATIENT SETUP] Defaulting patient name for session: {ctx.userdata.session_id}")
        
        patient_language = getattr(ctx.userdata, 'patient_language', 'English')

        await self.session.say(f"Thanks for letting me know, {HEALTHCARE_PROVIDER_NAME}", allow_interruptions=False)

        prompt = f"""
Say in {patient_language}: 
"{ctx.userdata.patient_name}, it's a pleasure to meet you. My goal is to make
your at-home recovery as smooth as possible. I work closely with
{HEALTHCARE_PROVIDER_NAME}'s office to understand your surgery and recovery
protocol. I'm going to listen quietely to capture today's discharge instructions
and text you a summary afterwards. Over the next few days, I'll also check in on
how you're doing and send you key reminders for things like medication and wound
care. If you have any questions while you're recovering at home, feel free to
text or call me anytime, I'm here 24/7 as your personal recovery assistant."
            """

        await self.session.generate_reply(instructions=prompt, allow_interruptions=False)

        await self.session.say(f"""
Alright {HEALTHCARE_PROVIDER_NAME}, feel free to begin. I'll give a verbal recap at the end to make sure I've noted everything correctly for {ctx.userdata.patient_name}.
        """, allow_interruptions=False)

        # Mute audio output while in passive mode (prevent any TTS playback)
        try:
            self.session.output.set_audio_enabled(False)
            logger.debug("[PASSIVE AUDIO] Output audio disabled")
        except Exception as e:
            logger.error(f"[PASSIVE AUDIO] Failed to disable output audio: {e}")

        return None, None
    
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
            patient_language=patient_language
        )

        
        if success:
            logger.info(f"[EMAIL] Session: {session_id} | Email sent successfully")

            patient_language = getattr(ctx.userdata, 'patient_language', 'English')
            
            if patient_language != 'English':
                prompt = f"""
First say in English: "Thanks for confirming." 

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

    def _extract_patient_info_quietly(self, transcript_text: str, session_id: str):
        """Extract patient name and language from conversation quietly"""
        import re
        
        # Extract patient name patterns
        name_patterns = [
            r'this is (\w+)',
            r'we have (\w+)',
            r'patient is (\w+)',
            r'(\w+) is here',
            r'(\w+) is the patient'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, transcript_text.lower())
            if match:
                patient_name = match.group(1).title()
                self.session.userdata.patient_name = patient_name
                logger.info(f"[AUTO EXTRACT] Session: {session_id} | Patient name: {patient_name}")
                self.memory.store_session_data(session_id, "patient_name", patient_name)
                break
        
        # Extract language patterns
        language_patterns = [
            r'speaks? (spanish|chinese|french|german|italian|portuguese|dutch|russian|arabic|japanese)',
            r'language is (spanish|chinese|french|german|italian|portuguese|dutch|russian|arabic|japanese)',
            r'prefers? (spanish|chinese|french|german|italian|portuguese|dutch|russian|arabic|japanese)'
        ]
        
        supported_languages = {
            'spanish': 'Spanish', 'chinese': 'Chinese', 'french': 'French',
            'german': 'German', 'italian': 'Italian', 'portuguese': 'Portuguese',
            'dutch': 'Dutch', 'russian': 'Russian', 'arabic': 'Arabic', 'japanese': 'Japanese'
        }
        
        for pattern in language_patterns:
            match = re.search(pattern, transcript_text.lower())
            if match:
                lang_key = match.group(1).lower()
                patient_language = supported_languages.get(lang_key, 'English')
                self.session.userdata.patient_language = patient_language
                logger.info(f"[AUTO EXTRACT] Session: {session_id} | Patient language: {patient_language}")
                self.memory.store_session_data(session_id, "patient_language", patient_language)
                break
        else:
            # Default to English if no language mentioned
            self.session.userdata.patient_language = 'English'
            logger.info(f"[AUTO EXTRACT] Session: {session_id} | Defaulting to English")
        
        # Mark as extracted so we don't do this again
        self.session.userdata.patient_info_extracted = True

    def _log_conversation_message(self, session_id: str, role: str, message: str):
        """Log conversation message to Redis"""
        try:
            import json
            import time
            
            # Create message entry
            msg_data = {
                "timestamp": time.time(),
                "role": role,
                "message": message.strip()
            }
            
            # Store in Redis
            key = f"postop:conversations:{session_id}"
            self.redis_client.lpush(key, json.dumps(msg_data))
            
            # Add session to sessions set for listing
            self.redis_client.sadd("postop:conversations:sessions", session_id)
            
        except Exception as e:
            logger.error(f"Failed to log conversation message: {e}")
        
    async def _logged_say(self, message: str, allow_interruptions: bool = True):
        """Wrapper for session.say that logs all outgoing messages and handles TTS suppression"""
        session_id = getattr(self.session.userdata, 'session_id', 'unknown')
        logger.info(f"[LLM OUTPUT] Session: {session_id} | Text: '{message}'")
        print(f"[CONVERSATION LOG] Session: {session_id} | MAYA OUTPUT: '{message}'")
        
        # Store conversation in Redis
        self._log_conversation_message(session_id, "assistant", message)
        
        # Check if TTS should be suppressed during passive mode
        if self._tts_suppressed:
            logger.info(f"[TTS SUPPRESSED] Session: {session_id} | Passive mode - message logged but not spoken: '{message}'")
            print(f"[TTS SUPPRESSED] Session: {session_id} | PASSIVE MODE: '{message}'")
            return None  # Suppress TTS output
        
        # Call original say method for normal speech
        return await self._original_say(message, allow_interruptions=allow_interruptions)

    async def _logged_generate_reply(self, *args, **kwargs):
        """Wrapper for session.generate_reply that logs responses"""
        # Call original generate_reply method and capture response
        response = await self._original_generate_reply(*args, **kwargs)
        
        # Log the generated response if available
        if hasattr(response, 'text_content') and response.text_content:
            session_id = getattr(self.session.userdata, 'session_id', 'unknown')
            logger.info(f"[LLM GENERATE_REPLY] Session: {session_id} | Text: '{response.text_content}'")
            print(f"[CONVERSATION LOG] Session: {session_id} | MAYA GENERATE_REPLY: '{response.text_content}'")
            
            # Store conversation in Redis
            self._log_conversation_message(session_id, "assistant", response.text_content)
        
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


# Console entrypoint
async def console_entrypoint(ctx: JobContext):
    """Console entrypoint - uses OpenAI TTS"""
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
        user_away_timeout=30.0  # Consider away after 30s of silence
    )

    ## CLAUDE: STOP CHANGING THIS TO THE ConsentCollector
    agent = DischargeAgent()
    
    # Add idle/silence handler: auto-exit passive mode after sustained silence
    from livekit.agents import UserStateChangedEvent
    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent):
        try:
            if getattr(session.userdata, 'is_passive_mode', False) and ev.new_state == "away":
                # Run in background to avoid blocking event loop
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
                    await agent._exit_passive_mode_and_summarize()
                asyncio.create_task(_auto_exit())
        except Exception as e:
            logger.error(f"[SILENCE EXIT] Handler error: {e}")

    await session.start(
        agent=agent,
        room=ctx.room
    )

# Production entrypoint (with TTS auto-detection)
async def production_entrypoint(ctx: JobContext):
    """Production entrypoint with TTS auto-detection"""
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
    
    # Default to discharge workflow with auto-detected TTS
    logger.info("Routing to discharge workflow for inbound call")
    await ctx.connect()
    
    session = AgentSession[SessionData](
        userdata=SessionData(),
        user_away_timeout=30.0
    )
    agent = DischargeAgent()  # Uses ElevenLabs TTS in production
    
    # Add idle/silence handler
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
                    await agent._exit_passive_mode_and_summarize()
                asyncio.create_task(_auto_exit())
        except Exception as e:
            logger.error(f"[SILENCE EXIT] Handler error: {e}")

    await session.start(
        agent=agent,
        room=ctx.room
    )

# Main entry point
def main():
    """Main function for running discharge workflow"""
    import sys
    # Environment variables are loaded in discharge.config module
    
    # Health endpoint is started by `agent/main.py` in non-console mode
    
    try:
        # Handle console mode vs production mode
        if is_console_mode():
            print("🎯 Starting PostOp AI Discharge Workflow in Console Mode")
            # Check for required OpenAI key
            if not os.getenv("OPENAI_API_KEY"):
                print("❌ Console mode requires OPENAI_API_KEY. Exiting...")
                sys.exit(1)
            
            cli.run_app(WorkerOptions(
                agent_name=LIVEKIT_AGENT_NAME,
                entrypoint_fnc=console_entrypoint,
                drain_timeout=60  # 60 seconds for faster Fly.io deployments
            ))
        else:
            print("🚀 Starting PostOp AI Discharge Workflow in Production Mode")
            # Production mode - check for required keys
            if not os.getenv("OPENAI_API_KEY"):
                print("❌ Production mode requires OPENAI_API_KEY. Exiting...")
                sys.exit(1)
            # Check for ElevenLabs API key
            if not os.getenv("ELEVEN_API_KEY"):
                print("⚠️ ELEVEN_API_KEY not set, using OpenAI TTS...")
                
            cli.run_app(WorkerOptions(
                agent_name=LIVEKIT_AGENT_NAME,
                entrypoint_fnc=production_entrypoint,
                drain_timeout=60  # 60 seconds for faster Fly.io deployments
            ))
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Health endpoint is managed by `agent/main.py`
        pass

if __name__ == "__main__":
    main()