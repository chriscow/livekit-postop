#!/usr/bin/env python3
"""
Runner script for comprehensive passive mode evaluation.
Run this from the agent directory with: uv run python run_passive_mode_eval.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the tools directory to Python path (relative to current directory)
tools_dir = Path(__file__).parent / "tools"
sys.path.insert(0, str(tools_dir))

# Ensure current directory is in path for discharge imports
sys.path.insert(0, str(Path(__file__).parent))

def check_environment():
    """Check if we're in the right environment"""
    try:
        # Test imports that should be available
        import livekit
        import livekit.agents
        from discharge.agents import DischargeAgent
        print("✅ Environment check passed - LiveKit and DischargeAgent available")
        return True
    except ImportError as e:
        print(f"❌ Environment check failed: {e}")
        print("\nPlease run this with uv from the agent directory:")
        print("1. cd /Users/chris/dev/livekit-postop/agent")
        print("2. Run: uv run python run_passive_mode_eval.py")
        print("\nNote: This needs the same environment as your main agent")
        return False

def load_env_file():
    """Load environment variables from .env file"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print(f"📄 Loading environment variables from {env_file}")
        # Load .env file using python-dotenv if available, otherwise skip
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print("✅ Environment variables loaded successfully")
            return True
        except ImportError:
            print("⚠️ python-dotenv not available - environment variables not loaded")
            print("   The test may fail if API keys are missing")
            print("   Run with: set -a; source .env; set +a; uv run python run_passive_mode_eval.py")
            return False
    else:
        print("⚠️ No .env file found - using system environment variables only")
        return True

async def main():
    """Main runner"""
    print("🚀 Discharge Agent Passive Mode Evaluation Runner")
    print("=" * 60)
    
    # Load environment variables first
    load_env_file()
    
    # Check environment 
    if not check_environment():
        return 1
    
    try:
        # Import and run the real LiveKit integration test
        from tools.real_livekit_passive_mode_eval import main as eval_main
        
        print("🔧 Starting comprehensive automated evaluation...")
        await eval_main()
        
        print("\n✅ Evaluation completed successfully!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️ Evaluation interrupted by user")
        sys.exit(130)