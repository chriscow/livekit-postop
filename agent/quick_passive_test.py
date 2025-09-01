#!/usr/bin/env python3
"""
Quick test of passive mode improvements
"""

import asyncio
from dataclasses import dataclass, field
from typing import List
from livekit.agents import AgentSession  
from livekit.plugins import openai
from discharge.agents import DischargeAgent

@dataclass
class TestSessionData:
    """Test session userdata matching what DischargeAgent expects"""
    session_id: str = "test-session-001"
    workflow_mode: str = "normal"
    is_passive_mode: bool = False
    patient_name: str = "Test Patient"
    collected_instructions: List[str] = field(default_factory=list)

async def test_simple_exit():
    """Quick test of exit detection"""
    print("🧪 Quick Passive Mode Exit Test")
    print("=" * 40)
    
    # Initialize without STT/TTS for pure text testing
    async with openai.LLM(model="gpt-4o-mini") as llm:
        # Create text-only session without audio plugins
        session = AgentSession[TestSessionData](
            llm=llm,
            userdata=TestSessionData(session_id="quick-test-001")
            # No STT/TTS - pure text mode
        )
        
        async with session:
            # Initialize agent without audio components
            agent = DischargeAgent()  
            
            # Start agent in text-only mode
            await session.start(agent)
            print("✅ Agent started")
            
            # Test 1: Initialize passive mode
            print("\n1️⃣ Testing passive mode initialization...")
            result1 = await session.run(user_input="I'm ready for discharge instructions")
            
            events = []
            try:
                while True:
                    event = result1.expect.next_event()
                    if event.is_message(role="assistant"):
                        msg = await event.get_message()
                        events.append(f"Message: {msg.content}")
                    elif event.is_function_call():
                        call = await event.get_function_call()
                        events.append(f"Function: {call.name}")
                    else:
                        break
            except:
                pass
                
            print(f"   Events: {len(events)}")
            for event in events[:3]:  # Show first 3
                print(f"   - {event}")
                
            # Test 2: Try direct Maya address 
            print("\n2️⃣ Testing Maya address (should exit)...")
            result2 = await session.run(user_input="Maya, did you get that?")
            
            events2 = []
            exit_detected = False
            try:
                while True:
                    event = result2.expect.next_event()
                    if event.is_message(role="assistant"):
                        msg = await event.get_message()
                        events2.append(f"Message: {str(msg.content)[:100]}")
                        # Look for exit indicators
                        if any(word in str(msg.content).lower() for word in ["here are", "summary", "captured", "instructions"]):
                            exit_detected = True
                    elif event.is_function_call():
                        call = await event.get_function_call()
                        events2.append(f"Function: {call.name}")
                        if call.name == "provide_instruction_summary":
                            exit_detected = True
                    else:
                        break
            except:
                pass
                
            print(f"   Events: {len(events2)}")
            for event in events2[:3]:  # Show first 3  
                print(f"   - {event}")
            print(f"   Exit detected: {'✅ YES' if exit_detected else '❌ NO'}")
            
            print(f"\n📊 Test Results:")
            print(f"   - Agent started: ✅")
            print(f"   - Passive mode init: {'✅' if len(events) > 0 else '❌'}")
            print(f"   - Maya exit detection: {'✅' if exit_detected else '❌'}")

if __name__ == "__main__":
    asyncio.run(test_simple_exit())