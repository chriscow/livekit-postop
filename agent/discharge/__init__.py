"""
Discharge package for PostOp AI system

Contains all discharge-related agents and functionality:
- ConsentCollector: Recording consent collection
- DischargeAgent: Complete workflow management (setup, instruction collection, translation, verification)
- discharge_orders: Discharge order data and utilities
"""

# Import discharge_orders directly since it has no livekit dependencies
# These imports happen immediately because they're lightweight data structures
from .discharge_orders import (
    DischargeOrder,
    DISCHARGE_ORDERS,
    SELECTED_DISCHARGE_ORDERS,
    get_order_by_id,
    get_selected_orders
)

# Agent classes are imported on-demand to avoid livekit dependencies during package import
# This function only runs when someone actually tries to use an agent class
def _lazy_import_agents():
    """Import all agent classes when first needed to avoid heavy dependencies at package load time"""
    from .agents import ConsentCollector, DischargeAgent
    return ConsentCollector, DischargeAgent

# Initialize agent class variables as None - they'll be populated when first accessed
# This is the "lazy loading" pattern - defer expensive imports until actually needed
ConsentCollector = None
DischargeAgent = None

def __getattr__(name):
    """
    Python magic method that runs when someone tries to access an attribute that doesn't exist
    This enables lazy loading - we only import the heavy agent classes when someone tries to use them
    
    Example: when someone does "from discharge import DischargeAgent", this function runs
    """
    global ConsentCollector, DischargeAgent
    
    # Check if they're asking for one of our agent classes
    if name in ['ConsentCollector', 'DischargeAgent']:
        # If we haven't loaded the agents yet, load them now
        if DischargeAgent is None:
            ConsentCollector, DischargeAgent = _lazy_import_agents()
        # Return the requested class from the global namespace
        return globals()[name]
    
    # If they asked for something we don't have, raise the standard Python error
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    'ConsentCollector',
    'DischargeAgent',
    'DischargeOrder',
    'DISCHARGE_ORDERS',
    'SELECTED_DISCHARGE_ORDERS',
    'get_order_by_id',
    'get_selected_orders'
]