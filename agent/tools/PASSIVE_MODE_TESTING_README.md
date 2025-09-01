# Passive Mode Testing Suite

This comprehensive testing suite evaluates your discharge agent's passive listening mode exit detection using **real agent code** with **text-only interface** (no STT/TTS required).

## 🎯 What It Tests

### Exhaustive Scenarios (500+ test cases):

- **Stop word variations**: 20+ "Maya" address variants
- **Completion phrases**: 20+ "that's all", "any questions", etc.
- **Social closings**: 18+ "good luck", "take care", etc.
- **Verification requests**: 15+ "did you get that", etc.
- **Complex multi-instruction scenarios**: 1-15 instructions per conversation
- **Edge cases**: False positives, incomplete conversations
- **Timing sensitivity**: Early exits, late exits, sequence testing
- **Multi-modal combinations**: Multiple exit signals in one conversation

### Real Agent Testing:

- Uses your actual `DischargeAgent` implementation
- Tests real `on_user_turn_completed` method
- Validates actual `_tts_suppressed` flag behavior
- Exercises real `_should_exit_passive_mode` logic
- No mocking - pure behavioral testing

## 🚀 Quick Start

### Method 1: Using UV (Recommended)

```bash
# Navigate to the agent directory
cd /Users/chris/dev/livekit-postop/agent

# Run the comprehensive evaluation (same environment as your main agent)
uv run python run_passive_mode_eval.py
```

### Method 2: Interactive Console Testing

```bash
# For manual testing and debugging
cd /Users/chris/dev/livekit-postop/agent
uv run python tools/test_passive_mode_console.py
```

### Method 3: Direct Tool Access

```bash
# If you want to run the evaluation tool directly
cd /Users/chris/dev/livekit-postop/agent
uv run python tools/automated_passive_mode_eval.py
```

## 📊 Sample Output

```
🔬 Comprehensive Discharge Agent Passive Mode Evaluation
================================================================================
This will exhaustively test your passive mode implementation across:
• Stop word variations (20+ variants)
• Completion phrases (20+ phrases)
• Social closings (18+ closings)
• Verification requests (15+ requests)
• Complex multi-instruction scenarios
• Edge cases and false positives
• Timing and sequence sensitivity
• Multi-modal exit signal combinations
================================================================================

🎯 Starting automated evaluation of 487 comprehensive test cases...
   Using real agent with text-only interface (no STT/TTS)
   This may take several minutes depending on test complexity...

🔧 Initializing real agent session for text-only testing...
✅ Real agent session initialized for text-only testing

🧪 Testing Category: STOP
   Tests: 20
   Progress: 0/20
   Progress: 10/20
   ✅ Category Pass Rate: 95.0% (19/20)

🧪 Testing Category: COMPLETION
   Tests: 20
   ✅ Category Pass Rate: 90.0% (18/20)

🧪 Testing Category: SOCIAL
   Tests: 18
   ✅ Category Pass Rate: 83.3% (15/18)

... [continues for all categories]

================================================================================
🎯 COMPREHENSIVE EVALUATION RESULTS
================================================================================
📊 Overall Performance:
   Total Tests: 487
   ✅ Passed: 412
   ❌ Failed: 75
   🎯 Pass Rate: 84.6%

⏱️ Performance Metrics:
   Total Time: 45.2s
   Avg Test Time: 92.8ms
   Fastest Test: 12.1ms
   Slowest Test: 234.5ms

📈 Category Breakdown:
   ✅ STOP: 95.0% (19/20)
   ✅ COMPLETION: 90.0% (18/20)
   ✅ SOCIAL: 83.3% (15/18)
   ⚠️ VERIFY: 78.9% (15/19)
   ✅ COMPLEX: 88.2% (142/161)
   ✅ FALSE: 100.0% (25/25)
   ⚠️ EARLY: 71.4% (5/7)
   ✅ COMBO: 91.7% (11/12)

🐛 Top Error Types:
   • Expected exit at turn 3, got 2: 23 occurrences
   • Expected exit at turn 2, got -1: 18 occurrences
   • Unexpected exit at turn 1: 12 occurrences

🎖️ Assessment:
   ✅ GOOD: Solid performance with room for minor improvements.
================================================================================

💾 Detailed report saved to: passive_mode_comprehensive_evaluation_20241201_143022.json

💡 Recommendations:
   1. Focus on verify scenarios (lowest pass rate: 78.9%)
   2. Address most common error: Expected exit at turn 3, got 2 (23 occurrences)
   3. Review failed test cases in the detailed report
   4. Consider adjusting exit detection sensitivity
```

## 📋 Test Categories Explained

### Stop Word Tests (`stop_*`)

- Direct "Maya" addressing in various contexts
- Tests case sensitivity and context awareness
- **Expected behavior**: Should always trigger exit

### Completion Phrase Tests (`completion_*`)

- "That's all", "Any questions?", "We're done"
- Tests natural conversation ending detection
- **Expected behavior**: Should trigger exit after instructions

### Social Closing Tests (`social_*`)

- "Good luck", "Take care", "Feel better"
- Tests emotional/social conversation endings
- **Expected behavior**: Should trigger exit (medium confidence)

### Verification Tests (`verify_*`)

- "Did you get that?", "Can you repeat?"
- Tests requests for confirmation/summary
- **Expected behavior**: Should trigger exit for summary

### Complex Tests (`complex_*`)

- 1-15 instructions + various exit signals
- Tests real-world conversation complexity
- **Expected behavior**: Collect all instructions, then exit

### False Positive Tests (`false_pos_*`)

- Greetings, incomplete conversations, casual mentions
- **Expected behavior**: Should NOT trigger exit

### Early Exit Tests (`early_exit_*`)

- Exit signals very early in conversation
- Tests timing sensitivity
- **Expected behavior**: Exit immediately when addressed

### Combination Tests (`combo_*`)

- Multiple exit signals in sequence
- Tests which signal takes precedence
- **Expected behavior**: Exit on first valid signal

## 🔧 Customizing Tests

### Adding New Test Scenarios

Edit `tools/automated_passive_mode_eval.py`:

```python
# Add to _generate_stop_word_variants()
additional_stop_words = [
    "Hey assistant",
    "Computer, are you ready?",
    "AI, can you help?"
]

# Add to _generate_completion_phrases()
additional_completions = [
    "I think we covered everything",
    "That should do it",
    "Nothing else for now"
]
```

### Adjusting Test Parameters

```python
# In ComprehensiveEvaluator.__init__()
# Limit test cases for faster execution
for i, stop_word in enumerate(self.stop_words[:10]):  # Reduced from 20

# Add more instruction categories
if "physical_therapy" in turn["text"].lower():
    session_data.collected_instructions.append({
        "text": turn["text"],
        "type": "therapy"
    })
```

### Custom Confidence Thresholds

```python
# In test case generation
TestCase(
    # ... other parameters ...
    confidence_level=0.75,  # Adjust based on how confident you are
    expected_exit_turn=2,   # When you expect exit to occur
)
```

## 📄 Output Files

### Detailed Report (`passive_mode_comprehensive_evaluation_*.json`)

Contains complete test results:

- Individual test case results
- Conversation logs for each test
- Timing data
- Error details
- Category breakdowns

### Key Fields:

```json
{
  "summary": {
    "total_tests": 487,
    "passed": 412,
    "failed": 75,
    "pass_rate": 84.6
  },
  "category_breakdown": {
    "stop": {"passed": 19, "total": 20, "pass_rate": 95.0}
  },
  "failed_tests": [
    {
      "test_id": "completion_003",
      "error": "Expected exit at turn 2, got 3",
      "expected_exit": 2,
      "actual_exit": 3
    }
  ],
  "detailed_results": [...] // Full test case results
}
```

## 🐛 Troubleshooting

### Environment Issues

**Error**: `No module named 'livekit'`

- **Solution**: Run in LiveKit environment or use `uv run`

**Error**: `No module named 'agent.discharge.agents'`

- **Solution**: Ensure PYTHONPATH includes project root

### Import Errors

**Error**: `Failed to import required components`

- **Solution**: Check that all LiveKit dependencies are installed
- Try: `pip install livekit livekit-agents livekit-plugins-openai`

### Agent Initialization

**Error**: `Failed to initialize real agent session`

- **Solution**: Check that `DischargeAgent` can be instantiated
- Verify no missing configuration or API keys

### Performance Issues

**Issue**: Tests running slowly

- **Solution**: Reduce test case count in `_generate_*` methods
- Focus on specific categories: `python run_passive_mode_eval.py --category stop`

## 🎯 Interpreting Results

### Pass Rate Guidelines:

- **90-100%**: Excellent - production ready
- **80-89%**: Good - minor tuning needed
- **70-79%**: Fair - some improvements required
- **60-69%**: Needs work - significant issues
- **<60%**: Poor - major problems

### Common Failure Patterns:

1. **"Expected exit at turn X, got Y"**: Timing sensitivity
   - **Fix**: Adjust `_should_exit_passive_mode` logic
2. **"Unexpected exit at turn X"**: False positive
   - **Fix**: Make exit detection more specific
3. **"Expected exit at turn X, got -1"**: Missed exit signal
   - **Fix**: Add missing phrases to detection logic

### Performance Metrics:

- **Test time <100ms**: Excellent responsiveness
- **Test time 100-500ms**: Good performance
- **Test time >500ms**: May need optimization

## 🚀 Next Steps

1. **Run the evaluation**: `uv run python run_passive_mode_eval.py`
2. **Analyze results**: Check pass rate and category breakdowns
3. **Fix issues**: Address failed test cases
4. **Iterate**: Re-run evaluation after fixes
5. **Production**: Deploy when pass rate >85%

This testing suite gives you confidence that your passive mode implementation will work reliably in real-world discharge instruction scenarios!
