"""
Configuration constants for the PostOp AI system
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
# Look for .env in the agent directory (parent of this discharge directory)
current_file_dir = os.path.dirname(__file__)  # discharge/
agent_dir = os.path.dirname(current_file_dir)  # agent/
dotenv_path = os.path.join(agent_dir, '.env')
env_loaded = load_dotenv(dotenv_path)

# Debug logging for environment loading
import logging
logger = logging.getLogger("postop-agent")
logger.info(f"Environment loading: .env path={dotenv_path}, exists={os.path.exists(dotenv_path)}, loaded={env_loaded}")

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
logger.info(f"Redis URL configured: {REDIS_URL[:50]}..." if REDIS_URL.startswith('redis://') else f"Redis URL: {REDIS_URL}")