#!/usr/bin/env python3
"""
Quick test of Maya detection logic only
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

async def test_maya_detection():
    """Test just the Maya detection logic"""
    
    from discharge.agents import DischargeAgent
    
    agent = DischargeAgent()
    mock_ctx = MockRunContext(MockSessionData())
    
    maya_test_cases = [
        # Should EXIT (direct address)
        ("Maya, did you get all that?", "EXIT"),
        ("Hey Maya, are you there?", "EXIT"),
        ("Maya can you repeat that?", "EXIT"),
        ("Did you catch that, Maya?", "EXIT"),
        ("Maya - did you understand?", "EXIT"),
        
        # Should CONTINUE (contextual mention)
        ("Maybe we should ask Maya about this", "CONTINUE"),
        ("Maya is our discharge coordinator", "CONTINUE"),
        ("I think Maya mentioned something earlier", "CONTINUE"),
    ]
    
    print("🔍 Testing Maya Detection Logic")
    print("=" * 40)
    
    for text, expected in maya_test_cases:
        # Test the helper function directly
        is_addressed = agent._is_maya_directly_addressed(text.lower())
        
        # Test the full analyze_exit_signal function
        result = await agent.analyze_exit_signal(mock_ctx, text)
        is_exit = "exiting passive mode" in result.lower()
        actual = "EXIT" if is_exit else "CONTINUE"
        
        status = "✅" if actual == expected else "❌"
        print(f"{status} '{text}'")
        print(f"   Helper says addressed: {is_addressed}")
        print(f"   Expected: {expected}, Got: {actual}")
        if actual != expected:
            print(f"   Full result: {result}")
        print()

if __name__ == "__main__":
    asyncio.run(test_maya_detection())