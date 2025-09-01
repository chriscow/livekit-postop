#!/usr/bin/env python3
"""
Test "Thanks Maya" edge case scenarios
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

async def test_thanks_maya():
    from discharge.agents import DischargeAgent
    
    agent = DischargeAgent()
    mock_ctx = MockRunContext(MockSessionData())
    
    test_cases = [
        ("Thanks, Maya", "CONTINUE", "Social thanks - should continue"),
        ("Thank you, Maya", "CONTINUE", "Polite thanks - should continue"), 
        ("Thanks Maya for listening", "CONTINUE", "Extended thanks - should continue"),
        ("Maya, thanks for recording that", "EXIT", "Direct address with thanks - should exit"),
        ("Thanks Maya, did you get that?", "EXIT", "Thanks + question - should exit"),
    ]
    
    print("🔍 Testing Maya Thanks Cases")
    print("=" * 40)
    
    for text, expected, description in test_cases:
        # Test helper function
        is_addressed = agent._is_maya_directly_addressed(text.lower())
        
        # Test full analysis
        result = await agent.analyze_exit_signal(mock_ctx, text)
        is_exit = "exiting passive mode" in result.lower()
        actual = "EXIT" if is_exit else "CONTINUE"
        
        status = "✅" if actual == expected else "❌"
        print(f"{status} \"{text}\"")
        print(f"   Helper addressed: {is_addressed}")
        print(f"   Expected: {expected}, Got: {actual}")
        print(f"   Description: {description}")
        if actual != expected:
            print(f"   Full result: {result}")
        print()
    
    return test_cases

if __name__ == "__main__":
    asyncio.run(test_thanks_maya())