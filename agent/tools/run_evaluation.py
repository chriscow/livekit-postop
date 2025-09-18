#!/usr/bin/env python3
"""
Evaluation Runner for PostOp AI

Runs evaluation against existing sessions, replaying user messages through the current
agent and comparing results. Automatically flags evaluation sessions in the database.

Usage:
    python run_evaluation.py <source_session_id> [--output-file result.json] [--verbose]

Examples:
    python run_evaluation.py session_1758066459                    # Run eval on specific session
    python run_evaluation.py session_1758066459 --verbose          # Detailed output
    python run_evaluation.py session_1758066459 --output-file eval.json  # Save results
"""

import os
import sys
import json
import asyncio
import argparse
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent directory to path so we can import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from shared.redis_database import get_database, close_database


class EvaluationRunner:
    """Runs evaluations against existing sessions with database tracking"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.database = None

    async def initialize(self):
        """Initialize database connection"""
        self.database = await get_database()

    async def load_source_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load the original session to replay"""
        session_data = await self.database.get_session(session_id)
        if not session_data:
            print(f"❌ Source session '{session_id}' not found in database")
            return None

        if session_data.get('is_evaluation', False):
            print(f"⚠️  Warning: Session '{session_id}' is itself an evaluation run")
            print(f"   Original source: {session_data.get('source_session_id', 'Unknown')}")

        return session_data

    def extract_user_messages(self, transcript: List[Dict]) -> List[str]:
        """Extract user messages from transcript for replay"""
        user_messages = []
        for message in transcript:
            if isinstance(message, dict) and message.get('role') == 'user':
                content = message.get('content', '').strip()
                if content:
                    user_messages.append(content)
        return user_messages

    async def run_chat_evaluation(self, user_messages: List[str], eval_session_id: str) -> Dict[str, Any]:
        """Run the agent evaluation by calling the chat interface directly"""

        if self.verbose:
            print(f"🤖 Running agent evaluation with {len(user_messages)} messages...")

        # Use the existing chat interface by calling it directly
        # We'll capture the output by redirecting stdout
        import subprocess
        import tempfile
        import json

        # Create a temporary file with the user messages
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for message in user_messages:
                f.write(f"{message}\n")
            temp_input_file = f.name

        try:
            # Create a script to feed inputs to the chat interface
            script_content = f'''
import sys
import asyncio
import os

# Add parent directory to path
sys.path.append("{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")

from discharge.agents import run_chat_interface, MockChatSession, DischargeAgent

async def run_eval():
    # Create mock session
    mock_session = MockChatSession("{eval_session_id}")
    agent = DischargeAgent()

    # Monkey patch session methods
    original_say = getattr(agent, '_original_say', None)
    original_generate_reply = getattr(agent, '_original_generate_reply', None)

    # Use the working approach from chat mode - patch session property
    original_session_property = type(agent).session
    def mock_session_property(self):
        return type('MockSession', (), {{
            'userdata': mock_session.userdata,
            'say': mock_session.say,
            'generate_reply': mock_session.generate_reply,
            'output': mock_session.output,
            'on': mock_session.on
        }})()

    type(agent).session = property(mock_session_property)

    try:
        await agent.on_enter()

        # Read messages from file and process
        with open("{temp_input_file}", "r") as f:
            messages = [line.strip() for line in f if line.strip()]

        for i, message in enumerate(messages, 1):
            print(f"user: {{message}}")

            # Create mock message and context
            mock_message = type('MockMessage', (), {{'text_content': message}})()
            mock_context = type('MockContext', (), {{}})()

            try:
                await agent.on_user_turn_completed(mock_context, mock_message)
            except Exception as e:
                print(f"ERROR: {{e}}")

        await agent.on_exit()

        # Output final state as JSON to stderr
        import json
        result = {{
            'collected_instructions': getattr(mock_session.userdata, 'collected_instructions', []),
            'patient_name': getattr(mock_session.userdata, 'patient_name', None),
            'patient_language': getattr(mock_session.userdata, 'patient_language', None),
            'workflow_mode': getattr(mock_session.userdata, 'workflow_mode', None),
            'openai_conversation': getattr(mock_session.userdata, 'openai_conversation', [])
        }}
        print("EVAL_RESULT:" + json.dumps(result), file=sys.stderr)

    finally:
        # Restore original session property
        type(agent).session = original_session_property

if __name__ == "__main__":
    asyncio.run(run_eval())
'''

            # Write the evaluation script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_file = f.name

            # Run the evaluation script
            if self.verbose:
                print("🔧 Running evaluation script...")

            result = subprocess.run([
                'python', script_file
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            # Parse output
            conversation_output = result.stdout.split('\n') if result.stdout else []

            # Extract evaluation result from stderr
            session_userdata = {}
            for line in result.stderr.split('\n'):
                if line.startswith('EVAL_RESULT:'):
                    try:
                        session_userdata = json.loads(line[12:])  # Remove 'EVAL_RESULT:' prefix
                        break
                    except json.JSONDecodeError:
                        pass

            if result.returncode != 0:
                if self.verbose:
                    print(f"⚠️  Script returned non-zero exit code: {result.returncode}")
                    print(f"STDERR: {result.stderr}")

            if self.verbose:
                print(f"✅ Evaluation complete. Collected {len(session_userdata.get('collected_instructions', []))} instructions")

            return {
                'conversation_output': conversation_output,
                'collected_instructions': session_userdata.get('collected_instructions', []),
                'session_userdata': session_userdata
            }

        finally:
            # Clean up temporary files
            try:
                os.unlink(temp_input_file)
                os.unlink(script_file)
            except:
                pass

    async def save_evaluation_session(self, eval_session_id: str, source_session: Dict,
                                     eval_results: Dict, user_messages: List[str]) -> bool:
        """Save evaluation session to database with proper flagging"""

        # Create evaluation metadata
        evaluation_metadata = {
            'evaluation_type': 'session_replay',
            'source_session_id': source_session['session_id'],
            'evaluation_timestamp': datetime.now().isoformat(),
            'user_message_count': len(user_messages),
            'original_instruction_count': len(source_session.get('collected_instructions', [])),
            'evaluation_instruction_count': len(eval_results.get('collected_instructions', [])),
            'agent_version': 'discharge_agent_v1'  # You can make this dynamic
        }

        # Create OpenAI conversation format from results
        transcript = eval_results['session_userdata'].get('openai_conversation', [])

        # Save evaluation session
        success = await self.database.save_session(
            session_id=eval_session_id,
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
            patient_name=eval_results['session_userdata'].get('patient_name'),
            patient_language=eval_results['session_userdata'].get('patient_language'),
            transcript=transcript,
            collected_instructions=eval_results['collected_instructions'],
            is_evaluation=True,
            source_session_id=source_session['session_id'],
            evaluation_metadata=evaluation_metadata
        )

        if success:
            print(f"💾 Evaluation session saved as: {eval_session_id}")
        else:
            print(f"❌ Failed to save evaluation session: {eval_session_id}")

        return success

    def compare_results(self, source_session: Dict, eval_results: Dict) -> Dict[str, Any]:
        """Compare original session with evaluation results"""

        original_instructions = source_session.get('collected_instructions', [])
        eval_instructions = eval_results.get('collected_instructions', [])

        # Extract instruction texts for comparison
        def extract_instruction_texts(instructions):
            texts = []
            for instr in instructions:
                if isinstance(instr, dict):
                    text = instr.get('text', '').strip().lower()
                else:
                    text = str(instr).strip().lower()
                if text:
                    texts.append(text)
            return texts

        original_texts = extract_instruction_texts(original_instructions)
        eval_texts = extract_instruction_texts(eval_instructions)

        # Calculate metrics
        original_set = set(original_texts)
        eval_set = set(eval_texts)

        matched = original_set.intersection(eval_set)
        missed = original_set - eval_set
        extra = eval_set - original_set

        # Calculate scores
        precision = len(matched) / len(eval_set) if eval_set else 0
        recall = len(matched) / len(original_set) if original_set else 1
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        return {
            'instruction_comparison': {
                'original_count': len(original_instructions),
                'evaluation_count': len(eval_instructions),
                'matched_count': len(matched),
                'missed_count': len(missed),
                'extra_count': len(extra),
                'precision': precision,
                'recall': recall,
                'f1_score': f1_score
            },
            'matched_instructions': list(matched),
            'missed_instructions': list(missed),
            'extra_instructions': list(extra),
            'conversation_comparison': {
                'original_message_count': len(source_session.get('transcript', [])),
                'evaluation_message_count': len(eval_results['session_userdata'].get('openai_conversation', []))
            }
        }

    async def run_evaluation(self, source_session_id: str, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Run complete evaluation workflow"""

        print(f"🚀 Starting evaluation for session: {source_session_id}")

        # Load source session
        source_session = await self.load_source_session(source_session_id)
        if not source_session:
            return {'error': 'Source session not found'}

        # Extract user messages
        user_messages = self.extract_user_messages(source_session.get('transcript', []))
        if not user_messages:
            print("⚠️  No user messages found in source session")
            return {'error': 'No user messages to replay'}

        print(f"📋 Found {len(user_messages)} user messages to replay")

        # Generate evaluation session ID
        eval_session_id = f"eval_{source_session_id}_{int(time.time())}"

        # Run evaluation
        eval_results = await self.run_chat_evaluation(user_messages, eval_session_id)

        # Save evaluation session to database
        await self.save_evaluation_session(eval_session_id, source_session, eval_results, user_messages)

        # Compare results
        comparison = self.compare_results(source_session, eval_results)

        # Create final results
        final_results = {
            'evaluation_metadata': {
                'source_session_id': source_session_id,
                'evaluation_session_id': eval_session_id,
                'evaluation_timestamp': datetime.now().isoformat(),
                'user_message_count': len(user_messages)
            },
            'source_session': {
                'session_id': source_session['session_id'],
                'patient_name': source_session.get('patient_name'),
                'patient_language': source_session.get('patient_language'),
                'original_instructions': source_session.get('collected_instructions', [])
            },
            'evaluation_results': eval_results,
            'comparison': comparison
        }

        # Output results
        print(f"\n📊 EVALUATION RESULTS")
        print(f"{'='*50}")
        print(f"Source Session: {source_session_id}")
        print(f"Evaluation Session: {eval_session_id}")
        print(f"User Messages: {len(user_messages)}")
        print(f"Original Instructions: {comparison['instruction_comparison']['original_count']}")
        print(f"Evaluation Instructions: {comparison['instruction_comparison']['evaluation_count']}")
        print(f"Matched: {comparison['instruction_comparison']['matched_count']}")
        print(f"Missed: {comparison['instruction_comparison']['missed_count']}")
        print(f"Extra: {comparison['instruction_comparison']['extra_count']}")
        print(f"Precision: {comparison['instruction_comparison']['precision']:.2%}")
        print(f"Recall: {comparison['instruction_comparison']['recall']:.2%}")
        print(f"F1 Score: {comparison['instruction_comparison']['f1_score']:.2%}")

        if comparison['missed_instructions']:
            print(f"\n⚠️  Missed Instructions:")
            for missed in comparison['missed_instructions']:
                print(f"  - {missed}")

        if comparison['extra_instructions']:
            print(f"\n➕ Extra Instructions:")
            for extra in comparison['extra_instructions']:
                print(f"  + {extra}")

        # Save to file if requested
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(final_results, f, indent=2, default=str)
            print(f"\n💾 Results saved to: {output_file}")

        return final_results


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run evaluation against existing PostOp AI session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s session_1758066459                    Run evaluation on session
  %(prog)s session_1758066459 --verbose          Show detailed progress
  %(prog)s session_1758066459 --output-file results.json  Save results to file
        """
    )

    parser.add_argument(
        "source_session_id",
        help="Source session ID to evaluate against"
    )

    parser.add_argument(
        "--output-file", "-o",
        help="File to save evaluation results (JSON format)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress output"
    )

    args = parser.parse_args()

    # Check database configuration
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL environment variable not set")
        return 1

    # Check OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable not set")
        return 1

    # Run evaluation
    runner = EvaluationRunner(verbose=args.verbose)

    try:
        await runner.initialize()
        results = await runner.run_evaluation(args.source_session_id, args.output_file)

        if 'error' in results:
            print(f"❌ Evaluation failed: {results['error']}")
            return 1

        return 0

    except KeyboardInterrupt:
        print("\n❌ Evaluation interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Evaluation failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    finally:
        await close_database()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))