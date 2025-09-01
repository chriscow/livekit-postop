#!/usr/bin/env python3
"""
Get detailed breakdown of exit detection test results for analysis
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

# Add current directory to path for imports
sys.path.insert(0, '.')

@dataclass 
class MockSessionData:
    """Mock session data for testing"""
    session_id: str = "test-session-001"
    workflow_mode: str = "normal"
    is_passive_mode: bool = False
    patient_name: str = "Test Patient"
    collected_instructions: List[str] = None
    
    def __post_init__(self):
        if self.collected_instructions is None:
            self.collected_instructions = []

class MockRunContext:
    """Mock run context for testing function tools"""
    def __init__(self, userdata):
        self.userdata = userdata

async def get_detailed_results():
    """Get detailed breakdown of test results"""
    print("🔍 Detailed Exit Detection Analysis")
    print("=" * 60)
    
    try:
        from discharge.agents import DischargeAgent
        
        agent = DischargeAgent()
        mock_userdata = MockSessionData()
        mock_ctx = MockRunContext(mock_userdata)
        
        # Same test cases as before
        test_cases = [
            # Direct Maya addresses - Should EXIT
            ("Maya, did you get all that?", "EXIT", "Direct Maya address - classic"),
            ("Hey Maya, are you there?", "EXIT", "Hey Maya variation"),
            ("Maya can you repeat that?", "EXIT", "Maya question format"),
            ("Did you catch that, Maya?", "EXIT", "Maya at end of sentence"),
            ("Maya - did you understand?", "EXIT", "Maya with dash separator"),
            
            # Completion signals - Should EXIT  
            ("That's all for the discharge instructions. Any questions?", "EXIT", "Classic completion + any questions"),
            ("Alright, that covers everything", "EXIT", "Informal completion"),
            ("I think we're done here", "EXIT", "Informal done signal"),
            ("That should be everything you need", "EXIT", "Polite completion"),
            ("We're all finished with instructions", "EXIT", "Formal completion"),
            ("That wraps up the discharge process", "EXIT", "Process completion"),
            ("I believe that's everything", "EXIT", "Belief-based completion"),
            ("That concludes our instructions", "EXIT", "Formal conclusion"),
            ("Nothing else to add", "EXIT", "Negative completion"),
            ("I'm all done explaining", "EXIT", "Personal completion"),
            
            # Verification requests - Should EXIT
            ("Did you capture all the instructions?", "EXIT", "Capture verification"),
            ("Were you able to record everything?", "EXIT", "Record verification"),
            ("Do you have all of that?", "EXIT", "General verification"),
            ("Did you get everything I said?", "EXIT", "Direct verification"),
            ("Are you following along okay?", "EXIT", "Following verification"),
            
            # Social closings - Should EXIT
            ("Good luck with your recovery! Take care.", "EXIT", "Good luck closing"),
            ("Hope you feel better soon", "EXIT", "Feel better closing"),
            ("Take it easy and get some rest", "EXIT", "Rest closing"),
            ("Wishing you a speedy recovery", "EXIT", "Speedy recovery"),
            ("Have a great day and heal well", "EXIT", "Great day closing"),
            
            # Edge cases - Tricky scenarios that might confuse
            ("Maybe we should ask Maya about this", "CONTINUE", "Maya mentioned but not addressed"),
            ("Maya is our discharge coordinator", "CONTINUE", "Maya mentioned in context"),
            ("I think Maya mentioned something earlier", "CONTINUE", "Maya referenced indirectly"),
            ("Any questions about the medication?", "CONTINUE", "Questions about specific topic"),
            ("That medication should be taken daily", "CONTINUE", "Instruction containing 'should be'"),
            ("I'm done with this particular instruction", "CONTINUE", "Partial done - not full completion"),
            ("We're almost finished", "CONTINUE", "Almost finished - not quite done"),
            ("That's one instruction down", "CONTINUE", "Partial completion"),
            
            # Normal instructions - Should CONTINUE
            ("Take this medication with food", "CONTINUE", "Basic medication instruction"),
            ("Keep the wound clean and dry", "CONTINUE", "Wound care instruction"),
            ("Follow up with your doctor in one week", "CONTINUE", "Follow-up instruction"),
            ("Call if you have a fever over 101", "CONTINUE", "Warning instruction"),
            ("Don't lift anything heavier than 10 pounds", "CONTINUE", "Activity restriction"),
            ("Apply ice for 20 minutes every hour", "CONTINUE", "Treatment instruction"),
            
            # Conversational noise - Should CONTINUE
            ("Hmm, let me think about that", "CONTINUE", "Thinking pause"),
            ("Where did I put those papers?", "CONTINUE", "Unrelated question"),
            ("The weather is nice today", "CONTINUE", "Unrelated comment"),
            ("Sorry, I need to check something", "CONTINUE", "Interruption"),
            ("Hold on a second", "CONTINUE", "Brief pause"),
            ("Let me grab my notes", "CONTINUE", "Preparation statement"),
        ]
        
        # Categorize results
        correct_exits = []
        correct_continues = []
        false_positives = []  # Should CONTINUE but got EXIT
        false_negatives = []  # Should EXIT but got CONTINUE
        
        print("Processing all test cases...")
        
        for i, (text, expected, description) in enumerate(test_cases):
            result = await agent.analyze_exit_signal(mock_ctx, text)
            
            # Determine if exit was recommended
            is_exit = "exit" in result.lower() and "exiting passive mode" in result.lower()
            actual = "EXIT" if is_exit else "CONTINUE"
            
            # Categorize the result
            if expected == "EXIT" and actual == "EXIT":
                correct_exits.append((text, description, result))
            elif expected == "CONTINUE" and actual == "CONTINUE":
                correct_continues.append((text, description, result))
            elif expected == "CONTINUE" and actual == "EXIT":
                false_positives.append((text, description, result))
            elif expected == "EXIT" and actual == "CONTINUE":
                false_negatives.append((text, description, result))
        
        # Print detailed results
        print(f"\n✅ CORRECT EXIT DETECTIONS ({len(correct_exits)}):")
        for text, desc, result in correct_exits:
            print(f"   ✓ '{text}' - {desc}")
        
        print(f"\n✅ CORRECT CONTINUE DECISIONS ({len(correct_continues)}):")
        for text, desc, result in correct_continues:
            print(f"   ✓ '{text}' - {desc}")
            
        print(f"\n❌ FALSE POSITIVES ({len(false_positives)}) - Should CONTINUE but triggered EXIT:")
        for text, desc, result in false_positives:
            print(f"   ✗ '{text}' - {desc}")
            print(f"     Reasoning: {result}")
            print()
            
        print(f"\n❌ FALSE NEGATIVES ({len(false_negatives)}) - Should EXIT but triggered CONTINUE:")
        for text, desc, result in false_negatives:
            print(f"   ✗ '{text}' - {desc}")
            print(f"     Reasoning: {result}")
            print()
        
        # Summary statistics
        total = len(test_cases)
        correct = len(correct_exits) + len(correct_continues)
        accuracy = (correct / total) * 100
        
        print(f"\n📊 DETAILED PERFORMANCE ANALYSIS:")
        print(f"   Total test cases: {total}")
        print(f"   Correct classifications: {correct}")
        print(f"   False positives (unnecessary exits): {len(false_positives)}")
        print(f"   False negatives (missed exits): {len(false_negatives)}")
        print(f"   Overall accuracy: {accuracy:.1f}%")
        print(f"   Exit detection recall: {len(correct_exits)/(len(correct_exits)+len(false_negatives))*100:.1f}%")
        print(f"   Continue precision: {len(correct_continues)/(len(correct_continues)+len(false_positives))*100:.1f}%")
        
        return {
            'correct_exits': correct_exits,
            'correct_continues': correct_continues,
            'false_positives': false_positives,
            'false_negatives': false_negatives,
            'accuracy': accuracy
        }
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    asyncio.run(get_detailed_results())