#!/usr/bin/env python3
"""
Session Viewer Tool for PostOp AI

Displays detailed session information with colorized conversation formatting.
Perfect for reviewing agent conversations and debugging tool interactions.

Usage:
    python view_session.py <session_id> [--no-color] [--compact]

Examples:
    python view_session.py session_1737151802          # Full colorized view
    python view_session.py session_1737151802 --compact # Compact format
    python view_session.py session_1737151802 --no-color # Plain text
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime
from typing import Optional, Dict, List, Any

# Add parent directory to path so we can import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from shared.redis_database import get_database, close_database


# ANSI Color Codes
class Colors:
    """ANSI color codes for terminal output"""
    # Role colors
    USER = '\033[93m'        # Yellow - user messages
    ASSISTANT = '\033[96m'   # Cyan - assistant messages
    SYSTEM = '\033[95m'      # Magenta - system messages
    TOOL = '\033[94m'        # Blue - tool calls and responses

    # Accent colors
    METADATA = '\033[92m'    # Green - metadata headers
    ERROR = '\033[91m'       # Red - errors
    TIMESTAMP = '\033[90m'   # Gray - timestamps

    # Formatting
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'

    # Boxes and separators
    SEPARATOR = '\033[90m'   # Gray for lines/boxes


def colorize(text: str, color: str, use_color: bool = True) -> str:
    """Apply color to text if color is enabled"""
    if not use_color:
        return text
    return f"{color}{text}{Colors.RESET}"


def format_timestamp(timestamp_str: str, created_at: Optional[datetime] = None) -> str:
    """Format timestamp to human-readable string"""
    try:
        if timestamp_str and len(timestamp_str) >= 13:
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass

    if created_at:
        return created_at.strftime("%Y-%m-%d %H:%M:%S")

    return "Unknown"


def print_session_metadata(session: Dict[str, Any], use_color: bool = True):
    """Print formatted session metadata"""
    session_id = session.get("session_id", "Unknown")
    timestamp_str = session.get("timestamp", "")
    created_at = session.get("created_at")
    patient_name = session.get("patient_name") or "Not specified"
    patient_language = session.get("patient_language") or "Not specified"

    # Calculate statistics
    transcript = session.get("transcript", [])
    instructions = session.get("collected_instructions", [])

    message_counts = {}
    tool_call_count = 0

    for msg in transcript:
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            message_counts[role] = message_counts.get(role, 0) + 1

            # Count tool calls
            if role == "assistant" and msg.get("tool_calls"):
                tool_call_count += len(msg["tool_calls"])

    formatted_time = format_timestamp(timestamp_str, created_at)

    # Print header
    print(colorize("=" * 80, Colors.SEPARATOR, use_color))
    print(colorize("SESSION DETAILS", Colors.METADATA + Colors.BOLD, use_color))
    print(colorize("=" * 80, Colors.SEPARATOR, use_color))
    print()

    # Session info
    print(f"{colorize('Session ID:', Colors.METADATA, use_color)} {session_id}")
    print(f"{colorize('Date/Time:', Colors.METADATA, use_color)} {colorize(formatted_time, Colors.TIMESTAMP, use_color)}")
    print(f"{colorize('Patient Name:', Colors.METADATA, use_color)} {patient_name}")
    print(f"{colorize('Language:', Colors.METADATA, use_color)} {patient_language}")
    print()

    # Statistics
    print(colorize("CONVERSATION STATISTICS", Colors.METADATA + Colors.BOLD, use_color))
    print(colorize("-" * 30, Colors.SEPARATOR, use_color))
    print(f"{colorize('Total Messages:', Colors.METADATA, use_color)} {len(transcript)}")

    for role, count in sorted(message_counts.items()):
        role_color = {
            'user': Colors.USER,
            'assistant': Colors.ASSISTANT,
            'system': Colors.SYSTEM,
            'tool': Colors.TOOL
        }.get(role, Colors.RESET)
        print(f"  {colorize(f'{role.title()}:', role_color, use_color)} {count}")

    print(f"{colorize('Tool Calls:', Colors.TOOL, use_color)} {tool_call_count}")
    print(f"{colorize('Instructions Collected:', Colors.METADATA, use_color)} {len(instructions)}")
    print()


def format_message_content(content: str, max_width: int = 80) -> str:
    """Format message content with word wrapping"""
    if not content:
        return ""

    # Simple word wrapping
    words = content.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        if current_length + len(word) + 1 <= max_width:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)


def print_tool_calls(tool_calls: List[Dict], use_color: bool = True, compact: bool = False):
    """Print formatted tool calls"""
    for i, tool_call in enumerate(tool_calls):
        tool_id = tool_call.get("id", "unknown")
        function_name = tool_call.get("function", {}).get("name", "unknown")
        arguments = tool_call.get("function", {}).get("arguments", "{}")

        if compact:
            print(f"    {colorize(f'[TOOL {i+1}]', Colors.TOOL + Colors.BOLD, use_color)} {function_name}")
        else:
            print(f"  {colorize('┌─', Colors.TOOL, use_color)} {colorize(f'Tool Call #{i+1}', Colors.TOOL + Colors.BOLD, use_color)}")
            print(f"  {colorize('├─', Colors.TOOL, use_color)} {colorize('Function:', Colors.TOOL, use_color)} {function_name}")
            print(f"  {colorize('├─', Colors.TOOL, use_color)} {colorize('ID:', Colors.TOOL, use_color)} {tool_id}")

            # Pretty print arguments if they're JSON
            try:
                args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
                if args_dict:
                    print(f"  {colorize('└─', Colors.TOOL, use_color)} {colorize('Args:', Colors.TOOL, use_color)}")
                    for key, value in args_dict.items():
                        print(f"      {colorize(f'{key}:', Colors.TOOL, use_color)} {value}")
                else:
                    print(f"  {colorize('└─', Colors.TOOL, use_color)} {colorize('Args:', Colors.TOOL, use_color)} (none)")
            except (json.JSONDecodeError, TypeError):
                print(f"  {colorize('└─', Colors.TOOL, use_color)} {colorize('Args:', Colors.TOOL, use_color)} {arguments}")


def print_conversation(transcript: List[Dict], use_color: bool = True, compact: bool = False):
    """Print formatted conversation with colors"""
    print(colorize("CONVERSATION TRANSCRIPT", Colors.METADATA + Colors.BOLD, use_color))
    print(colorize("=" * 80, Colors.SEPARATOR, use_color))
    print()

    if not transcript:
        print(colorize("(No conversation messages found)", Colors.DIM, use_color))
        return

    for i, message in enumerate(transcript):
        if not isinstance(message, dict):
            continue

        role = message.get("role", "unknown")
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        tool_call_id = message.get("tool_call_id")

        # Determine role color and prefix
        role_info = {
            'user': (Colors.USER, "👤 USER"),
            'assistant': (Colors.ASSISTANT, "🤖 ASSISTANT"),
            'system': (Colors.SYSTEM, "⚙️  SYSTEM"),
            'tool': (Colors.TOOL, "🔧 TOOL")
        }.get(role, (Colors.RESET, f"❓ {role.upper()}"))

        role_color, role_prefix = role_info

        # Print message header
        if compact:
            prefix = colorize(f"[{role.upper()}]", role_color + Colors.BOLD, use_color)
            if content.strip():
                formatted_content = format_message_content(content, max_width=70)
                # Indent continuation lines
                lines = formatted_content.split('\n')
                print(f"{prefix} {lines[0]}")
                for line in lines[1:]:
                    print(f"{'':9} {line}")
            elif tool_calls:
                print(f"{prefix} <tool calls>")
            elif tool_call_id:
                print(f"{prefix} <tool response>")
            else:
                print(f"{prefix} <empty>")
        else:
            print(f"{colorize('┌─', Colors.SEPARATOR, use_color)} {colorize(role_prefix, role_color + Colors.BOLD, use_color)}")

            if content.strip():
                formatted_content = format_message_content(content, max_width=76)
                for line in formatted_content.split('\n'):
                    print(f"{colorize('│', Colors.SEPARATOR, use_color)}  {line}")

            if tool_calls:
                print(f"{colorize('├─', Colors.SEPARATOR, use_color)} {colorize('Tool Calls:', Colors.TOOL + Colors.BOLD, use_color)}")
                print_tool_calls(tool_calls, use_color, compact)

            if tool_call_id:
                print(f"{colorize('├─', Colors.SEPARATOR, use_color)} {colorize('Tool Response ID:', Colors.TOOL, use_color)} {tool_call_id}")

            if not content.strip() and not tool_calls and not tool_call_id:
                print(f"{colorize('│', Colors.SEPARATOR, use_color)}  {colorize('(empty message)', Colors.DIM, use_color)}")

            print(f"{colorize('└─', Colors.SEPARATOR, use_color)}")

        print()


def print_collected_instructions(instructions: List[Dict], use_color: bool = True):
    """Print collected discharge instructions"""
    if not instructions:
        return

    print(colorize("COLLECTED INSTRUCTIONS", Colors.METADATA + Colors.BOLD, use_color))
    print(colorize("=" * 80, Colors.SEPARATOR, use_color))
    print()

    for i, instruction in enumerate(instructions, 1):
        if isinstance(instruction, dict):
            text = instruction.get("text", "")
            timestamp = instruction.get("timestamp", "")
            instr_type = instruction.get("type", "general")
        else:
            text = str(instruction)
            timestamp = ""
            instr_type = "general"

        print(f"{colorize(f'{i:2d}.', Colors.METADATA, use_color)} {text}")
        if timestamp:
            ts_formatted = timestamp.split('T')[0] + ' ' + timestamp.split('T')[1][:8] if 'T' in timestamp else timestamp
            print(f"     {colorize(f'[{ts_formatted}]', Colors.TIMESTAMP + Colors.DIM, use_color)}")
        print()


async def view_session(session_id: str, use_color: bool = True, compact: bool = False):
    """View a complete session with formatted output"""
    try:
        # Get database connection
        db = await get_database()

        # Fetch session data
        session = await db.get_session(session_id)

        if not session:
            print(colorize(f"ERROR: Session '{session_id}' not found in database", Colors.ERROR, use_color))
            return 1

        # Print session metadata
        print_session_metadata(session, use_color)

        # Print conversation
        transcript = session.get("transcript", [])
        print_conversation(transcript, use_color, compact)

        # Print collected instructions
        instructions = session.get("collected_instructions", [])
        if instructions:
            print_collected_instructions(instructions, use_color)

        return 0

    except Exception as e:
        print(colorize(f"Error viewing session: {e}", Colors.ERROR, use_color), file=sys.stderr)
        return 1

    finally:
        await close_database()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="View PostOp AI session with colorized conversation formatting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s session_1737151802          View session with full formatting
  %(prog)s session_1737151802 --compact Use compact display format
  %(prog)s session_1737151802 --no-color Plain text output (no colors)

Color Legend:
  Yellow   - User messages
  Cyan     - Assistant messages
  Magenta  - System messages
  Blue     - Tool calls and responses
  Green    - Metadata headers
        """
    )

    parser.add_argument(
        "session_id",
        help="Session ID to view (e.g., session_1737151802)"
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colorized output"
    )

    parser.add_argument(
        "--compact", "-c",
        action="store_true",
        help="Use compact display format"
    )

    args = parser.parse_args()

    # Check if we should use colors (disabled if piping or --no-color)
    use_color = not args.no_color and sys.stdout.isatty()

    # Validate session ID format
    if not args.session_id:
        print(colorize("Error: Session ID is required", Colors.ERROR, use_color), file=sys.stderr)
        return 1

    # Check database configuration
    if not os.getenv("REDIS_URL"):
        print(colorize("Error: REDIS_URL environment variable not set", Colors.ERROR, use_color), file=sys.stderr)
        return 1

    # View the session
    try:
        return asyncio.run(view_session(args.session_id, use_color, args.compact))
    except KeyboardInterrupt:
        print(colorize("\nInterrupted by user", Colors.ERROR, use_color), file=sys.stderr)
        return 1
    except Exception as e:
        print(colorize(f"Unexpected error: {e}", Colors.ERROR, use_color), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())