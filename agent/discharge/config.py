"""
Configuration constants for the PostOp AI system
"""
import os

# Agent Configuration  
AGENT_DISPLAY_NAME = os.getenv("AGENT_NAME", "Vince")  # What the agent calls itself
LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME")   # LiveKit registration name

# Validate LIVEKIT_AGENT_NAME but don't prevent module loading
if not LIVEKIT_AGENT_NAME:
    # Set a default to prevent import errors, but log the issue
    LIVEKIT_AGENT_NAME = "postop-ai-default"
    import warnings
    warnings.warn("LIVEKIT_AGENT_NAME environment variable not set, using default: postop-ai-default")

# Keep AGENT_NAME for backward compatibility (but prefer AGENT_DISPLAY_NAME)
AGENT_NAME = AGENT_DISPLAY_NAME

POSTOP_VOICE_ID = os.getenv("POSTOP_VOICE_ID", "tnSpp4vdxKPjI9w0GnoV")  # ElevenLabs voice ID defaults to Hope
CALLBACK_DELAY_SECONDS = int(os.getenv("CALLBACK_DELAY_SECONDS", "15"))  # Demo delay in seconds
ENABLE_PATIENT_CALLBACK = os.getenv("ENABLE_PATIENT_CALLBACK", "true").lower() == "true"
CONSOLE_TEST_PHONE = "(425) 829-5443"  # Hardcoded phone for console testing

# Redis Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')