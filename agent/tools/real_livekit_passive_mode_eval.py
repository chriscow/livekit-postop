#!/usr/bin/env python3
"""
Real LiveKit Integration Test for Passive Mode Exit Detection
Uses actual LiveKit AgentSession and framework components - no mocking!
"""

import asyncio
import sys
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

# Add current directory to path for imports
sys.path.insert(0, '.')

from livekit.agents import AgentSession
from livekit.plugins import openai
from discharge.agents import DischargeAgent, SessionData

@dataclass
class PassiveModeTestCase:
    """Test case for passive mode evaluation"""
    name: str
    conversation: List[str]
    expected_exit_at: int  # Which turn should trigger exit (-1 if no exit expected)
    description: str
    expected_instructions_collected: int = 0

@dataclass 
class TestResult:
    """Result of a passive mode test"""
    test_name: str
    success: bool
    actual_exit_turn: int
    expected_exit_turn: int
    conversation_log: List[Dict]
    error_message: str = ""
    processing_time: float = 0.0

class RealLiveKitPassiveModeEvaluator:
    """Evaluates passive mode using real LiveKit components"""
    
    def __init__(self):
        self.test_cases = self._create_test_cases()
        self.results = []
        
    def _create_test_cases(self) -> List[PassiveModeTestCase]:
        """Create comprehensive test cases for passive mode evaluation"""
        
        return [
            PassiveModeTestCase(
                name="direct_maya_address",
                conversation=[
                    "Take these medications twice daily with food",
                    "Change the bandage every 2 days", 
                    "Maya, did you get all that?"
                ],
                expected_exit_at=2,
                description="Direct address by name should trigger exit",
                expected_instructions_collected=2
            ),
            
            PassiveModeTestCase(
                name="completion_phrase_any_questions",
                conversation=[
                    "No heavy lifting for 2 weeks",
                    "Take ibuprofen for pain as needed",
                    "Follow up in one week",
                    "That's all for the discharge instructions. Any questions?"
                ],
                expected_exit_at=3,
                description="Completion phrase 'any questions' should trigger exit",
                expected_instructions_collected=3
            ),
            
            PassiveModeTestCase(
                name="social_closing_good_luck",
                conversation=[
                    "Keep the incision dry for 48 hours",
                    "Call if you have fever over 101",
                    "Good luck with your recovery! Take care."
                ],
                expected_exit_at=2,
                description="Social closing should trigger exit",
                expected_instructions_collected=2
            ),
            
            PassiveModeTestCase(
                name="verification_request",
                conversation=[
                    "Take antibiotics for 7 days",
                    "No swimming until cleared by doctor", 
                    "Did you capture all the instructions?"
                ],
                expected_exit_at=2,
                description="Verification request should trigger exit",
                expected_instructions_collected=2
            ),
            
            PassiveModeTestCase(
                name="false_positive_greeting",
                conversation=[
                    "Hello everyone, thank you for being here",
                    "Good morning doctor",
                    "Let's begin with your instructions"
                ],
                expected_exit_at=-1,  # Should NOT exit
                description="Social greetings should NOT trigger exit",
                expected_instructions_collected=0
            ),
            
            PassiveModeTestCase(
                name="complex_multi_instruction",
                conversation=[
                    "Take Lisinopril 10mg once daily in the morning",
                    "Monitor your blood pressure twice weekly", 
                    "Avoid NSAIDs like ibuprofen while on this medication",
                    "Schedule follow-up in 2 weeks to check labs",
                    "Call immediately if you have dizziness or swelling",
                    "That covers everything. Feel better!"
                ],
                expected_exit_at=5,
                description="Complex multi-instruction scenario with natural ending",
                expected_instructions_collected=5
            ),
            
            PassiveModeTestCase(
                name="early_maya_interrupt",
                conversation=[
                    "Take your medication as prescribed",
                    "Maya, wait - I need to ask something"
                ],
                expected_exit_at=1,
                description="Early direct address should immediately trigger exit",
                expected_instructions_collected=1
            ),
            
            PassiveModeTestCase(
                name="incomplete_conversation",
                conversation=[
                    "Take your medication as prescribed",
                    "I need to check something, be right back"
                ],
                expected_exit_at=-1,  # Should NOT exit
                description="Incomplete conversation should continue passive listening",
                expected_instructions_collected=1
            ),
            
            PassiveModeTestCase(
                name="multiple_completion_signals", 
                conversation=[
                    "Take these pills with food",
                    "Change dressing daily",
                    "That's all for now",
                    "Any other questions?"
                ],
                expected_exit_at=2,  # Should exit on first completion signal
                description="Should exit on first completion signal, not wait for second",
                expected_instructions_collected=2
            ),
            
            PassiveModeTestCase(
                name="maya_with_translation_request",
                conversation=[
                    "Toma estos medicamentos dos veces al día",
                    "Maya, can you translate that for the patient?"
                ],
                expected_exit_at=1,
                description="Translation request with Maya address should trigger exit",
                expected_instructions_collected=1
            )
        ]
    
    async def run_single_test(self, test_case: PassiveModeTestCase, llm) -> TestResult:
        """Run a single test case using real LiveKit AgentSession"""
        
        print(f"\n🧪 Testing: {test_case.name}")
        print(f"   {test_case.description}")
        
        start_time = datetime.now()
        conversation_log = []
        actual_exit_turn = -1
        
        try:
            # Initialize session with proper userdata
            async with AgentSession[SessionData](
                llm=llm,
                userdata=SessionData()
            ) as session:
                # Initialize the real DischargeAgent
                discharge_agent = DischargeAgent()
                await session.start(discharge_agent)
                
                # First, get agent into passive listening mode by triggering start_passive_listening
                print(f"   Initializing passive mode...")
                init_result = await session.run(user_input="I'm ready to start passive listening for discharge instructions")
                
                # Process initialization events 
                try:
                    while True:
                        event = init_result.expect.next_event()
                        if event.is_message(role="assistant"):
                            msg = await event.get_message()
                            print(f"   Agent: {str(msg.content)[:100]}...")
                        elif event.is_function_call():
                            call = await event.get_function_call()
                            print(f"   Tool: {call.name}({call.arguments})")
                        else:
                            break
                except:
                    pass  # No more events
                
                print(f"   Passive mode initialized, starting test...")
                
                # Process each conversation turn
                for i, user_input in enumerate(test_case.conversation):
                    print(f"   Turn {i}: '{user_input[:50]}{'...' if len(user_input) > 50 else ''}'")
                    
                    # Send text input to agent using real LiveKit session
                    result = await session.run(user_input=user_input)
                    
                    # Collect conversation events
                    events = []
                    try:
                        while True:
                            event = result.expect.next_event()
                            if event.is_message(role="assistant"):
                                msg = await event.get_message()
                                events.append({
                                    "type": "message",
                                    "content": msg.content,
                                    "role": "assistant"
                                })
                                
                                # Check if this looks like an exit from passive mode
                                content_lower = str(msg.content).lower()
                                exit_indicators = [
                                    "here are the", "discharge instructions", "i captured",
                                    "let me read", "summary", "did you get", "i noted"
                                ]
                                
                                if any(indicator in content_lower for indicator in exit_indicators):
                                    if actual_exit_turn == -1:  # First exit detection
                                        actual_exit_turn = i
                                        print(f"   ✅ Exit detected at turn {i}")
                                
                            elif event.is_function_call():
                                call = await event.get_function_call()
                                events.append({
                                    "type": "function_call",
                                    "name": call.name,
                                    "arguments": call.arguments
                                })
                                
                            else:
                                break
                    except:
                        # No more events
                        break
                    
                    conversation_log.append({
                        "turn": i,
                        "user_input": user_input,
                        "agent_events": events,
                        "exit_detected": actual_exit_turn == i
                    })
                
                # Evaluate test success
                success = (actual_exit_turn == test_case.expected_exit_at)
                error_message = ""
                
                if not success:
                    if test_case.expected_exit_at >= 0:
                        error_message = f"Expected exit at turn {test_case.expected_exit_at}, got {actual_exit_turn}"
                    else:
                        error_message = f"Expected no exit, but exit detected at turn {actual_exit_turn}"
                
                processing_time = (datetime.now() - start_time).total_seconds()
                
                status = "✅ PASS" if success else "❌ FAIL" 
                print(f"   Result: {status}")
                if error_message:
                    print(f"           {error_message}")
                
                return TestResult(
                    test_name=test_case.name,
                    success=success,
                    actual_exit_turn=actual_exit_turn,
                    expected_exit_turn=test_case.expected_exit_at,
                    conversation_log=conversation_log,
                    error_message=error_message,
                    processing_time=processing_time
                )
                
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            print(f"   Result: ❌ ERROR - {str(e)}")
            
            return TestResult(
                test_name=test_case.name,
                success=False,
                actual_exit_turn=-1,
                expected_exit_turn=test_case.expected_exit_at,
                conversation_log=conversation_log,
                error_message=str(e),
                processing_time=processing_time
            )
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all test cases and generate comprehensive report"""
        
        print("🔬 Real LiveKit Passive Mode Integration Test")
        print("=" * 70)
        print(f"Total test cases: {len(self.test_cases)}")
        print("Using real LiveKit AgentSession and DischargeAgent")
        print("=" * 70)
        
        # Initialize LLM for testing
        async with openai.LLM(model="gpt-4o-mini") as llm:
            
            start_time = datetime.now()
            results = []
            passed = 0
            failed = 0
            
            for test_case in self.test_cases:
                result = await self.run_single_test(test_case, llm)
                results.append(result)
                
                if result.success:
                    passed += 1
                else:
                    failed += 1
                
                # Small delay between tests
                await asyncio.sleep(0.1)
            
            total_time = (datetime.now() - start_time).total_seconds()
            
            # Generate report
            pass_rate = (passed / len(results)) * 100 if results else 0
            
            print(f"\n📊 Test Results Summary")
            print("=" * 40)
            print(f"Total Tests: {len(results)}")
            print(f"✅ Passed: {passed}")
            print(f"❌ Failed: {failed}")
            print(f"🎯 Pass Rate: {pass_rate:.1f}%")
            print(f"⏱️ Total Time: {total_time:.2f}s")
            
            # Show failed tests
            if failed > 0:
                print(f"\n🐛 Failed Tests:")
                for result in results:
                    if not result.success:
                        print(f"   • {result.test_name}: {result.error_message}")
            
            report = {
                "summary": {
                    "total_tests": len(results),
                    "passed": passed,
                    "failed": failed,
                    "pass_rate": pass_rate,
                    "total_time": total_time
                },
                "test_results": [asdict(r) for r in results],
                "timestamp": datetime.now().isoformat()
            }
            
            # Assessment
            print(f"\n🎖️ Assessment:")
            if pass_rate >= 90:
                print("   🌟 EXCELLENT: Your passive mode implementation is working great!")
            elif pass_rate >= 80:
                print("   ✅ GOOD: Solid performance with minor issues to address.")
            elif pass_rate >= 70:
                print("   ⚠️ FAIR: Decent performance but several areas need attention.")
            else:
                print("   🔧 NEEDS WORK: Significant improvements needed.")
            
            print("=" * 70)
            
            return report

async def main():
    """Main execution function"""
    
    try:
        evaluator = RealLiveKitPassiveModeEvaluator()
        report = await evaluator.run_all_tests()
        
        # Save detailed report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"real_livekit_passive_mode_evaluation_{timestamp}.json"
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n💾 Detailed report saved to: {report_file}")
        
        return report
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    asyncio.run(main())