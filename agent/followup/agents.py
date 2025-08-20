"""
Followup Agents for PostOp AI system

Contains agents for patient follow-up calls and reminders:
- FollowupAgent: Patient callback and reminder agent (legacy)
- ScheduledFollowupAgent: New agent for scheduled calls via CallScheduleItems
- patient_callback_entrypoint: Main entrypoint for patient callbacks
- scheduled_followup_entrypoint: New entrypoint for scheduled calls
"""
import json
import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, function_tool, RunContext, JobContext, WorkerOptions, cli
from livekit.plugins import openai, deepgram, elevenlabs, silero, noise_cancellation, hume

# Import configuration and utilities
from discharge.config import AGENT_NAME, LIVEKIT_AGENT_NAME, POSTOP_VOICE_ID
from shared import RedisMemory, prompt_manager

# Import scheduling components
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from scheduling.scheduler import CallScheduler
from discharge.discharge_orders import get_order_by_id
from discharge.medical_rag import MedicalRAGHandler

logger = logging.getLogger("postop-agent")


def is_console_mode():
    """Check if running in console mode"""
    return len(sys.argv) > 1 and sys.argv[1] == "console"


def create_tts_provider():
    """Create appropriate TTS provider based on mode"""
    if is_console_mode():
        return openai.TTS(voice="shimmer")
    else:
        # Use Hume for production
        return hume.TTS(
            voice=hume.VoiceById(id=POSTOP_VOICE_ID),
            description="Middle-age black woman, clear Atlanta accent, that exudes warmth, care and confidence. Speaks at a measured pace and is conversational - like a friend, a caring nurse, or your mother."
        )


class FollowupAgent(Agent):
    """Agent for patient follow-up calls with discharge reminders"""
    
    def __init__(self, callback_data: dict):
        self.callback_data = callback_data
        self.patient_phone = callback_data["patient_phone"]
        self.patient_language = callback_data["patient_language"]
        self.transcript_buffer = callback_data["transcript_buffer"]
        self.agent_name = callback_data["agent_name"]
        
        # Load followup instructions from YAML
        instructions = prompt_manager.load_prompt(
            "followup_instructions",
            agent_name=self.agent_name
        )
        
        super().__init__(instructions=instructions)

    @function_tool()
    async def provide_discharge_reminders(self, ctx: RunContext):
        """Provide personalized discharge instruction reminders to the patient"""
        if not self.transcript_buffer:
            await ctx.session.generate_reply(
                instructions="No specific discharge instructions were captured. Provide general post-operative care reminders and suggest they contact their healthcare provider for specific instructions."
            )
            return "No specific instructions available"
        
        # Analyze captured instructions to create personalized reminders
        instructions_text = " ".join([item["text"] for item in self.transcript_buffer])
        
        # Load reminder instructions from YAML
        reminder_instructions = prompt_manager.load_prompt(
            "reminder_template",
            instructions_text=instructions_text,
            patient_language=self.patient_language
        )
        
        await ctx.session.generate_reply(instructions=reminder_instructions)
        return "Provided personalized discharge reminders"

    @function_tool()
    async def answer_patient_question(self, ctx: RunContext, question: str):
        """Answer patient questions about their discharge instructions"""
        instructions_text = " ".join([item["text"] for item in self.transcript_buffer])
        
        await ctx.session.generate_reply(
            instructions=f"The patient asked: '{question}'. Based on the captured discharge instructions: '{instructions_text}', provide a helpful answer. If the question is beyond the scope of the captured instructions, advise them to contact their healthcare provider."
        )
        return f"Answered patient question: {question}"

    @function_tool()  
    async def end_patient_call(self, ctx: RunContext):
        """End the patient callback with caring closing"""
        await ctx.session.generate_reply(
            instructions="End the call warmly. Thank them for their time, remind them to follow their instructions, and encourage them to contact their healthcare provider with any concerns. Wish them a smooth recovery."
        )
        return "Patient callback completed"


class ScheduledFollowupAgent(Agent):
    """
    Enhanced agent for scheduled follow-up calls based on CallScheduleItems.
    Supports dynamic scheduling and discharge order reminders.
    """
    
    def __init__(self, call_item: CallScheduleItem, call_record: CallRecord):
        """
        Initialize with a CallScheduleItem that defines the call purpose
        
        Args:
            call_item: The scheduled call to execute
            call_record: Record to track call execution
        """
        self.call_item = call_item
        self.call_record = call_record
        self.scheduler = CallScheduler()
        
        # Initialize medical RAG handler
        try:
            self.medical_rag = MedicalRAGHandler(
                index_path="data/medical_rag",
                data_path="data/medical_rag/knowledge.pkl"
            )
            # Register medical RAG function tools with this agent
            self.medical_rag.register_with_agent(self)
            logger.info("Medical RAG handler initialized and registered")
        except Exception as e:
            logger.warning(f"Medical RAG handler not available: {e}")
            self.medical_rag = None
        
        # Use the call item's LLM prompt as the agent instructions
        super().__init__(instructions=call_item.llm_prompt)
        
        logger.info(f"Initialized ScheduledFollowupAgent for call {call_item.id}, type: {call_item.call_type.value}")
    
    @function_tool()
    async def end_call(self, ctx: RunContext):
        """End the follow-up call gracefully"""
        await ctx.session.generate_reply(
            instructions="End the call warmly. Thank the patient for their time, remind them to follow their discharge instructions, and encourage them to contact their healthcare provider with any concerns. Wish them a smooth recovery."
        )
        
        # Update call record
        self.call_record.ended_at = datetime.now()
        self.call_record.status = CallStatus.COMPLETED
        self.call_record.outcome_notes = "Call completed successfully by patient request"
        
        logger.info(f"Call {self.call_item.id} ended by patient request")
        return "Call ended successfully"
    
    @function_tool()
    async def detected_answering_machine(self, ctx: RunContext):
        """Handle when call reaches voicemail"""
        logger.info(f"Detected answering machine for call {self.call_item.id}")
        
        # Update call record
        self.call_record.ended_at = datetime.now()
        self.call_record.status = CallStatus.VOICEMAIL
        self.call_record.outcome_notes = "Call reached voicemail/answering machine"
        
        # Don't leave a message for now - just hang up
        return "Answering machine detected, ending call"
    
    @function_tool()
    async def schedule_reminder_call(self, ctx: RunContext, when: str, purpose: str):
        """
        Schedule an additional reminder call based on patient request
        
        Args:
            when: When to schedule the call (e.g., "tomorrow morning", "day before school")
            purpose: What the reminder call should accomplish
        """
        try:
            # Parse the "when" into a scheduled time
            from datetime import timedelta
            now = datetime.now()
            
            # Simple parsing - could be enhanced
            if "tomorrow" in when.lower():
                scheduled_time = now + timedelta(days=1)
                scheduled_time = scheduled_time.replace(hour=10, minute=0, second=0, microsecond=0)
            elif "day before" in when.lower():
                # Extract date from purpose or use a default
                scheduled_time = now + timedelta(days=6)  # Default to 6 days from now
                scheduled_time = scheduled_time.replace(hour=14, minute=0, second=0, microsecond=0)
            else:
                # Default to next day
                scheduled_time = now + timedelta(days=1)
                scheduled_time = scheduled_time.replace(hour=14, minute=0, second=0, microsecond=0)
            
            # Create new call item
            new_call = CallScheduleItem(
                patient_id=self.call_item.patient_id,
                patient_phone=self.call_item.patient_phone,
                scheduled_time=scheduled_time,
                call_type=CallType.FOLLOW_UP,
                priority=2,
                llm_prompt=f"You are calling to remind the patient: {purpose}. Be warm and helpful in your approach.",
                metadata={
                    "scheduled_by": "agent",
                    "original_call_id": self.call_item.id,
                    "requested_timing": when
                }
            )
            
            # Schedule the new call
            success = self.scheduler.schedule_call(new_call)
            
            if success:
                # Track in current call record
                self.call_record.additional_calls_scheduled.append(new_call.id)
                
                await ctx.session.generate_reply(
                    instructions=f"Confirm to the patient that you've scheduled a reminder call for {when} about {purpose}. Be reassuring and let them know they can always call their healthcare provider if they have urgent questions."
                )
                
                logger.info(f"Scheduled additional call {new_call.id} for {when}")
                return f"Scheduled reminder call for {when}"
            else:
                await ctx.session.generate_reply(
                    instructions="Apologize and let the patient know there was an issue scheduling the reminder. Suggest they contact their healthcare provider directly or set their own reminder."
                )
                return "Failed to schedule reminder call"
                
        except Exception as e:
            logger.error(f"Error scheduling reminder call: {e}")
            await ctx.session.generate_reply(
                instructions="Apologize and let the patient know there was an issue scheduling the reminder. Suggest they contact their healthcare provider directly."
            )
            return f"Error scheduling reminder: {str(e)}"
    
    @function_tool()
    async def get_discharge_order_details(self, ctx: RunContext):
        """
        Get detailed information about the related discharge order
        """
        if not self.call_item.related_discharge_order_id:
            return "No specific discharge order associated with this call"
        
        try:
            order = get_order_by_id(self.call_item.related_discharge_order_id)
            
            # Provide detailed information to help answer patient questions
            await ctx.session.generate_reply(
                instructions=f"The patient is asking about their discharge order: '{order.label}'. The full instructions are: '{order.discharge_order}'. Provide a clear, helpful explanation and answer any questions they have about these instructions."
            )
            
            return f"Provided details about {order.label}"
            
        except ValueError:
            logger.warning(f"Discharge order {self.call_item.related_discharge_order_id} not found")
            return "Discharge order details not available"
    
    @function_tool()
    async def record_patient_response(self, ctx: RunContext, question: str, response: str):
        """
        Record a patient's response to a specific question for tracking
        
        Args:
            question: The question that was asked
            response: The patient's response
        """
        self.call_record.patient_responses[question] = {
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Recorded patient response for call {self.call_item.id}: {question} -> {response}")
        return "Patient response recorded"


async def patient_callback_entrypoint(ctx: agents.JobContext, callback_key: str):
    """Entrypoint for patient callback calls"""
    # Retrieve callback data from Redis
    memory = RedisMemory()
    callback_data_json = memory.redis_client.get(callback_key)
    
    if not callback_data_json:
        print(f"[ERROR] No callback data found for key: {callback_key}")
        return
        
    callback_data = json.loads(callback_data_json)
    
    # Create patient-focused agent
    patient_agent = FollowupAgent(callback_data)
    
    # Set up patient call session
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM(model="gpt-4.1"),
        tts=create_tts_provider(),
        vad=silero.VAD.load(),
        turn_detection="vad",
    )
    
    await ctx.connect()
    
    # Start patient interaction
    await session.start(
        room=ctx.room,
        agent=patient_agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )
    
    # Begin with patient greeting
    await session.generate_reply(
        instructions=f"Say exactly: 'Hi! This is {callback_data['agent_name']} from PostOp AI. I'm calling to follow up on your recent procedure and remind you of your discharge instructions. Is this a good time to talk?'"
    )


async def scheduled_followup_entrypoint(ctx: agents.JobContext):
    """
    New entrypoint for scheduled follow-up calls based on CallScheduleItems.
    This is called by the LiveKit agent dispatch system for outbound calls.
    """
    logger.info(f"Starting scheduled followup call in room {ctx.room.name}")
    
    try:
        # Parse call metadata from the job
        if not ctx.job.metadata:
            logger.error("No call metadata provided in job")
            return
        
        call_metadata = json.loads(ctx.job.metadata)
        call_item_data = call_metadata.get("call_schedule_item")
        
        if not call_item_data:
            logger.error("No call_schedule_item in job metadata")
            return
        
        # Reconstruct CallScheduleItem from metadata
        call_item = CallScheduleItem.from_dict(call_item_data)
        
        # Create call record to track this execution
        call_record = CallRecord(
            call_schedule_item_id=call_item.id,
            patient_id=call_item.patient_id,
            started_at=datetime.now(),
            status=CallStatus.IN_PROGRESS,
            room_name=ctx.room.name,
            participant_identity="patient"
        )
        
        # Update call status in scheduler
        scheduler = CallScheduler()
        scheduler.update_call_status(call_item.id, CallStatus.IN_PROGRESS, "Call started")
        
        # Create the scheduled followup agent
        agent = ScheduledFollowupAgent(call_item, call_record)
        
        # Set up the session with telephony optimizations
        session = AgentSession(
            stt=deepgram.STT(model="nova-3", language="multi"),
            llm=openai.LLM(model="gpt-4o"),
            tts=create_tts_provider(),
            vad=silero.VAD.load(),
            turn_detection="vad",
        )
        
        await ctx.connect()
        
        # Start the agent session
        await session.start(
            room=ctx.room,
            agent=agent,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
        
        # Wait for participant to join (the patient answering the call)
        participant = await ctx.wait_for_participant(identity="patient")
        logger.info(f"Patient joined call {call_item.id}: {participant.identity}")
        
        # Begin the call with the agent's specific instructions
        # The agent's instructions are already set from call_item.llm_prompt
        await session.generate_reply()
        
        logger.info(f"Scheduled followup call {call_item.id} started successfully")
        
        # The session will continue until the call ends naturally
        # Call completion will be handled by the agent's function tools
        
    except Exception as e:
        logger.error(f"Error in scheduled followup call: {e}", exc_info=True)
        
        # Update call status to failed
        if 'call_item' in locals():
            scheduler = CallScheduler()
            scheduler.update_call_status(
                call_item.id, 
                CallStatus.FAILED, 
                f"Call execution failed: {str(e)}"
            )
            
            # Save error record
            if 'call_record' in locals():
                call_record.ended_at = datetime.now()
                call_record.status = CallStatus.FAILED
                call_record.error_message = str(e)
                call_record.outcome_notes = f"Call execution failed: {str(e)}"
                scheduler.save_call_record(call_record)


# Console mode entry point for followup workflow
def main():
    """Main function for running followup workflow"""
    from dotenv import load_dotenv
    import sys
    
    load_dotenv()
    
    # Handle console mode
    if is_console_mode():
        print("🎯 Starting PostOp AI Followup Workflow in Console Mode")
        
        # For followup, we need a callback key parameter
        print("📞 Followup workflow requires a callback key parameter")
        print("Usage: python followup_main.py console <callback_key>")
        
        # This is a simplified entrypoint - in practice you'd pass callback_key
        def console_entrypoint(ctx: JobContext):
            # This would need to be modified to handle callback keys properly
            return patient_callback_entrypoint(ctx, "demo_callback_key")
        
        cli.run_app(WorkerOptions(
            agent_name=f"{AGENT_NAME}-followup",
            entrypoint_fnc=console_entrypoint
        ))
    else:
        print("Production mode not implemented for followup workflow yet")
        sys.exit(1)


if __name__ == "__main__":
    main()