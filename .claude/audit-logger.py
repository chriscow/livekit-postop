#!/usr/bin/env python3
"""
Claude Code Audit Logger
Logs all user interactions, tool calls, responses, and system events for audit trail.
"""

import os
import sys
import json
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class AuditLogger:
    def __init__(self):
        self.project_dir = Path(os.getenv('CLAUDE_PROJECT_DIR', '.'))
        self.log_dir = self.project_dir / '.claude' / 'logs'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create daily log file
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        self.log_file = self.log_dir / f'audit-{today}.log'
        
        # Hook type from environment variable
        self.hook_type = os.getenv('CLAUDE_HOOK_TYPE', 'unknown')
        
    def get_timestamp(self) -> str:
        """Get formatted timestamp."""
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    def get_event_indicator(self, hook_type: str, data: Dict[str, Any] = None) -> str:
        """Get human-readable event indicator based on hook type."""
        indicators = {
            'UserPromptSubmit': '🗨️  [USER-INPUT]',
            'PreToolUse': '🔧 [TOOL-START]',
            'PostToolUse': '✅ [TOOL-COMPLETE]',
            'Stop': '🏁 [RESPONSE-END]',
            'SubagentStop': '🤖 [SUBAGENT-END]',
            'Notification': '🔔 [NOTIFICATION]',
            'SessionStart': '🚀 [SESSION-START]',
            'SessionEnd': '🛑 [SESSION-END]',
            'PreCompact': '🗜️  [PRE-COMPACT]'
        }
        
        base_indicator = indicators.get(hook_type, f'❓ [{hook_type.upper()}]')
        
        # Add subagent name if available
        if hook_type == 'SubagentStop' and data:
            subagent_name = data.get('subagent_type', 'unknown')
            base_indicator = f'🤖 [SUBAGENT-{subagent_name.upper()}-END]'
        elif hook_type == 'PreToolUse' and data:
            tool_name = data.get('tool_name', 'unknown')
            base_indicator = f'🔧 [TOOL-START:{tool_name.upper()}]'
        elif hook_type == 'PostToolUse' and data:
            tool_name = data.get('tool_name', 'unknown')
            base_indicator = f'✅ [TOOL-COMPLETE:{tool_name.upper()}]'
            
        return base_indicator
    
    def format_tool_data(self, data: Dict[str, Any]) -> str:
        """Format tool-specific data for logging."""
        if not data:
            return ""
            
        formatted_parts = []
        
        # Tool name and parameters
        if 'tool_name' in data:
            formatted_parts.append(f"Tool: {data['tool_name']}")
            
        if 'parameters' in data and data['parameters']:
            formatted_parts.append("Parameters:")
            for key, value in data['parameters'].items():
                # Truncate very long values
                str_value = str(value)
                if len(str_value) > 200:
                    str_value = str_value[:200] + "... [TRUNCATED]"
                formatted_parts.append(f"  {key}: {str_value}")
        
        # Tool results/output
        if 'result' in data:
            result = data['result']
            if isinstance(result, str) and len(result) > 500:
                result = result[:500] + "... [TRUNCATED]"
            formatted_parts.append(f"Result: {result}")
            
        if 'error' in data:
            formatted_parts.append(f"Error: {data['error']}")
            
        return "\n".join(formatted_parts) if formatted_parts else ""
    
    def format_user_input(self, data: Dict[str, Any]) -> str:
        """Format user input data for logging."""
        if not data:
            return ""
            
        formatted_parts = []
        
        if 'prompt' in data:
            prompt = data['prompt']
            if len(prompt) > 1000:
                prompt = prompt[:1000] + "... [TRUNCATED]"
            formatted_parts.append(f"User Message: {prompt}")
            
        if 'files' in data and data['files']:
            formatted_parts.append(f"Attached Files: {', '.join(data['files'])}")
            
        return "\n".join(formatted_parts) if formatted_parts else ""
    
    def format_response_data(self, data: Dict[str, Any]) -> str:
        """Format response data for logging."""
        if not data:
            return ""
            
        formatted_parts = []
        
        if 'response' in data:
            response = data['response']
            if len(response) > 1000:
                response = response[:1000] + "... [TRUNCATED]"
            formatted_parts.append(f"Response: {response}")
            
        if 'thinking' in data:
            thinking = data['thinking']
            if len(thinking) > 500:
                thinking = thinking[:500] + "... [TRUNCATED]"
            formatted_parts.append(f"Thinking: {thinking}")
            
        return "\n".join(formatted_parts) if formatted_parts else ""
    
    def log_event(self, hook_type: str, data: Dict[str, Any] = None):
        """Log a single event with proper formatting."""
        timestamp = self.get_timestamp()
        indicator = self.get_event_indicator(hook_type, data)
        
        # Build log entry
        log_entry = f"\n{timestamp} {indicator}\n"
        log_entry += "=" * 80 + "\n"
        
        # Format data based on hook type
        if hook_type == 'UserPromptSubmit':
            content = self.format_user_input(data)
        elif hook_type in ['PreToolUse', 'PostToolUse']:
            content = self.format_tool_data(data)
        elif hook_type in ['Stop', 'SubagentStop']:
            content = self.format_response_data(data)
        else:
            # Generic formatting for other hook types
            content = json.dumps(data, indent=2) if data else "No additional data"
        
        if content:
            log_entry += content + "\n"
            
        log_entry += "=" * 80 + "\n"
        
        # Write to log file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # Also write to stderr for immediate visibility (optional)
        print(f"{timestamp} {indicator}", file=sys.stderr)

def main():
    """Main entry point for the audit logger."""
    logger = AuditLogger()
    
    # Get hook type from environment
    hook_type = logger.hook_type
    
    # Try to read data from stdin (JSON format)
    data = None
    try:
        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read().strip()
            if stdin_content:
                data = json.loads(stdin_content)
    except (json.JSONDecodeError, Exception) as e:
        # If we can't parse JSON, log the raw content
        data = {"raw_input": stdin_content if 'stdin_content' in locals() else "", "parse_error": str(e)}
    
    # Also check for data in environment variables (Claude may pass data this way)
    env_data = {}
    for key, value in os.environ.items():
        if key.startswith('CLAUDE_HOOK_'):
            env_data[key] = value
    
    if env_data:
        if data is None:
            data = {}
        data.update(env_data)
    
    # Log the event
    logger.log_event(hook_type, data)

if __name__ == '__main__':
    main()