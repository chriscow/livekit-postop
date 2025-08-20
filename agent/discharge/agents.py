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
from .config import AGENT_NAME, LIVEKIT_AGENT_NAME, POSTOP_VOICE_ID
# Removed unused imports
from shared import RedisMemory, prompt_manager

logger = logging.getLogger("postop-agent")


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
    
    def __post_init__(self):
        if self.collected_instructions is None:
            self.collected_instructions = []
        if self.room_people is None:
            self.room_people = []
    


class DischargeAgent(Agent):
    """Initial agent that handles patient setup and routing to appropriate workflow"""
    
    def __init__(self, chat_ctx=None):
        """
        Initialize Discharge Agent
        
        Args:
            chat_ctx: Chat context from previous agent (for conversation continuity)
        """


        # Load initial discharge agent instructions from YAML
        # instructions = prompt_manager.load_prompt(
        #     "discharge_initial",
        #     agent_name=AGENT_NAME
        # )

        instructions = """
You are Maya, an AI medical translation and discharge support specialist. Your goal is to bridge communication gaps between healthcare providers and patients/families who have language barriers, then provide ongoing post-discharge support.

**FUNDAMENTAL RULE:** ALWAYS speak to doctors and healthcare providers in English. ONLY speak to patients/families in their native language when translation is needed.

**PASSIVE LISTENING MODE:**
- If everyone in the consultation speaks English, enter passive listening mode immediately
- Stay completely silent during the consultation, only listening and collecting discharge instructions
- Exit passive listening mode when:
  * Someone says your name ("Maya", "Hey Maya", "Maya, are you listening?")
  * Translation is requested ("Can you translate?", "What did they say?")
  * Doctor indicates completion ("That's all", "Any questions?", "We're done", "Maya, did you get all that?")
  * Someone asks if you captured everything or needs clarification
  * There's a long pause and someone seems to be waiting for your response

**TRANSLATION MODE:**
- If translation is required, temporarily exit passive listening mode to perform translations
- After completing translations and ensuring all non-English questions are answered by the doctor, return to passive listening mode
- **CRITICAL:** The doctor must answer all medical questions - you only translate, never provide medical advice

Follow this specific interaction structure:

1. Initial Introduction and Role Clarification

When introduced by the doctor:
- Assess if translation is needed based on languages spoken in the room
- If everyone speaks English: "I'll listen quietly to collect discharge instructions for follow-up support."
- If translation needed, introduce yourself naturally: "Hello [patient family names], I'm Maya. I'm going to help with translating Dr. [Doctor's name]'s instructions about [patient's name]'s care." Then to doctor IN ENGLISH: "Dr. [name], you can go ahead with your instructions. I'll translate as needed."

2. Passive Listening (English-only consultations)

During English consultations:
- Enter passive listening mode immediately using start_passive_listening()
- Stay completely silent and collect all discharge instructions
- Use exit_passive_listening() when you detect any of the exit conditions listed above
- After exiting to respond, you can return to passive listening using start_passive_listening() if the consultation continues

3. Translation Mode (Multi-language consultations)

When translation is needed:
- Speak naturally as if you're physically present in the room
- Address people directly by name: "Maria, el Dr. Shah dice que..."
- When translating to doctor: "Dr. Shah, Maria está preguntando si..."
- **CRITICAL:** Always speak to Dr. Shah in English, regardless of the patient's language
- **CRITICAL:** Only speak to the patient/family in their native language (Spanish, etc.)
- **NEVER answer medical questions yourself - always let the doctor respond first**
- Speak conversationally without formal prefixes like "[To Maria:]"

4. Question Handling Protocol

**CRITICAL RULE:** All medical questions must be answered by the doctor first.

When family asks medical questions:
- Translate to doctor IN ENGLISH: "Dr. [name], [family member] is asking: [clear translation]"
- Wait for doctor's complete response
- Translate back to family IN THEIR LANGUAGE: "[Family member name], el doctor dice que..."
- Never provide medical advice or answers without the doctor's input

5. Post-Consultation Follow-Up Setup

After doctor completes consultation, speak naturally to patient family in their language:
- "I'm going to send you a complete summary of the instructions in about 10 minutes."
- "During [patient name]'s recovery, I'm going to contact you daily with reminders."
- "You can communicate with me whenever you want, but for medical questions I'll connect you with the clinic."

Then ask the doctor if there is anything else they would like to add.


**CRITICAL SAFETY PROTOCOLS:**
- **NEVER provide medical advice or answers without doctor's input**
- If unsure about any translation, ask the doctor for clarification immediately
- Always let the doctor answer medical questions first, then translate their response
- Document all interactions for medical team review
- Never contradict or modify doctor's instructions - only translate and clarify

**IMPORTANT OPERATIONAL RULES:**
- Use start_passive_listening() for English-only consultations
- Use exit_passive_listening() when you detect any of these triggers:
  * Your name is mentioned ("Maya")
  * Translation is requested
  * Doctor indicates they're finished
  * Someone asks if you captured everything
  * Long pause where someone seems to be waiting for you
- After responding, return to passive listening with start_passive_listening() if the consultation continues
- The doctor must answer all medical questions - you are a translation bridge, not a medical advisor

Continue providing translation and support services following this structure, always prioritizing patient safety and ensuring the doctor provides all medical guidance.
"""

        if is_console_mode():
            tts = openai.TTS(voice="shimmer")
        else:
            # Use Hume for production
            tts = hume.TTS(
                voice=hume.VoiceById(id=POSTOP_VOICE_ID),
                description="Middle-age black woman, clear Atlanta accent, that exudes warmth, care and confidence. Speaks at a measured pace and is conversational - like a friend, a caring nurse, or your mother."
            )
            
        # Initialize agent with services
        super().__init__(
            instructions=instructions,
            chat_ctx=chat_ctx,
            stt=deepgram.STT(model="nova-3", language="multi"),
            llm=openai.LLM(model="gpt-4.1"),
            tts=tts,
            vad=silero.VAD.load()
        )
        
        # Agent state (Redis memory for persistence)
        self.memory = RedisMemory()
        
        # Redis client for conversation logging
        import redis
        import os
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        
        # Override session.say to log all outgoing messages
        self._original_say = None
        self._original_generate_reply = None
        
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
                    logger.info(f"[CONVERSATION ITEM] Session: {session_id} | Role: {event.item.role} | Text: '{response_text}'")
                    print(f"[CONVERSATION LOG] Session: {session_id} | MAYA CONVERSATION: '{response_text}'")
                    
                    # Store conversation in Redis
                    self._log_conversation_message(session_id, "assistant", response_text)
        
        await self.session.say("Hi all! I'm Maya, thanks for dialing me in today. So Dr. Shah, who do we have in the room today?")
        
    async def _logged_say(self, message: str):
        """Wrapper for session.say that logs all outgoing messages"""
        session_id = getattr(self.session.userdata, 'session_id', 'unknown')
        logger.info(f"[LLM OUTPUT] Session: {session_id} | Text: '{message}'")
        print(f"[CONVERSATION LOG] Session: {session_id} | MAYA OUTPUT: '{message}'")
        
        # Store conversation in Redis
        self._log_conversation_message(session_id, "assistant", message)
        
        # Call original say method
        return await self._original_say(message)

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

    # Workflow Transition Functions
    @function_tool
    async def start_passive_listening(self, ctx: RunContext[SessionData]):
        """Enter passive listening mode for instruction collection"""
        ctx.userdata.workflow_mode = "passive_listening"
        ctx.userdata.is_passive_mode = True
        logger.info(f"Entering passive listening mode for session: {ctx.userdata.session_id}")
        
        # Also store in memory for persistence
        self.memory.store_session_data(ctx.userdata.session_id, "workflow_mode", "passive_listening")
        self.memory.store_session_data(ctx.userdata.session_id, "is_passive_mode", True)
        
        intro_message = f"Got it, I'll listen quietly while you go through {ctx.userdata.patient_name}'s instructions."
        return None, intro_message
    
    @function_tool()
    async def exit_passive_listening(self, ctx: RunContext):
        """Call this function when:
        1. Addressed directly by name ("Maya", "Hey Maya", "Maya, are you listening?")
        2. Asked for translation ("Can you translate this?", "What did they say?")
        3. Doctor indicates they're finished ("That's all", "Any questions?", "We're done", "We're all set", "Maya, did you get all that?")
        4. Someone asks if you captured everything or needs clarification
        
        After exiting, you can return to passive listening if the consultation continues and no further translation is needed."""
        is_passive_mode = getattr(ctx.userdata, 'is_passive_mode', False)
        print(f"[DEBUG] exit_passive_listening called. is_passive_mode: {is_passive_mode}")
        print(f"[DEBUG] Current transcript buffer size: {len(getattr(self, 'transcript_buffer', []))}")
        
        if not is_passive_mode:
            return "Not currently in passive listening mode"
            
        ctx.userdata.is_passive_mode = False
        if hasattr(self, '_agent_session') and self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
            
        # If no transcripts captured, provide a fallback message
        transcript_buffer = getattr(self, 'transcript_buffer', [])
        if len(transcript_buffer) == 0:
            await ctx.session.generate_reply(
                instructions="The transcript buffer is empty. Say: 'I'm sorry, I didn't capture any discharge instructions during passive listening. Could you please repeat the key points you covered, or would you like me to ask specific questions about the discharge orders?'"
            )
            return "No transcripts captured during passive listening"
        else:
            # await self.trigger_review(ctx)  # TODO: Implement trigger_review method
            await ctx.session.generate_reply(
                instructions="Provide a summary of collected discharge instructions and ask if anything is missing."
            )
            return "Exited passive listening mode and provided summary"
        
    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Handle user speech completion - control response based in passive mode"""
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
        
        if is_passive_mode:
            # During passive listening, process the speech but don't generate automatic responses
            print(f"[DEBUG] Processing passive transcript: '{transcript_text}'")

            # Check if being directly addressed for translation
            # if self._is_translation_request(transcript_text):
            #     print("[DEBUG] Translation request detected, exiting passive mode")
            #     logger.info(f"[WORKFLOW] Session: {session_id} | Translation request detected, exiting passive mode")
            #     # Don't raise StopResponse - let the agent respond to the translation request
            #     # await self._handle_translation_request(turn_ctx, transcript_text)
            #     return
            
            # Store instruction silently
            # await self._store_instruction_silently(transcript_text)

            # Prevent automatic response by raising StopResponse
            raise StopResponse()

        # Normal mode - let the agent respond automatically
        # (default behavior continues)


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
        userdata=SessionData()
    )

    ## CLAUDE: STOP CHANGING THIS TO THE ConsentCollector
    agent = DischargeAgent()
    
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
        userdata=SessionData()
    )
    agent = DischargeAgent()  # Uses ElevenLabs TTS in production
    
    await session.start(
        agent=agent,
        room=ctx.room
    )


# Main entry point
def main():
    """Main function for running discharge workflow"""
    from dotenv import load_dotenv
    import sys
    
    load_dotenv()
    
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