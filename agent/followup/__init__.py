"""
Followup package for PostOp AI system

Contains followup-related agents and functionality:
- FollowupAgent: Patient callback and reminder agent
- patient_callback_entrypoint: Main entrypoint for patient callbacks
"""

# Lazy import to avoid livekit dependencies during package import
FollowupAgent = None
patient_callback_entrypoint = None

def __getattr__(name):
    global FollowupAgent, patient_callback_entrypoint
    if name in ['FollowupAgent', 'patient_callback_entrypoint']:
        if FollowupAgent is None:
            from .agents import FollowupAgent as _FollowupAgent, patient_callback_entrypoint as _patient_callback_entrypoint
            globals()['FollowupAgent'] = _FollowupAgent
            globals()['patient_callback_entrypoint'] = _patient_callback_entrypoint
        return globals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    'FollowupAgent',
    'patient_callback_entrypoint'
]