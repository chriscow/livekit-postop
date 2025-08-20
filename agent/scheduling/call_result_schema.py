"""
Standardized result schema for call execution

Provides consistent data structures for call execution results
to simplify retry logic and error handling across the system.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum


class CallResultCategory(Enum):
    """Categories of call execution results"""
    SUCCESS = "success"
    NETWORK_ERROR = "network_error" 
    SIP_ERROR = "sip_error"
    SYSTEM_ERROR = "system_error"
    PATIENT_ERROR = "patient_error"  # No answer, busy, declined


class CallRetryability(Enum):
    """Whether a call failure should be retried"""
    RETRYABLE = "retryable"
    NOT_RETRYABLE = "not_retryable"
    MAX_ATTEMPTS_REACHED = "max_attempts_reached"


@dataclass
class CallExecutionResult:
    """
    Standardized result from call execution
    
    This provides a consistent interface between call executors
    and retry logic, regardless of the underlying telephony system.
    """
    success: bool
    category: CallResultCategory
    retryability: CallRetryability
    message: str
    
    # SIP-specific information
    sip_status_code: Optional[str] = None
    sip_status_text: Optional[str] = None
    
    # Call execution details
    room_name: Optional[str] = None
    participant_identity: Optional[str] = None
    call_duration_seconds: Optional[int] = None
    
    # Error information
    error_details: Optional[Dict[str, Any]] = None
    
    # Retry guidance
    suggested_retry_delay_seconds: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success,
            "category": self.category.value,
            "retryability": self.retryability.value,
            "message": self.message
        }
        
        # Add optional fields if present
        if self.sip_status_code:
            result["sip_status_code"] = self.sip_status_code
        if self.sip_status_text:
            result["sip_status_text"] = self.sip_status_text
        if self.room_name:
            result["room_name"] = self.room_name
        if self.participant_identity:
            result["participant_identity"] = self.participant_identity
        if self.call_duration_seconds:
            result["call_duration_seconds"] = self.call_duration_seconds
        if self.error_details:
            result["error_details"] = self.error_details
        if self.suggested_retry_delay_seconds:
            result["suggested_retry_delay_seconds"] = self.suggested_retry_delay_seconds
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallExecutionResult":
        """Create from dictionary"""
        return cls(
            success=data["success"],
            category=CallResultCategory(data["category"]),
            retryability=CallRetryability(data["retryability"]),
            message=data["message"],
            sip_status_code=data.get("sip_status_code"),
            sip_status_text=data.get("sip_status_text"),
            room_name=data.get("room_name"),
            participant_identity=data.get("participant_identity"),
            call_duration_seconds=data.get("call_duration_seconds"),
            error_details=data.get("error_details"),
            suggested_retry_delay_seconds=data.get("suggested_retry_delay_seconds")
        )
    
    def should_retry(self, attempt_count: int, max_attempts: int) -> bool:
        """
        Determine if this result indicates the call should be retried
        
        Args:
            attempt_count: Current attempt number
            max_attempts: Maximum allowed attempts
            
        Returns:
            True if the call should be retried
        """
        if attempt_count >= max_attempts:
            return False
        
        return self.retryability == CallRetryability.RETRYABLE
    
    def get_retry_delay(self, attempt_count: int) -> int:
        """
        Get suggested retry delay in seconds
        
        Args:
            attempt_count: Current attempt number
            
        Returns:
            Delay in seconds before retry
        """
        if self.suggested_retry_delay_seconds:
            return self.suggested_retry_delay_seconds
        
        # Default exponential backoff based on category
        if self.category == CallResultCategory.NETWORK_ERROR:
            # Network errors: 5m, 15m, 30m
            delays = [300, 900, 1800]
        elif self.category == CallResultCategory.SIP_ERROR:
            # SIP errors: 2m, 10m, 20m  
            delays = [120, 600, 1200]
        elif self.category == CallResultCategory.PATIENT_ERROR:
            # Patient errors (busy, no answer): 10m, 30m, 60m
            delays = [600, 1800, 3600]
        else:
            # System errors: 1m, 5m, 15m
            delays = [60, 300, 900]
        
        return delays[min(attempt_count - 1, len(delays) - 1)]
    
    def get_human_readable_summary(self) -> str:
        """Get a human-readable summary of the call result"""
        if self.success:
            duration_text = ""
            if self.call_duration_seconds:
                minutes = self.call_duration_seconds // 60
                seconds = self.call_duration_seconds % 60
                duration_text = f" ({minutes}m {seconds}s)"
            
            return f"Call completed successfully{duration_text}"
        
        # Handle different error categories
        if self.category == CallResultCategory.SIP_ERROR and self.sip_status_code:
            status_meanings = {
                '486': 'Patient phone was busy',
                '487': 'Call was cancelled or timed out', 
                '408': 'No answer - call timed out',
                '503': 'Service temporarily unavailable',
                '404': 'Phone number not found',
                '603': 'Call declined by patient'
            }
            
            meaning = status_meanings.get(self.sip_status_code, f'SIP error {self.sip_status_code}')
            return f"{meaning}: {self.message}"
        
        return f"{self.category.value.replace('_', ' ').title()}: {self.message}"


def create_success_result(
    room_name: str,
    participant_identity: str = "patient",
    call_duration_seconds: Optional[int] = None
) -> CallExecutionResult:
    """Create a success result"""
    return CallExecutionResult(
        success=True,
        category=CallResultCategory.SUCCESS,
        retryability=CallRetryability.NOT_RETRYABLE,
        message="Call completed successfully",
        room_name=room_name,
        participant_identity=participant_identity,
        call_duration_seconds=call_duration_seconds
    )


def create_sip_error_result(
    sip_status_code: str,
    sip_status_text: str,
    message: str,
    room_name: Optional[str] = None
) -> CallExecutionResult:
    """Create a SIP error result with appropriate retry logic"""
    
    # Determine retryability based on SIP status code
    permanent_failures = ['404', '410', '603']  # Not found, gone, decline
    patient_busy_codes = ['486', '600']  # Busy, busy everywhere
    
    if sip_status_code in permanent_failures:
        retryability = CallRetryability.NOT_RETRYABLE
    elif sip_status_code in patient_busy_codes:
        retryability = CallRetryability.RETRYABLE
    else:
        # Most other SIP errors are retryable
        retryability = CallRetryability.RETRYABLE
    
    return CallExecutionResult(
        success=False,
        category=CallResultCategory.SIP_ERROR,
        retryability=retryability,
        message=message,
        sip_status_code=sip_status_code,
        sip_status_text=sip_status_text,
        room_name=room_name
    )


def create_network_error_result(message: str) -> CallExecutionResult:
    """Create a network error result (usually retryable)"""
    return CallExecutionResult(
        success=False,
        category=CallResultCategory.NETWORK_ERROR,
        retryability=CallRetryability.RETRYABLE,
        message=message,
        suggested_retry_delay_seconds=300  # 5 minutes for network issues
    )


def create_system_error_result(message: str, retryable: bool = True) -> CallExecutionResult:
    """Create a system error result"""
    return CallExecutionResult(
        success=False,
        category=CallResultCategory.SYSTEM_ERROR,
        retryability=CallRetryability.RETRYABLE if retryable else CallRetryability.NOT_RETRYABLE,
        message=message
    )


def create_patient_error_result(
    message: str,
    sip_status_code: Optional[str] = None
) -> CallExecutionResult:
    """Create a patient-related error (no answer, busy, etc.)"""
    return CallExecutionResult(
        success=False,
        category=CallResultCategory.PATIENT_ERROR,
        retryability=CallRetryability.RETRYABLE,
        message=message,
        sip_status_code=sip_status_code,
        suggested_retry_delay_seconds=600  # 10 minutes for patient issues
    )