"""
Time utilities for PostOp AI system

Provides timezone-aware datetime handling for consistent scheduling
across different patient locations and server deployments.
"""
from datetime import datetime, timezone
from typing import Optional
import pytz
import logging

logger = logging.getLogger("time-utils")

# Default timezone for the system (UTC)
SYSTEM_TIMEZONE = timezone.utc

# Common patient timezones (can be extended)
PATIENT_TIMEZONES = {
    'US/Eastern': pytz.timezone('US/Eastern'),
    'US/Central': pytz.timezone('US/Central'),
    'US/Mountain': pytz.timezone('US/Mountain'),
    'US/Pacific': pytz.timezone('US/Pacific'),
    'UTC': pytz.timezone('UTC')
}


def now_utc() -> datetime:
    """
    Get current time in UTC
    
    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(SYSTEM_TIMEZONE)


def parse_iso_to_utc(iso_string: str) -> datetime:
    """
    Parse ISO datetime string to UTC datetime
    
    Args:
        iso_string: ISO format datetime string
        
    Returns:
        datetime object in UTC timezone
        
    Raises:
        ValueError: If the ISO string is invalid
    """
    try:
        dt = datetime.fromisoformat(iso_string)
        
        # If naive datetime, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SYSTEM_TIMEZONE)
            logger.warning(f"Naive datetime {iso_string} assumed to be UTC")
        else:
            # Convert to UTC
            dt = dt.astimezone(SYSTEM_TIMEZONE)
            
        return dt
    except ValueError as e:
        logger.error(f"Failed to parse ISO datetime string '{iso_string}': {e}")
        raise


def to_utc(dt: datetime, assume_timezone: str = 'UTC') -> datetime:
    """
    Convert datetime to UTC
    
    Args:
        dt: Datetime to convert
        assume_timezone: Timezone to assume if datetime is naive
        
    Returns:
        datetime object in UTC timezone
    """
    if dt.tzinfo is None:
        # Naive datetime - assume specified timezone
        if assume_timezone in PATIENT_TIMEZONES:
            local_tz = PATIENT_TIMEZONES[assume_timezone]
            dt = local_tz.localize(dt)
        else:
            dt = dt.replace(tzinfo=SYSTEM_TIMEZONE)
            logger.warning(f"Unknown timezone '{assume_timezone}', assuming UTC")
    
    return dt.astimezone(SYSTEM_TIMEZONE)


def to_patient_timezone(dt: datetime, patient_timezone: str = 'UTC') -> datetime:
    """
    Convert UTC datetime to patient's local timezone
    
    Args:
        dt: UTC datetime to convert
        patient_timezone: Target timezone (defaults to UTC)
        
    Returns:
        datetime object in patient's timezone
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SYSTEM_TIMEZONE)
    
    if patient_timezone in PATIENT_TIMEZONES:
        target_tz = PATIENT_TIMEZONES[patient_timezone]
        return dt.astimezone(target_tz)
    else:
        logger.warning(f"Unknown patient timezone '{patient_timezone}', using UTC")
        return dt.astimezone(SYSTEM_TIMEZONE)


def format_for_patient(dt: datetime, patient_timezone: str = 'UTC') -> str:
    """
    Format datetime for display to patient in their local timezone
    
    Args:
        dt: UTC datetime to format
        patient_timezone: Patient's timezone
        
    Returns:
        Formatted datetime string in patient's timezone
    """
    local_dt = to_patient_timezone(dt, patient_timezone)
    return local_dt.strftime("%Y-%m-%d %I:%M %p %Z")


def get_patient_friendly_time(dt: datetime, patient_timezone: str = 'UTC') -> str:
    """
    Get a patient-friendly description of the time
    
    Args:
        dt: UTC datetime
        patient_timezone: Patient's timezone
        
    Returns:
        Human-readable time description
    """
    local_dt = to_patient_timezone(dt, patient_timezone)
    now_local = to_patient_timezone(now_utc(), patient_timezone)
    
    # Calculate difference
    time_diff = local_dt - now_local
    hours_diff = time_diff.total_seconds() / 3600
    
    if abs(hours_diff) < 1:
        return "in a few minutes" if hours_diff > 0 else "just now"
    elif hours_diff < 24:
        return f"in {int(hours_diff)} hours" if hours_diff > 0 else f"{int(abs(hours_diff))} hours ago"
    else:
        days_diff = int(hours_diff / 24)
        return f"in {days_diff} days" if days_diff > 0 else f"{abs(days_diff)} days ago"


def add_business_hours_offset(
    dt: datetime, 
    offset_hours: int, 
    patient_timezone: str = 'UTC',
    business_start: int = 9,  # 9 AM
    business_end: int = 17    # 5 PM
) -> datetime:
    """
    Add offset hours but ensure the result falls within business hours in patient timezone
    
    Args:
        dt: Base datetime (UTC)
        offset_hours: Hours to add
        patient_timezone: Patient's timezone for business hours calculation
        business_start: Business hours start (24-hour format)
        business_end: Business hours end (24-hour format)
        
    Returns:
        Adjusted datetime in UTC that falls within business hours
    """
    # Calculate the target time
    target_dt = dt + timedelta(hours=offset_hours)
    
    # Convert to patient timezone to check business hours
    local_target = to_patient_timezone(target_dt, patient_timezone)
    
    # If it's outside business hours, adjust to next business day
    if local_target.hour < business_start:
        # Too early - move to business start
        local_target = local_target.replace(hour=business_start, minute=0, second=0, microsecond=0)
    elif local_target.hour >= business_end:
        # Too late - move to next business day
        next_day = local_target + timedelta(days=1)
        local_target = next_day.replace(hour=business_start, minute=0, second=0, microsecond=0)
    
    # Skip weekends (move to Monday if it's Saturday or Sunday)
    while local_target.weekday() >= 5:  # 5=Saturday, 6=Sunday
        local_target += timedelta(days=1)
        local_target = local_target.replace(hour=business_start, minute=0, second=0, microsecond=0)
    
    # Convert back to UTC
    return to_utc(local_target.replace(tzinfo=None), patient_timezone)


# Convenience imports for backward compatibility
def utc_now():
    """Alias for now_utc()"""
    return now_utc()


def parse_discharge_time(discharge_time_iso: str) -> datetime:
    """
    Parse discharge time from ISO string to UTC datetime
    
    Args:
        discharge_time_iso: ISO format discharge datetime
        
    Returns:
        UTC datetime object
    """
    return parse_iso_to_utc(discharge_time_iso)