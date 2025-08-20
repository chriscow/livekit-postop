from livekit.agents import Agent, RunContext, function_tool
from livekit.plugins import deepgram, openai, silero
from shared import get_job_context
from .agents import DischargeAgent, SessionData, is_console_mode, create_tts_provider
from .config import AGENT_NAME

import logging

logger = logging.getLogger("postop-agent")

class ConsentCollector(Agent):
    """Agent that collects recording consent before proceeding"""
    
    def __init__(self):
        super().__init__(
            instructions="You are a voice AI agent with the singular task to collect positive recording consent from the user. If consent is not given, you must end the call.",
            stt=deepgram.STT(model="nova-3", language="multi"),
            llm=openai.LLM(model="gpt-4.1"),
            tts=create_tts_provider(),
            vad=silero.VAD.load()
        )

    async def on_enter(self) -> None:
        await self.session.say(f"Hi there! I'm {AGENT_NAME} from PostOp AI. I'm here to help make sure the patient gets all their discharge instructions and follow-up reminders. May I record this call so I have accurate discharge instructions to refer to in the future?")

    @function_tool
    async def on_consent_given(self, ctx: RunContext[SessionData]):
        """Use this tool to indicate that consent has been given and the call may proceed."""
        # Update session data with consent
        ctx.userdata.consent_given = True
        
        # Perform a handoff, immediately transferring control to the new agent
        # Pass chat context to maintain conversation continuity
        return DischargeAgent(chat_ctx=self.session.chat_ctx)

    @function_tool
    async def end_call(self) -> None:
        """Use this tool to indicate that consent has not been given and the call should end."""
        await self.session.say("No problem! Without recording, I can't help with this process. Feel free to contact the folks here directly for post operative support.")
        
        # In console mode, there's no real room to delete
        if is_console_mode():
            logger.info("Console mode: Call ended due to no consent - exiting gracefully")
            # In console mode, just return - the session will end naturally
            return
        
        # In production mode, delete the room to end the call
        try:
            job_ctx = get_job_context()
            await job_ctx.api.room.delete_room(api.DeleteRoomRequest(room=job_ctx.room.name))
            logger.info("Production mode: Room deleted due to no consent")
        except Exception as e:
            logger.error(f"Failed to delete room: {e}")
            # Continue anyway - the important part is that consent was declined

