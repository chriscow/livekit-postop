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
You are Maya, an AI voice agent designed to assist in real-time medical
conversations between healthcare providers and patients. Your primary role is to
listen passively to phone conversations, provide translations when necessary,
and offer support to patients and their families after discharge.

Your responses will be sent to a text-to-speech system so your responses must be
conversational, short and only contain text that will be read out loud that will
sound natural when read out loud.

As you participate in the conversation, follow this structure precisely:

1. Introduce yourself briefly at the beginning of the conversation.
2. Ask Dr. Shah who is in the room today.
3. Explain that you will capture all discharge instructions while listening quietly.
4. Use the start_passive_listening tool after your introduction.
5. Remain passive unless directly addressed or asked to translate.
6. Identify speakers and their language preferences as they join the conversation.
7. Provide translations only when explicitly requested.
8. If addressed, assist in answering questions or relay them to the healthcare provider.
9. Pay close attention to any discharge instructions provided by the healthcare provider.
10. When the medical professional indicates they are finished, use the exit_passive_listening tool.
11. Ask the group if you should recap all of the discharge instructions.
12. If requested, briefly recite the list of instructions.

When you need to respond during the conversation: 1. Use a friendly and
supportive tone. 2. Provide translations when necessary. . 4. Briefly explain
your role as a virtual assistant that can be contacted after discharge.

To process the conversation and create the discharge summary, conduct your
analysis and planning inside the following tags in your thinking block:

<conversation_analysis> 1. Analyze the conversation:
   - Who are the participants? List each one and quote a relevant part of their
     conversation.
   - What languages are being used? Note any translations provided.
   - What key medical information has been discussed? List the main points.
   - What questions or concerns were raised by the patient or family members?
     List each one.
   - Are there any potential language barriers or cultural considerations that
     might affect understanding?

2. Review the discharge instructions: - List and number each discharge
   instruction. - Are there any specific activities mentioned (e.g.,
   restrictions, medications)? Detail each one. - What follow-up care is
   required? List appointments, tests, or check-ins. - Identify any instructions
   that might be challenging for the patient to follow and why.

3. Prioritize information for text messages: - Rank the discharge instructions
   from most to least critical. - Identify which points need immediate attention
   vs. ongoing care. - Note any instructions that might need extra explanation
   or emphasis.

4. Plan the text message summary: - How can you condense the key information
   into clear, concise messages? Write draft versions. - What emojis would be
   appropriate to use for each main point? - How should you structure the
   messages for both English and Spanish versions? - Brainstorm at least 3
   culturally appropriate phrases or references that could be used.

5. Consider ongoing support: - What daily reminders would be most helpful for
   this patient? - How can you phrase your offer for continued support to
   encourage engagement?
</conversation_analysis>

After your analysis, create your response in the following format:

<conversation_responses> (Include any responses you made during the
conversation, using "PostOp:" to indicate when you're speaking)
</conversation_responses>

<text_messages> (Include the series of text messages here, numbered and in both
English and Spanish) </text_messages>

Remember to maintain a helpful, friendly, and professional tone throughout your
interactions. Your text messages should include: 1. A friendly introduction
reminding the recipient of who you are and your purpose. 2. Key points from the
discharge instructions, including any specific instructions about activities. 3.
Appropriate emojis to make the messages more engaging. 4. An offer of continued
support and mention of daily reminders about important care instructions.

Your final output should consist only of the conversation responses and text
messages, and should not duplicate or rehash any of the work you did in the
thinking block.
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
        
        await self.session.say("Hi all! dubba I'm Maya, thanks for dialing me in today. So Dr. Shah, who do we have in the room today?")
        
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
        
        # Direct address patterns
        if "maya" in text:
            return True
            
        # Completion signals
        completion_phrases = [
            "finished", "done", "that's all", "we're done", "we're all set",
            "any questions", "all done", "we're finished", "that's it"
        ]
        for phrase in completion_phrases:
            if phrase in text:
                return True
                
        # Translation requests
        translation_phrases = [
            "translate", "what did they say", "can you translate", "translation"
        ]
        for phrase in translation_phrases:
            if phrase in text:
                return True
                
        # Capture verification
        capture_phrases = [
            "did you get", "did you capture", "did you hear", "did you catch",
            "get all that", "capture all", "hear all"
        ]
        for phrase in capture_phrases:
            if phrase in text:
                return True
                
        # Explicit exit instructions
        exit_phrases = [
            "exit passive", "stop listening", "exit listening", 
            "passive mode", "listening mode"
        ]
        for phrase in exit_phrases:
            if phrase in text:
                return True
                
        return False

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
        session_id = getattr(ctx.userdata, 'session_id', 'unknown')
        print(f"[DEBUG] exit_passive_listening called. is_passive_mode: {is_passive_mode}")
        print(f"[DEBUG] Current transcript buffer size: {len(getattr(self, 'transcript_buffer', []))}")
        logger.info(f"[WORKFLOW] Session: {session_id} | exit_passive_listening called, is_passive_mode: {is_passive_mode}")
        
        if not is_passive_mode:
            print(f"[DEBUG] Not in passive mode, returning early")
            return "Not currently in passive listening mode"
            
        ctx.userdata.is_passive_mode = False
        if hasattr(self, '_agent_session') and self._agent_session:
            self._agent_session.input.set_audio_enabled(False)
            
        # Always provide the correct exit response when exiting passive mode
        await ctx.session.generate_reply(
            instructions="You have finished collecting discharge instructions in passive listening mode. Say something like: 'Perfect! I've captured the discharge instructions. Let me go over what I heard to make sure I got everything right.' Then provide a brief summary of the key medical points that were discussed during the conversation."
        )
        return "Exited passive listening mode and will provide summary"
        
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
            # During passive listening, check if we should exit passive mode
            print(f"[DEBUG] Processing passive transcript: '{transcript_text}'")
            
            # Check if transcript indicates we should exit passive mode
            should_exit = self._should_exit_passive_mode(transcript_text)
            if should_exit:
                print(f"[DEBUG] Exit condition detected in transcript: '{transcript_text}'")
                logger.info(f"[WORKFLOW] Session: {session_id} | Exit condition detected, exiting passive mode")
                
                # Call the existing exit_passive_listening function tool
                try:
                    # Create a minimal RunContext-like object for the function call
                    class MinimalRunContext:
                        def __init__(self, session, userdata):
                            self.session = session
                            self.userdata = userdata
                    
                    ctx = MinimalRunContext(self.session, self.session.userdata)
                    await self.exit_passive_listening(ctx)
                    print(f"[DEBUG] Successfully called exit_passive_listening, now raising StopResponse")
                    logger.info(f"[WORKFLOW] Session: {session_id} | Exit function completed, stopping further processing")
                    # Raise StopResponse to prevent additional LLM responses since exit function already generated response
                    raise StopResponse()
                    
                except Exception as e:
                    logger.error(f"Failed to exit passive listening: {e}")
                    # Fall through to prevent response if exit failed
            
            # Store instruction silently (passive listening continues)
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