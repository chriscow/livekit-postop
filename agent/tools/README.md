# PostOp AI Tools

This directory contains utility scripts for the PostOp AI discharge agent system.

## Available Tools

### `list_sessions.py` - Session Database Browser

Lists database sessions with human-readable timestamps and message counts, ordered by most recent first. Perfect for finding sessions to replay in chat evaluation mode.

#### Usage

```bash
# List 20 most recent sessions (default)
python list_sessions.py

# List 50 most recent sessions
python list_sessions.py --limit 50

# Show detailed info including patient names and instruction counts
python list_sessions.py --detailed

# Combine options
python list_sessions.py --limit 100 --detailed
```

#### Example Output

**Basic mode:**
```
Found 12 recent sessions:

Session ID                Date/Time           Messages
-------------------------------------------------------
session_1737151802        2025-01-17 14:30:22       15 msgs
session_1737148234        2025-01-17 13:30:34       23 msgs
session_1737144567        2025-01-17 12:22:47        8 msgs
```

**Detailed mode:**
```
Found 12 recent sessions:

Session ID                Date/Time           Messages | Patient         Language   Instr
----------------------------------------------------------------------------------------
session_1737151802        2025-01-17 14:30:22       15 msgs | John Smith      English      3 instr
session_1737148234        2025-01-17 13:30:34       23 msgs | Maria Garcia    Spanish      5 instr
session_1737144567        2025-01-17 12:22:47        8 msgs | Unknown         English      0 instr
```

#### Integration with Chat Mode

Use the session IDs from this tool to replay sessions in chat evaluation mode:

```bash
# First, find interesting sessions
python tools/list_sessions.py --limit 10

# Then replay a specific session
python agents.py chat session_1737151802
```

### `view_session.py` - Detailed Session Viewer

Displays comprehensive session information with beautifully formatted, colorized conversation output. Perfect for reviewing agent conversations, debugging tool interactions, and understanding conversation flow.

#### Usage

```bash
# View session with full colorized formatting
python view_session.py session_1737151802

# Compact format for quick scanning
python view_session.py session_1737151802 --compact

# Plain text output (no colors) - good for piping
python view_session.py session_1737151802 --no-color
```

#### Color Legend

- 🟡 **Yellow** - User messages
- 🔵 **Cyan** - Assistant messages
- 🟣 **Magenta** - System messages
- 🔷 **Blue** - Tool calls and responses
- 🟢 **Green** - Metadata headers
- ⚫ **Gray** - Timestamps and separators

#### Example Output

```
================================================================================
SESSION DETAILS
================================================================================

Session ID: session_1737151802
Date/Time: 2025-01-17 14:30:22
Patient Name: John Smith
Language: English

CONVERSATION STATISTICS
------------------------------
Total Messages: 15
  User: 7
  Assistant: 6
  System: 1
  Tool: 1
Tool Calls: 3
Instructions Collected: 2

CONVERSATION TRANSCRIPT
================================================================================

┌─ ⚙️  SYSTEM
│  You are Maya, an AI discharge assistant...
└─

┌─ 👤 USER
│  Hello, I'm Dr. Smith and this is patient John
└─

┌─ 🤖 ASSISTANT
├─ Tool Calls:
  ┌─ Tool Call #1
  ├─ Function: extract_patient_info
  ├─ ID: call_abc123
  └─ Args:
      patient_name: John
└─

┌─ 🔧 TOOL
│  Extracted: Patient name: John
└─
```

#### Features

✅ **Complete session metadata** - timestamps, patient info, statistics
✅ **Colorized conversation** - distinct colors for each role
✅ **Tool call visualization** - formatted function calls with arguments
✅ **Instruction summary** - collected discharge instructions
✅ **Flexible formatting** - compact and detailed modes
✅ **Smart color detection** - auto-disables colors when piping output

#### Integration Workflow

```bash
# 1. Find interesting sessions
python tools/list_sessions.py --detailed

# 2. View detailed session content
python tools/view_session.py session_1737151802

# 3. Replay session for evaluation
python agents.py chat session_1737151802
```

#### Requirements

- PostgreSQL database configured with `DATABASE_URL` environment variable
- Access to the PostOp AI shared modules
- Python 3.8+ with asyncpg

#### Error Handling

The script handles common issues gracefully:
- Missing `DATABASE_URL` environment variable
- Database connection failures
- Empty session database
- Malformed timestamp data (falls back to database timestamps)

For debugging database connection issues, check that your `DATABASE_URL` is properly formatted:
```
DATABASE_URL=postgresql://user:password@host:port/database
```