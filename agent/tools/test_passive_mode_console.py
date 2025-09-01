#!/usr/bin/env python3
"""
Interactive console testing for discharge agent passive listening mode.
Use this for manual testing and debugging without phone calls.
"""

import asyncio
import sys
from datetime import datetime
from typing import List, Dict

# Add project root to path
sys.path.append('.')

def print_banner():
    """Print testing banner"""
    print("🧪 Discharge Agent Passive Mode Console Tester")
    print("=" * 60)
    print("This tool lets you test passive mode exit detection with text input")
    print("Commands:")
    print("  'quit' or 'exit' - Exit the tester")
    print("  'reset' - Reset the conversation")
    print("  'status' - Show current agent state")
    print("  'scenario X' - Run predefined scenario (1-7)")
    print("  Anything else - Send as user input to agent")
    print("=" * 60)

class MockSessionData:
    """Mock session data for testing"""
    def __init__(self):
        self.session_id = f"console_test_{int(datetime.now().timestamp())}"
        self.patient_name = "Test Patient"
        self.patient_language = "English"
        self.workflow_mode = "passive_listening"
        self.is_passive_mode = True
        self.collected_instructions = []
        self.instructions_map = {}
        self._exiting_passive = False

class MockRunContext:
    """Mock run context for testing"""
    def __init__(self, userdata):
        self.userdata = userdata
        
    class MockSession:
        async def say(self, message):
            print(f"🗣️  MAYA: {message}")
            
        async def generate_reply(self, instructions=None):
            if instructions:
                print(f"🧠 MAYA (thinking): {instructions[:100]}...")
            return type('obj', (object,), {'text_content': 'Generated response'})
    
    def __init__(self, userdata):
        self.userdata = userdata
        self.session = self.MockSession()

class MockChatMessage:
    """Mock chat message for testing"""
    def __init__(self, text):
        self.text_content = text

class ConsoleTester:
    """Console-based tester for passive mode"""
    
    def __init__(self):
        self.session_data = None
        self.agent = None
        self.conversation_history = []
        self.scenarios = self._create_scenarios()
        self.reset_session()
        
    def _create_scenarios(self):
        """Create quick test scenarios"""
        return {
            1: [
                "Take these pills twice daily with food",
                "Change bandages every 2 days", 
                "Maya, did you get all that?"
            ],
            2: [
                "No heavy lifting for 2 weeks",
                "Take ibuprofen for pain as needed",
                "That's all for now. Any questions?"
            ],
            3: [
                "Keep the wound dry",
                "Call if fever over 101",
                "Good luck with recovery!"
            ],
            4: [
                "Take antibiotics for 7 days",
                "No swimming until cleared",
                "Did you capture everything?"
            ],
            5: [
                "Hello there", 
                "How are you feeling?",
                "Let's start with your instructions"
            ],
            6: [
                "Take Lisinopril 10mg daily",
                "Monitor blood pressure weekly", 
                "Avoid NSAIDs",
                "Follow up in 2 weeks",
                "Call if dizziness occurs",
                "That covers everything!"
            ],
            7: [
                "Take your medication",
                "I need to step out briefly"
            ]
        }
    
    def reset_session(self):
        """Reset the test session"""
        self.session_data = MockSessionData()
        self.conversation_history = []
        
        try:
            from discharge.agents import DischargeAgent
            self.agent = DischargeAgent()
            print("✅ Agent loaded successfully")
        except ImportError:
            print("⚠️ Could not import DischargeAgent - using mock")
            self.agent = None
    
    def show_status(self):
        """Show current agent state"""
        print(f"\n📊 Current State:")
        print(f"   Session ID: {self.session_data.session_id}")
        print(f"   Passive Mode: {self.session_data.is_passive_mode}")
        print(f"   Instructions Collected: {len(self.session_data.collected_instructions)}")
        print(f"   Conversation Turns: {len(self.conversation_history)}")
        
        if self.agent:
            tts_suppressed = getattr(self.agent, '_tts_suppressed', False)
            print(f"   TTS Suppressed: {tts_suppressed}")
        
        if self.session_data.collected_instructions:
            print(f"\n📝 Collected Instructions:")
            for i, inst in enumerate(self.session_data.collected_instructions, 1):
                if isinstance(inst, dict):
                    print(f"   {i}. [{inst.get('type', 'general')}] {inst.get('text', inst)}")
                else:
                    print(f"   {i}. {inst}")
        print()
    
    async def process_input(self, user_input: str) -> Dict:
        """Process user input through the agent"""
        
        if not self.agent:
            return {
                "response": "Agent not available - using mock response",
                "exit_detected": "Maya" in user_input.lower() or "questions" in user_input.lower(),
                "tts_suppressed": self.session_data.is_passive_mode
            }
        
        # Create mock objects
        mock_ctx = MockRunContext(self.session_data)
        mock_message = MockChatMessage(user_input)
        
        # Store state before processing
        was_passive = self.session_data.is_passive_mode
        instructions_before = len(self.session_data.collected_instructions)
        
        try:
            # Process through agent's on_user_turn_completed
            await self.agent.on_user_turn_completed(None, mock_message)
            
            # Check state changes
            is_passive_now = self.session_data.is_passive_mode
            tts_suppressed = getattr(self.agent, '_tts_suppressed', False)
            exit_detected = was_passive and not is_passive_now
            
            self.conversation_history.append({
                "input": user_input,
                "was_passive": was_passive,
                "is_passive_now": is_passive_now,
                "exit_detected": exit_detected,
                "tts_suppressed": tts_suppressed,
                "timestamp": datetime.now().isoformat()
            })
            
            return {
                "exit_detected": exit_detected,
                "tts_suppressed": tts_suppressed,
                "instructions_collected": len(self.session_data.collected_instructions) - instructions_before
            }
            
        except Exception as e:
            print(f"❌ Error processing input: {e}")
            return {"error": str(e)}
    
    async def run_scenario(self, scenario_num: int):
        """Run a predefined scenario"""
        if scenario_num not in self.scenarios:
            print(f"❌ Scenario {scenario_num} not found")
            return
            
        print(f"\n🎬 Running Scenario {scenario_num}")
        scenario = self.scenarios[scenario_num]
        
        for i, input_text in enumerate(scenario):
            print(f"\n📝 Turn {i+1}: {input_text}")
            result = await self.process_input(input_text)
            
            if result.get("exit_detected"):
                print("🚪 EXIT DETECTED!")
                print(f"   TTS Suppressed: {result.get('tts_suppressed', False)}")
                break
            else:
                print(f"👂 Still listening (TTS: {'suppressed' if result.get('tts_suppressed') else 'active'})")
        
        self.show_status()
    
    async def interactive_loop(self):
        """Main interactive testing loop"""
        
        while True:
            try:
                user_input = input("\n💬 Enter input (or 'help'): ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() in ['quit', 'exit']:
                    print("👋 Goodbye!")
                    break
                    
                elif user_input.lower() == 'help':
                    print_banner()
                    continue
                    
                elif user_input.lower() == 'reset':
                    self.reset_session()
                    print("🔄 Session reset")
                    continue
                    
                elif user_input.lower() == 'status':
                    self.show_status()
                    continue
                    
                elif user_input.lower().startswith('scenario '):
                    try:
                        scenario_num = int(user_input.split()[1])
                        await self.run_scenario(scenario_num)
                    except (IndexError, ValueError):
                        print("❌ Usage: scenario <number> (1-7)")
                    continue
                
                # Process regular input
                print(f"📨 Processing: '{user_input}'")
                result = await self.process_input(user_input)
                
                if result.get("exit_detected"):
                    print("🎉 EXIT DETECTED! Agent should now provide summary.")
                elif result.get("tts_suppressed"):
                    print("🤫 Still in passive mode - response suppressed")
                else:
                    print("💬 Normal mode - agent can respond")
                
                if result.get("instructions_collected", 0) > 0:
                    print(f"📝 Collected {result['instructions_collected']} new instructions")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

async def main():
    """Main entry point"""
    print_banner()
    
    tester = ConsoleTester()
    
    print(f"\n🚀 Ready for testing!")
    print(f"Current state: Passive mode = {tester.session_data.is_passive_mode}")
    print(f"Try scenario 1-7, or type your own discharge instruction text.")
    
    await tester.interactive_loop()

if __name__ == "__main__":
    asyncio.run(main())