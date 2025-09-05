import asyncio
import time
from types import SimpleNamespace

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.llm import ChatContext, ChatMessage, StopResponse, function_tool
from livekit.plugins import deepgram, openai, silero


class MinimalPassiveAgent(Agent):
    def __init__(self) -> None:
        instructions = (
            "You are a minimal passive-mode test agent.\n"
            "Use start_passive_listening to enter passive mode and exit_passive_listening to exit.\n"
            "While in passive mode, remain completely silent and do not generate replies.\n"
        )
        super().__init__(
            instructions=instructions,
            stt=deepgram.STT(model="nova-3", language="multi"),
            llm=openai.LLM(model="gpt-4.1"),
            tts=openai.TTS(voice="shimmer"),
            vad=silero.VAD.load(),
        )
        self._tts_suppressed = False

    async def on_enter(self) -> None:
        # Simple intro for manual testing
        session_id = f"mini_{int(time.time())}"
        self.session.userdata.session_id = session_id
        await self.session.say(
            "Minimal passive agent ready. Use the start_passive_listening tool to begin passive mode."
        )

    @function_tool()
    async def start_passive_listening(self, ctx):
        ctx.userdata.is_passive_mode = True
        self._tts_suppressed = True
        return "Entering passive mode (silent)."

    @function_tool()
    async def exit_passive_listening(self, ctx):
        if not getattr(ctx.userdata, "is_passive_mode", False):
            return "Not in passive mode."
        ctx.userdata.is_passive_mode = False
        self._tts_suppressed = False
        await ctx.session.say("Exited passive mode.")
        return "Exited passive mode."

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        is_passive = getattr(self.session.userdata, "is_passive_mode", False)
        text = new_message.text_content or ""
        if is_passive:
            # Stay silent unconditionally in passive
            self._tts_suppressed = True
            # Simple manual exit triggers for convenience
            lower = text.lower()
            if any(p in lower for p in ["stop listening", "exit passive", "we're done", "that's all"]):
                self.session.userdata.is_passive_mode = False
                self._tts_suppressed = False
                await self.session.say("Okay, exiting passive mode now.")
                raise StopResponse()
            raise StopResponse()
        else:
            self._tts_suppressed = False


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    # Minimal userdata with just our flag and session_id
    userdata = SimpleNamespace(is_passive_mode=False, session_id=f"mini_{int(time.time())}")

    session = AgentSession(userdata=userdata)
    agent = MinimalPassiveAgent()

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        agent_name="minimal-passive-agent",
        entrypoint_fnc=entrypoint,
        drain_timeout=60,
    )) 