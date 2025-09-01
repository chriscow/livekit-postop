#!/usr/bin/env python3
"""
Stress test with completely new edge cases not used in training
These are designed to be tricky and test real-world scenarios
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import List

sys.path.insert(0, '.')

@dataclass 
class MockSessionData:
    session_id: str = "test-session-001"
    workflow_mode: str = "normal" 
    is_passive_mode: bool = False
    patient_name: str = "Test Patient"
    collected_instructions: List[str] = None
    
    def __post_init__(self):
        if self.collected_instructions is None:
            self.collected_instructions = []

class MockRunContext:
    def __init__(self, userdata):
        self.userdata = userdata

async def stress_test_new_cases():
    """Stress test with completely new challenging edge cases"""
    
    from discharge.agents import DischargeAgent
    
    agent = DischargeAgent()
    mock_ctx = MockRunContext(MockSessionData())
    
    # NEW challenging test cases - never seen before
    new_stress_tests = [
        # Tricky Maya variations - should EXIT
        ("Maya, can you summarize what we discussed?", "EXIT", "Maya with summarization request"),
        ("Maya? Did you catch all of that?", "EXIT", "Maya with question mark"),
        ("Alright Maya, what did you record?", "EXIT", "Prefixed Maya address"),
        ("Let me ask Maya - did you get everything?", "EXIT", "Maya in middle with dash"),
        
        # Tricky Maya false positives - should CONTINUE  
        ("I think Maya's system is working well", "CONTINUE", "Maya possessive form"),
        ("The Maya protocol requires documentation", "CONTINUE", "Maya as proper noun/protocol"),
        ("Maya and I discussed this earlier", "CONTINUE", "Maya as person reference"),
        ("According to Maya's notes from yesterday", "CONTINUE", "Maya possessive with context"),
        
        # Complex completion variants - should EXIT
        ("Well, I think that pretty much covers it all", "EXIT", "Complex informal completion"),
        ("Okay, that should do it for the instructions", "EXIT", "That should do it variant"),
        ("I reckon that's about everything you need", "EXIT", "Regional dialect completion"),
        ("So that wraps things up nicely", "EXIT", "Things up variant"), 
        ("Right, I believe we've covered it all", "EXIT", "We've covered it variant"),
        ("That pretty much sums up everything", "EXIT", "Sums up everything"),
        ("I suppose that covers all the bases", "EXIT", "Covers all the bases"),
        
        # Complex verification - should EXIT  
        ("Did you manage to get all of that down?", "EXIT", "Manage to get down variant"),
        ("Are you able to play that back to me?", "EXIT", "Play back verification"),
        ("Can you confirm you have everything?", "EXIT", "Confirm you have variant"),
        ("Would you mind repeating what I just said?", "EXIT", "Polite repeat request"),
        
        # Social closing variants - should EXIT
        ("Alright, you take care now", "EXIT", "Take care now variant"),
        ("Best wishes for your recovery", "EXIT", "Best wishes variant"), 
        ("Hope everything goes smoothly", "EXIT", "Hope goes smoothly"),
        ("Take care of yourself", "EXIT", "Take care of yourself"),
        ("Get well soon, okay?", "EXIT", "Get well soon okay"),
        
        # Tricky false positive completions - should CONTINUE
        ("I'm done talking about this topic", "CONTINUE", "Done talking about topic"),
        ("That covers the medication part", "CONTINUE", "Covers partial topic"),
        ("We're finished with the first section", "CONTINUE", "Finished with section"),
        ("That concludes my explanation of dosages", "CONTINUE", "Concludes explanation of"),
        ("Nothing else about wound care", "CONTINUE", "Nothing else about specific"),
        ("Any questions before we move on?", "CONTINUE", "Questions before move on"),
        ("Are you following so far?", "CONTINUE", "Following so far"),
        
        # Interruption and continuation - should CONTINUE
        ("Hold on, let me check my notes", "CONTINUE", "Hold on check notes"),
        ("Sorry, where was I?", "CONTINUE", "Where was I"),
        ("Let me see... what's next?", "CONTINUE", "Let me see what's next"),
        ("Hang on a moment", "CONTINUE", "Hang on moment"),
        ("Give me just a second", "CONTINUE", "Give me second"),
        
        # Complex conversational - should CONTINUE
        ("The doctor mentioned this earlier", "CONTINUE", "Doctor mentioned earlier"),
        ("As we discussed in the room", "CONTINUE", "As we discussed"),
        ("Like I said before", "CONTINUE", "Like I said before"),
        ("You'll remember from our conversation", "CONTINUE", "Remember from conversation"),
        
        # Ambiguous boundary cases - these are the real tests
        ("I think that covers most of it", "EXIT", "Most of it - should still exit?"),
        ("That should be almost everything", "CONTINUE", "Almost everything - partial?"),
        ("Any final questions before we wrap up?", "EXIT", "Final questions - completion signal?"),
        ("Do you have any other questions?", "CONTINUE", "Other questions - or completion?"),
        ("Is there anything else you need?", "EXIT", "Anything else need - completion?"),
        ("That's probably all you need to know", "EXIT", "Probably all - completion?"),
        ("I guess that covers the main points", "EXIT", "Main points - or partial?"),
        
        # Multi-layered complexity
        ("Maya, I think that covers everything, any questions?", "EXIT", "Maya + completion + questions"),
        ("So Maya, did you get all that? Good luck!", "EXIT", "Maya + verification + social"),
        ("Alright, that should be everything. Take care now!", "EXIT", "Completion + social closing"),
    ]
    
    print("🚨 STRESS TEST: Completely New Edge Cases")
    print("=" * 60)
    print(f"Testing {len(new_stress_tests)} never-before-seen cases...")
    print()
    
    correct_exits = 0
    correct_continues = 0
    incorrect_classifications = []
    
    for i, (text, expected, description) in enumerate(new_stress_tests):
        result = await agent.analyze_exit_signal(mock_ctx, text)
        
        # Determine if exit was recommended
        is_exit = "exit" in result.lower() and "exiting passive mode" in result.lower()
        actual = "EXIT" if is_exit else "CONTINUE"
        
        # Track results
        status = "✅" if actual == expected else "❌"
        
        if actual == expected:
            if actual == "EXIT":
                correct_exits += 1
            else:
                correct_continues += 1
        else:
            incorrect_classifications.append({
                "text": text,
                "expected": expected,
                "actual": actual, 
                "description": description,
                "result": result
            })
        
        print(f"{status} '{text[:60]}{'...' if len(text) > 60 else ''}'")
        print(f"   Expected: {expected}, Got: {actual}")
        if actual != expected:
            print(f"   Reasoning: {result}")
        print()
        
        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"--- Progress: {i + 1}/{len(new_stress_tests)} ---\n")
    
    # Final analysis
    total = len(new_stress_tests)
    correct = correct_exits + correct_continues
    accuracy = (correct / total) * 100
    
    print("🎯 STRESS TEST RESULTS")
    print("=" * 40)
    print(f"Total new test cases: {total}")
    print(f"Correct classifications: {correct}")
    print(f"Accuracy on unseen cases: {accuracy:.1f}%")
    print(f"Exit detection: {correct_exits}")
    print(f"Continue detection: {correct_continues}")
    print(f"Misclassifications: {len(incorrect_classifications)}")
    
    if incorrect_classifications:
        print(f"\n🔍 FAILED CASES:")
        for error in incorrect_classifications:
            print(f"❌ '{error['text'][:50]}...'")
            print(f"   Expected: {error['expected']}, Got: {error['actual']}")
            print(f"   Description: {error['description']}")
            print()
    
    # Assessment
    if accuracy >= 90:
        print("🌟 EXCELLENT: System generalizes well to unseen cases!")
    elif accuracy >= 80:
        print("✅ GOOD: Solid generalization with minor edge cases")
    elif accuracy >= 70:
        print("⚠️ FAIR: Some overfitting, needs refinement")
    else:
        print("🔧 POOR: Significant overfitting to training cases")
    
    return accuracy, incorrect_classifications

if __name__ == "__main__":
    asyncio.run(stress_test_new_cases())