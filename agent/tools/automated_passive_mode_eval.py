#!/usr/bin/env python3
"""
Comprehensive automated evaluation suite for discharge agent passive listening mode.
Tests exhaustive scenarios, stop words, edge cases, and performance metrics.
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
import itertools

# Add project root to path
sys.path.append('.')

class ExitSignalType(Enum):
    DIRECT_ADDRESS = "direct_address"
    COMPLETION_PHRASE = "completion_phrase" 
    SOCIAL_CLOSING = "social_closing"
    VERIFICATION_REQUEST = "verification_request"
    CONVERSATION_SHIFT = "conversation_shift"
    NO_EXIT = "no_exit"

@dataclass
class TestCase:
    """Individual test case for passive mode evaluation"""
    id: str
    name: str
    conversation: List[Dict[str, str]]
    expected_exit_turn: int  # -1 means no exit expected
    expected_exit_type: ExitSignalType
    expected_instructions: int
    instruction_categories: List[str]
    confidence_level: float  # 0-1, how confident we are this should trigger exit
    notes: str = ""

@dataclass 
class TestResult:
    """Result of a single test case"""
    test_id: str
    success: bool
    actual_exit_turn: int
    expected_exit_turn: int
    exit_type_detected: str
    instructions_collected: int
    processing_time: float
    error_message: str = ""
    conversation_log: List[Dict] = None

class ComprehensiveEvaluator:
    """Exhaustive automated testing for passive mode"""
    
    def __init__(self):
        self.test_cases = []
        self.results = []
        self.stop_words = self._generate_stop_word_variants()
        self.completion_phrases = self._generate_completion_phrases()
        self.social_closings = self._generate_social_closings()
        self.direct_addresses = self._generate_direct_addresses()
        self.verification_requests = self._generate_verification_requests()
        self._generate_all_test_cases()
        
    def _generate_stop_word_variants(self) -> List[str]:
        """Generate comprehensive stop word variations"""
        base_words = ["maya", "Maya", "MAYA"]
        contexts = [
            "{word}",
            "Hey {word}",
            "{word}, are you there?",
            "{word}, did you get that?",
            "Okay {word}",
            "{word} please summarize",
            "Can you hear us {word}?",
            "{word}, are you listening?",
            "Thank you {word}",
            "{word}, what did you capture?",
            "So {word}, any questions?",
            "{word} can you translate that?",
            "Alright {word}",
            "{word}, we're done now"
        ]
        
        variants = []
        for word in base_words:
            for context in contexts:
                variants.append(context.format(word=word))
        
        return variants
    
    def _generate_completion_phrases(self) -> List[str]:
        """Generate completion phrase variations"""
        return [
            "That's all",
            "That's all for now",
            "That's everything",
            "We're done",
            "We're all done",
            "We're finished",
            "That's it",
            "That covers it",
            "That covers everything",
            "Any questions?",
            "Do you have any questions?",
            "Questions?",
            "All done",
            "Finished",
            "Complete",
            "That completes the instructions",
            "Those are all the instructions",
            "That's the end of the discharge instructions",
            "No more instructions",
            "I think that's everything"
        ]
    
    def _generate_social_closings(self) -> List[str]:
        """Generate social closing variations"""
        return [
            "Good luck",
            "Good luck with your recovery",
            "Take care",
            "Take care of yourself",
            "Feel better",
            "Get well soon",
            "Hope you feel better",
            "Best wishes",
            "Have a good day",
            "See you later",
            "Until next time",
            "Be safe",
            "Rest well",
            "Heal quickly",
            "Wishing you well",
            "Get some rest",
            "Take it easy",
            "Be well"
        ]
    
    def _generate_direct_addresses(self) -> List[str]:
        """Generate direct address variations beyond just 'Maya'"""
        return [
            "AI assistant",
            "Computer",
            "System", 
            "Translation service",
            "Interpreter",
            "Assistant"
        ]
    
    def _generate_verification_requests(self) -> List[str]:
        """Generate verification request variations"""
        return [
            "Did you get all that?",
            "Did you capture everything?",
            "Do you have all the instructions?",
            "Are you getting this?",
            "Did you hear everything?",
            "Have you been recording this?",
            "Are you capturing the instructions?",
            "Did you understand everything?",
            "Can you repeat what I said?",
            "What instructions did you get?",
            "Can you summarize what we covered?",
            "Tell me what you heard",
            "Read back the instructions",
            "What did you capture?",
            "Do you need me to repeat anything?"
        ]
    
    def _generate_instruction_examples(self) -> List[Dict[str, str]]:
        """Generate realistic medical instruction examples"""
        return [
            {"text": "Take Lisinopril 10mg once daily in the morning", "type": "medication"},
            {"text": "No heavy lifting over 10 pounds for 6 weeks", "type": "activity"},
            {"text": "Keep incision dry for 48 hours", "type": "wound"},
            {"text": "Change dressing daily with sterile technique", "type": "wound"},
            {"text": "Take ibuprofen 600mg every 6 hours for pain", "type": "medication"},
            {"text": "Follow up with Dr. Smith in 2 weeks", "type": "followup"},
            {"text": "Call if temperature exceeds 101.5°F", "type": "warning"},
            {"text": "No driving while taking pain medication", "type": "precaution"},
            {"text": "Wear compression stockings for 2 weeks", "type": "device"},
            {"text": "Clear liquid diet for 24 hours, then advance as tolerated", "type": "diet"},
            {"text": "Monitor blood pressure twice weekly", "type": "monitoring"},
            {"text": "Physical therapy starting next week", "type": "followup"},
            {"text": "Avoid NSAIDs while on blood thinners", "type": "precaution"},
            {"text": "Ice for 20 minutes every 2 hours", "type": "device"},
            {"text": "Return to ER if severe chest pain or shortness of breath", "type": "warning"}
        ]
    
    def _generate_all_test_cases(self):
        """Generate comprehensive test case suite"""
        
        # 1. Stop word variations
        self._generate_stop_word_test_cases()
        
        # 2. Completion phrase variations  
        self._generate_completion_phrase_test_cases()
        
        # 3. Social closing variations
        self._generate_social_closing_test_cases()
        
        # 4. Verification request variations
        self._generate_verification_request_test_cases()
        
        # 5. Complex multi-instruction scenarios
        self._generate_complex_instruction_scenarios()
        
        # 6. Edge cases and false positives
        self._generate_edge_case_scenarios()
        
        # 7. Timing and sequence variations
        self._generate_timing_scenarios()
        
        # 8. Multi-modal exit signal combinations
        self._generate_combination_scenarios()
        
    def _generate_stop_word_test_cases(self):
        """Generate test cases for all stop word variations"""
        instructions = self._generate_instruction_examples()[:3]
        
        for i, stop_word in enumerate(self.stop_words[:20]):  # Limit to avoid explosion
            conversation = []
            # Add some instructions first
            for inst in instructions:
                conversation.append({"role": "doctor", "text": inst["text"]})
            
            # Add stop word
            conversation.append({"role": "doctor", "text": stop_word})
            
            self.test_cases.append(TestCase(
                id=f"stop_word_{i:03d}",
                name=f"Stop Word: '{stop_word}'",
                conversation=conversation,
                expected_exit_turn=len(instructions),
                expected_exit_type=ExitSignalType.DIRECT_ADDRESS,
                expected_instructions=len(instructions),
                instruction_categories=[inst["type"] for inst in instructions],
                confidence_level=0.95,
                notes=f"Direct address variation: {stop_word}"
            ))
    
    def _generate_completion_phrase_test_cases(self):
        """Generate test cases for completion phrases"""
        instructions = self._generate_instruction_examples()[:4]
        
        for i, phrase in enumerate(self.completion_phrases):
            conversation = []
            # Add instructions
            for inst in instructions:
                conversation.append({"role": "doctor", "text": inst["text"]})
            
            # Add completion phrase
            conversation.append({"role": "doctor", "text": phrase})
            
            self.test_cases.append(TestCase(
                id=f"completion_{i:03d}",
                name=f"Completion: '{phrase}'",
                conversation=conversation,
                expected_exit_turn=len(instructions),
                expected_exit_type=ExitSignalType.COMPLETION_PHRASE,
                expected_instructions=len(instructions),
                instruction_categories=[inst["type"] for inst in instructions],
                confidence_level=0.85,
                notes=f"Completion phrase: {phrase}"
            ))
    
    def _generate_social_closing_test_cases(self):
        """Generate test cases for social closings"""
        instructions = self._generate_instruction_examples()[:2]
        
        for i, closing in enumerate(self.social_closings):
            conversation = []
            # Add instructions  
            for inst in instructions:
                conversation.append({"role": "doctor", "text": inst["text"]})
            
            # Add social closing
            conversation.append({"role": "doctor", "text": closing})
            
            self.test_cases.append(TestCase(
                id=f"social_{i:03d}",
                name=f"Social: '{closing}'",
                conversation=conversation,
                expected_exit_turn=len(instructions),
                expected_exit_type=ExitSignalType.SOCIAL_CLOSING,
                expected_instructions=len(instructions),
                instruction_categories=[inst["type"] for inst in instructions],
                confidence_level=0.75,
                notes=f"Social closing: {closing}"
            ))
    
    def _generate_verification_request_test_cases(self):
        """Generate test cases for verification requests"""
        instructions = self._generate_instruction_examples()[:3]
        
        for i, request in enumerate(self.verification_requests):
            conversation = []
            # Add instructions
            for inst in instructions:
                conversation.append({"role": "doctor", "text": inst["text"]})
            
            # Add verification request
            conversation.append({"role": "doctor", "text": request})
            
            self.test_cases.append(TestCase(
                id=f"verify_{i:03d}",
                name=f"Verification: '{request}'",
                conversation=conversation,
                expected_exit_turn=len(instructions),
                expected_exit_type=ExitSignalType.VERIFICATION_REQUEST,
                expected_instructions=len(instructions),
                instruction_categories=[inst["type"] for inst in instructions],
                confidence_level=0.90,
                notes=f"Verification request: {request}"
            ))
    
    def _generate_complex_instruction_scenarios(self):
        """Generate complex multi-instruction scenarios"""
        all_instructions = self._generate_instruction_examples()
        
        # Various instruction count scenarios
        for count in [1, 3, 5, 8, 10, 15]:
            if count > len(all_instructions):
                continue
                
            instructions = all_instructions[:count]
            
            # Test with different exit signals
            exit_signals = [
                ("Maya, that's everything", ExitSignalType.DIRECT_ADDRESS, 0.95),
                ("Any questions about those instructions?", ExitSignalType.COMPLETION_PHRASE, 0.85),
                ("Take care and heal well", ExitSignalType.SOCIAL_CLOSING, 0.70),
                ("Did you capture all of that?", ExitSignalType.VERIFICATION_REQUEST, 0.90)
            ]
            
            for signal, signal_type, confidence in exit_signals:
                conversation = []
                for inst in instructions:
                    conversation.append({"role": "doctor", "text": inst["text"]})
                conversation.append({"role": "doctor", "text": signal})
                
                self.test_cases.append(TestCase(
                    id=f"complex_{count}_{signal_type.value}",
                    name=f"Complex {count} instructions + {signal_type.value}",
                    conversation=conversation,
                    expected_exit_turn=len(instructions),
                    expected_exit_type=signal_type,
                    expected_instructions=len(instructions),
                    instruction_categories=[inst["type"] for inst in instructions],
                    confidence_level=confidence,
                    notes=f"{count} instructions with {signal_type.value} exit"
                ))
    
    def _generate_edge_case_scenarios(self):
        """Generate edge cases and false positive scenarios"""
        
        # False positive scenarios - should NOT trigger exit
        false_positives = [
            {
                "conversation": [
                    {"role": "doctor", "text": "Hello everyone, thank you for being here"},
                    {"role": "patient", "text": "Good morning doctor"},
                    {"role": "doctor", "text": "Let's begin with your instructions"}
                ],
                "name": "Greeting with 'thank you'",
                "notes": "Social pleasantries should not trigger exit"
            },
            {
                "conversation": [
                    {"role": "doctor", "text": "Take these medications as prescribed"},
                    {"role": "nurse", "text": "I need to step out for a moment"},
                    {"role": "doctor", "text": "We'll continue when she returns"}
                ],
                "name": "Incomplete conversation", 
                "notes": "Interrupted conversation should not exit"
            },
            {
                "conversation": [
                    {"role": "patient", "text": "Maya is my daughter's name too"},
                    {"role": "doctor", "text": "That's a lovely name"},
                    {"role": "doctor", "text": "Now for your medications"}
                ],
                "name": "Maya as proper name",
                "notes": "Maya mentioned but not addressing the AI"
            },
            {
                "conversation": [
                    {"role": "doctor", "text": "Do you have any questions so far?"},
                    {"role": "patient", "text": "No, I understand"},
                    {"role": "doctor", "text": "Good, let's continue with more instructions"}
                ],
                "name": "Mid-conversation question check",
                "notes": "Questions during conversation should not exit"
            }
        ]
        
        for i, scenario in enumerate(false_positives):
            self.test_cases.append(TestCase(
                id=f"false_pos_{i:03d}",
                name=f"False Positive: {scenario['name']}",
                conversation=scenario["conversation"],
                expected_exit_turn=-1,  # No exit expected
                expected_exit_type=ExitSignalType.NO_EXIT,
                expected_instructions=1 if "medication" in scenario["conversation"][0]["text"] else 0,
                instruction_categories=["medication"] if "medication" in scenario["conversation"][0]["text"] else [],
                confidence_level=0.95,
                notes=scenario["notes"]
            ))
    
    def _generate_timing_scenarios(self):
        """Generate scenarios testing timing and sequence sensitivity"""
        
        # Early exit scenarios
        early_exits = [
            {"signal": "Maya, wait", "turn": 1, "confidence": 0.85},
            {"signal": "Maya, stop for a second", "turn": 0, "confidence": 0.90},
            {"signal": "Actually Maya, can you help with something?", "turn": 2, "confidence": 0.95}
        ]
        
        for i, scenario in enumerate(early_exits):
            conversation = []
            instructions = self._generate_instruction_examples()[:5]
            
            # Add instructions up to exit turn
            for j in range(scenario["turn"]):
                if j < len(instructions):
                    conversation.append({"role": "doctor", "text": instructions[j]["text"]})
            
            # Add early exit signal
            conversation.append({"role": "doctor", "text": scenario["signal"]})
            
            self.test_cases.append(TestCase(
                id=f"early_exit_{i:03d}",
                name=f"Early Exit: Turn {scenario['turn']}",
                conversation=conversation,
                expected_exit_turn=scenario["turn"],
                expected_exit_type=ExitSignalType.DIRECT_ADDRESS,
                expected_instructions=scenario["turn"],
                instruction_categories=[inst["type"] for inst in instructions[:scenario["turn"]]],
                confidence_level=scenario["confidence"],
                notes=f"Early exit at turn {scenario['turn']}"
            ))
    
    def _generate_combination_scenarios(self):
        """Generate scenarios with multiple exit signals"""
        
        # Multiple signal combinations
        combinations = [
            {
                "signals": ["That's all for now", "Maya, did you get that?"],
                "expected_turn": 0,  # First signal should trigger
                "name": "Completion + Direct Address"
            },
            {
                "signals": ["Any questions?", "Good luck with recovery"],
                "expected_turn": 0,  # First signal should trigger
                "name": "Completion + Social Closing"
            },
            {
                "signals": ["Did you capture everything?", "Take care now"],
                "expected_turn": 0,  # First signal should trigger  
                "name": "Verification + Social"
            }
        ]
        
        for i, combo in enumerate(combinations):
            instructions = self._generate_instruction_examples()[:3]
            conversation = []
            
            # Add instructions
            for inst in instructions:
                conversation.append({"role": "doctor", "text": inst["text"]})
            
            # Add combination signals
            for signal in combo["signals"]:
                conversation.append({"role": "doctor", "text": signal})
            
            self.test_cases.append(TestCase(
                id=f"combo_{i:03d}",
                name=f"Combination: {combo['name']}",
                conversation=conversation,
                expected_exit_turn=len(instructions) + combo["expected_turn"],
                expected_exit_type=ExitSignalType.COMPLETION_PHRASE,  # First signal type
                expected_instructions=len(instructions),
                instruction_categories=[inst["type"] for inst in instructions],
                confidence_level=0.95,
                notes=f"Multiple exit signals: {combo['name']}"
            ))

class MockSessionData:
    """Mock session data for testing"""
    def __init__(self):
        self.session_id = f"auto_test_{int(datetime.now().timestamp())}"
        self.patient_name = "Test Patient"
        self.patient_language = "English"
        self.workflow_mode = "passive_listening"
        self.is_passive_mode = True
        self.collected_instructions = []
        self.instructions_map = {}
        self._exiting_passive = False

class MockChatMessage:
    """Mock chat message for testing"""
    def __init__(self, text):
        self.text_content = text

class RealAgentSessionManager:
    """Manages real agent sessions for text-based testing"""
    
    def __init__(self):
        self.agent = None
        self.session = None
        self.chat_ctx = None
        
    async def setup_text_only_session(self):
        """Set up a real agent session configured for text-only interaction"""
        try:
            # Import LiveKit components
            from livekit.agents import AgentSession, JobContext
            from livekit.agents.llm import ChatContext, ChatMessage
            from livekit.plugins import openai
            from discharge.agents import DischargeAgent
            
            # Create real agent instance
            self.agent = DischargeAgent()
            
            # Configure for text-only mode (no STT/TTS)
            self.chat_ctx = ChatContext()
            
            print("✅ Real agent session initialized for text-only testing")
            return True
            
        except ImportError as e:
            print(f"❌ Failed to import required components: {e}")
            print("   Make sure you're running in the LiveKit environment")
            return False
        except Exception as e:
            print(f"❌ Failed to setup agent session: {e}")
            return False
    
    async def process_text_input(self, text_input: str, session_data=None) -> Dict[str, Any]:
        """Process text input through the real agent using direct method testing"""
        if not self.agent:
            raise RuntimeError("Agent session not initialized")
        
        from livekit.agents.llm import ChatMessage
        
        # Create real ChatMessage from text
        message = ChatMessage(
            role="user",
            content=[text_input]  # ChatMessage expects content as a list
        )
        
        # Create mock session and inject into agent temporarily
        class MockSession:
            def __init__(self, userdata):
                self.userdata = userdata
                
            async def say(self, msg):
                pass  # Silent for testing
                
            async def generate_reply(self, **kwargs):
                pass  # Silent for testing
                
            def on(self, event_name):
                def decorator(func):
                    return func
                return decorator
        
        # Store agent's original session (if any)
        original_session = getattr(self.agent, 'session', None)
        
        # Create mock session with test data
        if session_data:
            mock_session = MockSession(session_data)
            
            # Use Python's attribute setting directly (bypassing property)
            object.__setattr__(self.agent, 'session', mock_session)
        
        # Store state before processing
        pre_state = {
            'is_passive': getattr(session_data, 'is_passive_mode', True) if session_data else True,
            'instructions_count': len(getattr(session_data, 'collected_instructions', [])),
            'tts_suppressed': getattr(self.agent, '_tts_suppressed', False)
        }
        
        try:
            # Process through agent's real on_user_turn_completed method
            await self.agent.on_user_turn_completed(self.chat_ctx, message)
        except Exception as e:
            # Restore original session
            if original_session:
                object.__setattr__(self.agent, 'session', original_session)
            raise e
        
        # Capture state after processing
        post_state = {
            'is_passive': getattr(session_data, 'is_passive_mode', True) if session_data else True,
            'instructions_count': len(getattr(session_data, 'collected_instructions', [])),
            'tts_suppressed': getattr(self.agent, '_tts_suppressed', False)
        }
        
        # Restore original session
        if original_session:
            object.__setattr__(self.agent, 'session', original_session)
        
        # Detect exit condition
        exit_detected = pre_state['is_passive'] and not post_state['is_passive']
        
        return {
            'pre_state': pre_state,
            'post_state': post_state,
            'exit_detected': exit_detected,
            'tts_suppressed': post_state['tts_suppressed'],
            'instructions_collected': post_state['instructions_count'] - pre_state['instructions_count']
        }

class AutomatedTestRunner:
    """Runs automated tests with real agent and text-only interface"""
    
    def __init__(self):
        self.evaluator = ComprehensiveEvaluator()
        self.results = []
        self.session_manager = RealAgentSessionManager()
        
    async def initialize(self):
        """Initialize the real agent session"""
        success = await self.session_manager.setup_text_only_session()
        if not success:
            raise RuntimeError("Failed to initialize real agent session")
        return True
        
    async def run_single_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case with real agent"""
        
        start_time = datetime.now()
        
        # Create real session data
        session_data = MockSessionData()  # This mimics the real session userdata
        conversation_log = []
        
        try:
            exit_detected_at = -1
            
            for i, turn in enumerate(test_case.conversation):
                # Process text input through real agent
                result = await self.session_manager.process_text_input(
                    turn["text"], 
                    session_data
                )
                
                # Log the conversation turn
                conversation_log.append({
                    "turn": i,
                    "role": turn["role"],
                    "text": turn["text"],
                    "pre_passive": result['pre_state']['is_passive'],
                    "post_passive": result['post_state']['is_passive'],
                    "tts_suppressed": result['tts_suppressed'],
                    "exit_detected": result['exit_detected'],
                    "instructions_delta": result['instructions_collected']
                })
                
                # Track first exit detection
                if result['exit_detected'] and exit_detected_at == -1:
                    exit_detected_at = i
                
                # Simulate instruction collection for realistic testing
                if "medication" in turn["text"].lower() or "take" in turn["text"].lower():
                    session_data.collected_instructions.append({
                        "text": turn["text"],
                        "type": "medication"
                    })
                elif "wound" in turn["text"].lower() or "bandage" in turn["text"].lower():
                    session_data.collected_instructions.append({
                        "text": turn["text"], 
                        "type": "wound"
                    })
                elif any(word in turn["text"].lower() for word in ["follow up", "appointment", "visit"]):
                    session_data.collected_instructions.append({
                        "text": turn["text"],
                        "type": "followup"
                    })
                elif any(word in turn["text"].lower() for word in ["call if", "emergency", "fever"]):
                    session_data.collected_instructions.append({
                        "text": turn["text"],
                        "type": "warning"
                    })
                elif "activity" in turn["text"].lower() or "lifting" in turn["text"].lower():
                    session_data.collected_instructions.append({
                        "text": turn["text"],
                        "type": "activity"
                    })
            
            # Evaluate test success
            success = True
            error_message = ""
            
            if test_case.expected_exit_turn >= 0:
                # Exit expected
                if exit_detected_at != test_case.expected_exit_turn:
                    success = False
                    error_message = f"Expected exit at turn {test_case.expected_exit_turn}, got {exit_detected_at}"
            else:
                # No exit expected
                if exit_detected_at >= 0:
                    success = False
                    error_message = f"Unexpected exit at turn {exit_detected_at}"
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return TestResult(
                test_id=test_case.id,
                success=success,
                actual_exit_turn=exit_detected_at,
                expected_exit_turn=test_case.expected_exit_turn,
                exit_type_detected=test_case.expected_exit_type.value,
                instructions_collected=len(session_data.collected_instructions),
                processing_time=processing_time,
                error_message=error_message,
                conversation_log=conversation_log
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            return TestResult(
                test_id=test_case.id,
                success=False,
                actual_exit_turn=-1,
                expected_exit_turn=test_case.expected_exit_turn,
                exit_type_detected="error",
                instructions_collected=0,
                processing_time=processing_time,
                error_message=str(e)
            )
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all test cases and generate comprehensive report"""
        
        print("🚀 Starting Comprehensive Automated Evaluation")
        print("=" * 80)
        print(f"Total test cases: {len(self.evaluator.test_cases)}")
        
        # Initialize real agent session
        print("🔧 Initializing real agent session for text-only testing...")
        try:
            await self.initialize()
        except Exception as e:
            print(f"❌ Failed to initialize agent: {e}")
            print("   Please ensure you're running in the LiveKit environment with proper dependencies")
            return {"error": "Failed to initialize agent", "details": str(e)}
        
        start_time = datetime.now()
        results = []
        
        # Group tests by category for organized output
        categories = {}
        for test_case in self.evaluator.test_cases:
            category = test_case.id.split('_')[0]
            if category not in categories:
                categories[category] = []
            categories[category].append(test_case)
        
        # Run tests by category
        for category, test_cases in categories.items():
            print(f"\n🧪 Testing Category: {category.upper()}")
            print(f"   Tests: {len(test_cases)}")
            
            category_results = []
            passed = 0
            
            for i, test_case in enumerate(test_cases):
                if i % 10 == 0:  # Progress indicator
                    print(f"   Progress: {i}/{len(test_cases)}")
                
                result = await self.run_single_test(test_case)
                category_results.append(result)
                
                if result.success:
                    passed += 1
            
            category_pass_rate = (passed / len(test_cases)) * 100
            print(f"   ✅ Category Pass Rate: {category_pass_rate:.1f}% ({passed}/{len(test_cases)})")
            
            results.extend(category_results)
        
        total_time = (datetime.now() - start_time).total_seconds()
        
        # Generate comprehensive report
        return self._generate_report(results, total_time)
    
    def _generate_report(self, results: List[TestResult], total_time: float) -> Dict[str, Any]:
        """Generate comprehensive evaluation report"""
        
        # Overall statistics
        total_tests = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total_tests - passed
        pass_rate = (passed / total_tests) * 100 if total_tests > 0 else 0
        
        # Performance metrics
        processing_times = [r.processing_time for r in results]
        avg_processing_time = statistics.mean(processing_times)
        max_processing_time = max(processing_times)
        min_processing_time = min(processing_times)
        
        # Category breakdown
        category_stats = {}
        for result in results:
            category = result.test_id.split('_')[0]
            if category not in category_stats:
                category_stats[category] = {"passed": 0, "total": 0}
            
            category_stats[category]["total"] += 1
            if result.success:
                category_stats[category]["passed"] += 1
        
        # Add pass rates
        for category in category_stats:
            stats = category_stats[category]
            stats["pass_rate"] = (stats["passed"] / stats["total"]) * 100
        
        # Error analysis
        error_types = {}
        for result in results:
            if not result.success and result.error_message:
                error_type = result.error_message.split(',')[0]  # First part of error
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Failed test details
        failed_tests = [
            {
                "test_id": r.test_id,
                "error": r.error_message,
                "expected_exit": r.expected_exit_turn,
                "actual_exit": r.actual_exit_turn
            }
            for r in results if not r.success
        ]
        
        report = {
            "summary": {
                "total_tests": total_tests,
                "passed": passed,
                "failed": failed,
                "pass_rate": pass_rate,
                "total_execution_time": total_time,
                "avg_test_time": avg_processing_time,
                "min_test_time": min_processing_time,
                "max_test_time": max_processing_time
            },
            "category_breakdown": category_stats,
            "error_analysis": error_types,
            "failed_tests": failed_tests,
            "detailed_results": [asdict(r) for r in results],
            "timestamp": datetime.now().isoformat(),
            "evaluation_config": {
                "stop_word_variants": len(self.evaluator.stop_words),
                "completion_phrases": len(self.evaluator.completion_phrases),
                "social_closings": len(self.evaluator.social_closings),
                "verification_requests": len(self.evaluator.verification_requests)
            }
        }
        
        return report
    
    def print_report_summary(self, report: Dict[str, Any]):
        """Print executive summary of the evaluation report"""
        
        # Check if report contains error
        if "error" in report:
            print("\n" + "="*80)
            print("❌ EVALUATION FAILED")
            print("="*80)
            print(f"Error: {report['error']}")
            if "details" in report:
                print(f"Details: {report['details']}")
            print("="*80)
            return
        
        summary = report["summary"]
        
        print("\n" + "="*80)
        print("🎯 COMPREHENSIVE EVALUATION RESULTS")
        print("="*80)
        
        print(f"📊 Overall Performance:")
        print(f"   Total Tests: {summary['total_tests']}")
        print(f"   ✅ Passed: {summary['passed']}")
        print(f"   ❌ Failed: {summary['failed']}")
        print(f"   🎯 Pass Rate: {summary['pass_rate']:.1f}%")
        
        print(f"\n⏱️ Performance Metrics:")
        print(f"   Total Time: {summary['total_execution_time']:.2f}s")
        print(f"   Avg Test Time: {summary['avg_test_time']*1000:.1f}ms")
        print(f"   Fastest Test: {summary['min_test_time']*1000:.1f}ms")
        print(f"   Slowest Test: {summary['max_test_time']*1000:.1f}ms")
        
        print(f"\n📈 Category Breakdown:")
        for category, stats in report["category_breakdown"].items():
            status = "✅" if stats["pass_rate"] >= 80 else "⚠️" if stats["pass_rate"] >= 60 else "❌"
            print(f"   {status} {category.upper()}: {stats['pass_rate']:.1f}% ({stats['passed']}/{stats['total']})")
        
        if report["error_analysis"]:
            print(f"\n🐛 Top Error Types:")
            sorted_errors = sorted(report["error_analysis"].items(), key=lambda x: x[1], reverse=True)
            for error_type, count in sorted_errors[:5]:
                print(f"   • {error_type}: {count} occurrences")
        
        # Performance assessment
        print(f"\n🎖️ Assessment:")
        if summary['pass_rate'] >= 90:
            print("   🌟 EXCELLENT: Your passive mode implementation is performing exceptionally well!")
        elif summary['pass_rate'] >= 80:
            print("   ✅ GOOD: Solid performance with room for minor improvements.")
        elif summary['pass_rate'] >= 70:
            print("   ⚠️ FAIR: Decent performance but several areas need attention.")
        elif summary['pass_rate'] >= 60:
            print("   🔧 NEEDS WORK: Significant improvements needed.")
        else:
            print("   🚨 POOR: Major issues detected. Review implementation.")
        
        print("="*80)

async def main():
    """Main execution entry point - fully automated"""
    
    print("🔬 Comprehensive Discharge Agent Passive Mode Evaluation")
    print("="*80)
    print("This will exhaustively test your passive mode implementation across:")
    print("• Stop word variations (20+ variants)")
    print("• Completion phrases (20+ phrases)")  
    print("• Social closings (18+ closings)")
    print("• Verification requests (15+ requests)")
    print("• Complex multi-instruction scenarios")
    print("• Edge cases and false positives")
    print("• Timing and sequence sensitivity")
    print("• Multi-modal exit signal combinations")
    print("="*80)
    
    runner = AutomatedTestRunner()
    
    print(f"\n🎯 Starting automated evaluation of {len(runner.evaluator.test_cases)} comprehensive test cases...")
    print("   Using real agent with text-only interface (no STT/TTS)")
    print("   This may take several minutes depending on test complexity...")
    
    # Run the comprehensive evaluation automatically
    report = await runner.run_all_tests()
    
    # Print summary
    runner.print_report_summary(report)
    
    # Save detailed report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"passive_mode_comprehensive_evaluation_{timestamp}.json"
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n💾 Detailed report saved to: {report_file}")
    
    # Generate recommendations
    if report["summary"]["pass_rate"] < 80:
        print(f"\n💡 Recommendations:")
        
        category_stats = report["category_breakdown"]
        worst_category = min(category_stats.items(), key=lambda x: x[1]["pass_rate"])
        
        print(f"   1. Focus on {worst_category[0]} scenarios (lowest pass rate: {worst_category[1]['pass_rate']:.1f}%)")
        
        if report["error_analysis"]:
            top_error = max(report["error_analysis"].items(), key=lambda x: x[1])
            print(f"   2. Address most common error: {top_error[0]} ({top_error[1]} occurrences)")
        
        print(f"   3. Review failed test cases in the detailed report")
        print(f"   4. Consider adjusting exit detection sensitivity")
    
    return report

if __name__ == "__main__":
    try:
        report = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Evaluation interrupted by user")
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()