  🧪 Step-by-Step Testing Guide

  Prerequisites

  cd /Users/chris/dev/livekit-postop/agent
  # Ensure you're in the virtual environment
  source .venv/bin/activate  # if needed

  Step 1: Verify Environment

  # Check that required environment variables are set
  python -c "import os; print('✅ DATABASE_URL set' if os.getenv('DATABASE_URL') else '❌ Missing DATABASE_URL')"
  python -c "import os; print('✅ OPENAI_API_KEY set' if os.getenv('OPENAI_API_KEY') else '❌ Missing OPENAI_API_KEY')"

  Step 2: List Available Sessions

  # See what sessions exist in your database
  python tools/list_sessions.py --detailed
  Expected Output:
  Found N recent sessions:

  Session ID                Date/Time           Messages | Patient         Language Instr
  ------------------------------------------------------------------------------------------
  session_1758066459        2025-09-16 16:47:39       17 msgs | Joseph          Italian    2 instr
  test_123                  2025-09-16 16:00:00        1 msgs | John Doe        English    1 instr

  Step 3: View an Original Session

  # Look at the detailed conversation from an original session
  python tools/view_session.py session_1758066459 --compact
  Expected Output:
  ================================================================================
  SESSION DETAILS
  ================================================================================

  Session ID: session_1758066459
  Date/Time: 2025-09-16 16:47:39
  Patient Name: Joseph
  Language: Italian

  CONVERSATION STATISTICS
  ------------------------------
  Total Messages: 17
    Assistant: 6
    System: 1
    Tool: 4
    User: 6
  Tool Calls: 4
  Instructions Collected: 2

  Step 4: Test Interactive Chat Mode

  # Test interactive chat (type a few messages, then type 'quit')
  python -m discharge.agents chat

  What to expect:
  1. Should start with: 💬 Starting PostOp AI Chat Evaluation Mode
  2. Should show: assistant: Hi all! I'm Maya, thanks for dialing me in today...
  3. Should wait for your input with: user: 
  4. Type something like: Hello Maya
  5. Should respond appropriately
  6. Type: quit to exit

  Success criteria: ✅ No "property 'session' object has no setter" errors

  Step 5: Test Session Replay Mode

  # Replay an existing session (replace with actual session ID from step 2)
  python -m discharge.agents chat session_1758066459

  Expected Output:
  💬 Starting PostOp AI Chat Evaluation Mode
  📁 Replaying session: session_1758066459
  Loading session session_1758066459 for replay...
  Loaded session session_1758066459 with 6 user messages
  === SESSION REPLAY STARTED ===
  === CONVERSATION OUTPUT ===
  assistant: Hi all! I'm Maya, thanks for dialing me in today. So Dr. Shah, who do we have in the room today?
  user: We have Joseph, and he speaks Italian.
  user: Super thanks.
  user: Okay, Joseph. Take two Tylenol
  user: Anytime for pain, but no more than, uh,
  user: once every four hours.
  user: Nope. That's it.
  === SESSION REPLAY COMPLETED ===
  Instructions collected: 0

  Success criteria: ✅ Shows conversation replay, no session setter errors

  Step 6: Run Complete Evaluation

  # Run evaluation against an existing session
  python tools/run_evaluation.py session_1758066459 --verbose

  Expected Output:
  🚀 Starting evaluation for session: session_1758066459
  📋 Found 6 user messages to replay
  🤖 Running agent evaluation with 6 messages...
  🔧 Running evaluation script...
  ✅ Evaluation complete. Collected 0 instructions
  💾 Evaluation session saved as: eval_session_1758066459_XXXXXXXXXX

  📊 EVALUATION RESULTS
  ==================================================
  Source Session: session_1758066459
  Evaluation Session: eval_session_1758066459_XXXXXXXXXX
  User Messages: 6
  Original Instructions: 2
  Evaluation Instructions: 0
  Matched: 0
  Missed: 2
  Extra: 0
  Precision: 0.00%
  Recall: 0.00%
  F1 Score: 0.00%

  Success criteria: ✅ Creates evaluation session, shows metrics, no errors

  Step 7: Verify Evaluation Session Was Saved

  # List sessions again to see the new evaluation session
  python tools/list_sessions.py --detailed

  Expected: You should see a new session with ID like eval_session_1758066459_XXXXXXXXXX

  Step 8: View the Evaluation Session Details

  # Replace with the actual evaluation session ID from step 6
  python tools/view_session.py eval_session_1758066459_XXXXXXXXXX --compact

  Expected Output:
  ================================================================================
  SESSION DETAILS
  ================================================================================

  Session ID: eval_session_1758066459_XXXXXXXXXX
  Date/Time: 2025-09-17 XX:XX:XX
  Patient Name: Not specified
  Language: Not specified

  CONVERSATION STATISTICS
  ------------------------------
  Total Messages: 7
    System: 1
    User: 6
  Tool Calls: 0
  Instructions Collected: 0

  CONVERSATION TRANSCRIPT
  ================================================================================

  [SYSTEM] You are Maya, an AI discharge assistant...
  [USER] We have Joseph, and he speaks Italian.
  [USER] Super thanks.
  [USER] Okay, Joseph. Take two Tylenol
  [USER] Anytime for pain, but no more than, uh,
  [USER] once every four hours.
  [USER] Nope. That's it.

  Success criteria: ✅ Shows conversation transcript with 7 messages (not 0!)

  Step 9: Run Comprehensive Test

  # Run the automated comprehensive test
  python tools/final_comprehensive_test.py

  Expected Output:
  🧪 COMPREHENSIVE SCIENTIFIC VERIFICATION
  ======================================================================
  🔬 TEST 1: Session Replay Mode
  ==================================================
  📊 Return code: 0
  📊 Session setter error: ✅ ABSENT

  🔬 TEST 2: Interactive Mode
  ==================================================
  📊 Return code: 0
  📊 Session setter error: ✅ ABSENT

  🔬 TEST 3: Complete Evaluation System
  ==================================================
  📊 Return code: 0
  📊 Evaluation saved: ✅ YES
  📊 Total Messages: 7
  ✅ Evaluation session contains conversation data

  🎉 SCIENTIFIC METHOD: COMPLETE SUCCESS

  Success criteria: ✅ All tests pass, no session setter errors

  ---
  🚨 What to Look For (Failure Signs)

  ❌ "property 'session' of 'DischargeAgent' object has no setter" - This means the fix didn't work
  ❌ "Total Messages: 0" in evaluation sessions - Conversation capture failing
  ❌ Process hangs or crashes - Code issues
  ❌ "No sessions found" - Database connection problems

  🎯 Success Indicators

  ✅ Interactive chat responds to input
  ✅ Session replay shows conversation✅ Evaluation creates new sessions with conversation data
  ✅ All tests pass without session setter errors

  Try each step in order and let me know where (if anywhere) you encounter issues!