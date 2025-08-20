"""
LiveKit API Adapter - Abstracts LiveKit API calls for easier testing

This adapter separates the LiveKit API calls from business logic,
making the code more testable by allowing easy mocking of the adapter
instead of the entire LiveKit API.
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from livekit import api

logger = logging.getLogger("livekit-adapter")


@dataclass
class AgentDispatchRequest:
    """Request to create an agent dispatch"""
    agent_name: str
    room_name: str
    metadata: Dict[str, Any]


@dataclass
class SipCallRequest:
    """Request to make a SIP call"""
    room_name: str
    trunk_id: str
    phone_number: str
    participant_identity: str


@dataclass
class CallResult:
    """Result of a call attempt"""
    success: bool
    room_name: str
    participant_identity: Optional[str] = None
    dispatch_id: Optional[str] = None
    sip_participant_id: Optional[str] = None
    error_message: Optional[str] = None
    sip_status_code: Optional[str] = None
    sip_status_text: Optional[str] = None
    retryable: bool = True


class LiveKitAdapter(ABC):
    """Abstract interface for LiveKit operations"""
    
    @abstractmethod
    async def create_agent_dispatch(self, request: AgentDispatchRequest) -> str:
        """Create an agent dispatch and return dispatch ID"""
        pass
    
    @abstractmethod
    async def create_sip_participant(self, request: SipCallRequest) -> str:
        """Create SIP participant and return participant ID"""
        pass


class RealLiveKitAdapter(LiveKitAdapter):
    """Real implementation using LiveKit API"""
    
    async def create_agent_dispatch(self, request: AgentDispatchRequest) -> str:
        """Create an agent dispatch using real LiveKit API"""
        lkapi = api.LiveKitAPI()
        try:
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=request.agent_name,
                    room=request.room_name,
                    metadata=json.dumps(request.metadata)
                )
            )
            dispatch_id = getattr(dispatch, 'id', None)
            logger.info(f"Created agent dispatch {dispatch_id} for room {request.room_name}")
            return dispatch_id
        finally:
            await lkapi.aclose()
    
    async def create_sip_participant(self, request: SipCallRequest) -> str:
        """Create SIP participant using real LiveKit API"""
        lkapi = api.LiveKitAPI()
        try:
            participant = await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=request.room_name,
                    sip_trunk_id=request.trunk_id,
                    sip_call_to=request.phone_number,
                    participant_identity=request.participant_identity,
                    wait_until_answered=True,
                )
            )
            participant_id = getattr(participant, 'participant_id', None)
            logger.info(f"Created SIP participant {participant_id} in room {request.room_name}")
            return participant_id
        finally:
            await lkapi.aclose()


class MockLiveKitAdapter(LiveKitAdapter):
    """Mock implementation for testing"""
    
    def __init__(self):
        self.dispatches_created = []
        self.participants_created = []
        self.should_fail = False
        self.failure_error = None
        self.failure_sip_code = None
        self.fail_on_dispatch = False  # Allow controlling which operation fails
        
    async def create_agent_dispatch(self, request: AgentDispatchRequest) -> str:
        """Mock agent dispatch creation"""
        if self.should_fail and self.fail_on_dispatch:
            raise Exception(self.failure_error or "Mock dispatch failure")
        
        dispatch_id = f"mock-dispatch-{len(self.dispatches_created) + 1}"
        self.dispatches_created.append({
            'id': dispatch_id,
            'agent_name': request.agent_name,
            'room_name': request.room_name,
            'metadata': request.metadata
        })
        return dispatch_id
    
    async def create_sip_participant(self, request: SipCallRequest) -> str:
        """Mock SIP participant creation"""
        if self.should_fail and not self.fail_on_dispatch:
            if self.failure_sip_code:
                # Simulate SIP error
                class MockTwirpError(Exception):
                    def __init__(self, message, metadata):
                        self.message = message
                        self.metadata = metadata
                        super().__init__(message)
                
                raise MockTwirpError(
                    self.failure_error or "SIP error",
                    {
                        'sip_status_code': self.failure_sip_code,
                        'sip_status': 'Mock SIP Error'
                    }
                )
            else:
                raise Exception(self.failure_error or "Mock participant failure")
        
        participant_id = f"mock-participant-{len(self.participants_created) + 1}"
        self.participants_created.append({
            'id': participant_id,
            'room_name': request.room_name,
            'trunk_id': request.trunk_id,
            'phone_number': request.phone_number,
            'participant_identity': request.participant_identity
        })
        return participant_id
    
    def reset(self):
        """Reset mock state"""
        self.dispatches_created.clear()
        self.participants_created.clear()
        self.should_fail = False
        self.failure_error = None
        self.failure_sip_code = None
        self.fail_on_dispatch = False


def create_livekit_adapter(mock: bool = False) -> LiveKitAdapter:
    """Factory function to create LiveKit adapter"""
    if mock:
        return MockLiveKitAdapter()
    return RealLiveKitAdapter()