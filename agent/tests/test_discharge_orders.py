"""
Tests for enhanced discharge orders functionality
"""
import pytest
from discharge.discharge_orders import DischargeOrder, DISCHARGE_ORDERS, get_selected_orders


class TestDischargeOrder:
    """Tests for DischargeOrder dataclass"""
    
    def test_default_values(self):
        """Test default values for new fields"""
        order = DischargeOrder(
            id="test_id",
            label="Test Order", 
            discharge_order="Test instructions"
        )
        
        assert order.generates_calls is False
        assert order.call_template is None
        assert order.day_offset == 0
        assert order.send_at_hour == 9
    
    def test_order_with_call_template(self):
        """Test order with call template"""
        call_template = {
            "timing": "24_hours_after_discharge",
            "call_type": "discharge_reminder",
            "priority": 2,
            "prompt_template": "Test prompt for {patient_name}"
        }
        
        order = DischargeOrder(
            id="test_id",
            label="Test Order",
            discharge_order="Test instructions",
            generates_calls=True,
            call_template=call_template
        )
        
        assert order.generates_calls is True
        assert order.call_template == call_template
        assert order.call_template["timing"] == "24_hours_after_discharge"
        assert order.call_template["call_type"] == "discharge_reminder"
        assert order.call_template["priority"] == 2
        assert "{patient_name}" in order.call_template["prompt_template"]


class TestDischargeOrdersData:
    """Tests for the actual discharge orders data"""
    
    def test_discharge_orders_structure(self):
        """Test that all discharge orders have required fields"""
        for order in DISCHARGE_ORDERS:
            assert hasattr(order, 'id')
            assert hasattr(order, 'label')
            assert hasattr(order, 'discharge_order')
            assert hasattr(order, 'generates_calls')
            assert hasattr(order, 'call_template')
            assert hasattr(order, 'day_offset')
            assert hasattr(order, 'send_at_hour')
            
            # ID and label should be non-empty strings
            assert isinstance(order.id, str) and len(order.id) > 0
            assert isinstance(order.label, str) and len(order.label) > 0
            assert isinstance(order.discharge_order, str) and len(order.discharge_order) > 0
            
            # Boolean and numeric fields
            assert isinstance(order.generates_calls, bool)
            assert isinstance(order.day_offset, int)
            assert isinstance(order.send_at_hour, int)
    
    def test_orders_with_call_templates(self):
        """Test orders that generate calls have valid templates"""
        call_generating_orders = [order for order in DISCHARGE_ORDERS if order.generates_calls]
        
        # Should have some orders that generate calls
        assert len(call_generating_orders) > 0
        
        for order in call_generating_orders:
            assert order.call_template is not None
            assert isinstance(order.call_template, dict)
            
            # Required template fields
            assert "timing" in order.call_template
            assert "call_type" in order.call_template
            assert "priority" in order.call_template
            assert "prompt_template" in order.call_template
            
            # Validate field types and values
            assert isinstance(order.call_template["timing"], str)
            assert len(order.call_template["timing"]) > 0
            
            assert isinstance(order.call_template["call_type"], str)
            assert order.call_template["call_type"] in [
                "discharge_reminder", "wellness_check", "medication_reminder", "follow_up", "urgent"
            ]
            
            assert isinstance(order.call_template["priority"], int)
            assert 1 <= order.call_template["priority"] <= 3
            
            assert isinstance(order.call_template["prompt_template"], str)
            assert len(order.call_template["prompt_template"]) > 0
    
    def test_specific_order_templates(self):
        """Test specific orders have expected templates"""
        # Find compression bandage order
        compression_order = next(
            (order for order in DISCHARGE_ORDERS if order.id == "vm_compression"), 
            None
        )
        assert compression_order is not None
        assert compression_order.generates_calls is True
        assert compression_order.call_template["timing"] == "24_hours_after_discharge"
        assert "{patient_name}" in compression_order.call_template["prompt_template"]
        assert "{discharge_order}" in compression_order.call_template["prompt_template"]
        
        # Find activity restrictions order
        activity_order = next(
            (order for order in DISCHARGE_ORDERS if order.id == "vm_activity"),
            None
        )
        assert activity_order is not None
        assert activity_order.generates_calls is True
        assert activity_order.call_template["timing"] == "48_hours_after_discharge"
        
        # Find school return order
        school_order = next(
            (order for order in DISCHARGE_ORDERS if order.id == "vm_school"),
            None
        )
        assert school_order is not None
        assert school_order.generates_calls is True
        assert "day_before_date:2025-06-23" in school_order.call_template["timing"]
    
    def test_prompt_template_placeholders(self):
        """Test that prompt templates have expected placeholders"""
        call_generating_orders = [order for order in DISCHARGE_ORDERS if order.generates_calls]
        
        for order in call_generating_orders:
            prompt = order.call_template["prompt_template"]
            
            # Should contain patient name placeholder
            assert "{patient_name}" in prompt
            
            # Should contain discharge order reference
            assert "{discharge_order}" in prompt or order.discharge_order in prompt
            
            # Should be conversational (contain common phone call phrases)
            prompt_lower = prompt.lower()
            conversational_indicators = [
                "you are calling", "this is a", "ask", "remind", "check", 
                "how", "questions", "feeling", "instructions"
            ]
            assert any(indicator in prompt_lower for indicator in conversational_indicators)
    
    def test_timing_specifications(self):
        """Test that timing specifications are valid formats"""
        call_generating_orders = [order for order in DISCHARGE_ORDERS if order.generates_calls]
        
        valid_timing_patterns = [
            r'\d+_hours_after_discharge',
            r'daily_for_\d+_days_starting_\d+_hours_after_discharge',
            r'day_before_date:\d{4}-\d{2}-\d{2}',
            r'within_24_hours'
        ]
        
        import re
        
        for order in call_generating_orders:
            timing = order.call_template["timing"]
            
            # Should match at least one valid pattern
            matches_pattern = any(
                re.match(pattern, timing) for pattern in valid_timing_patterns
            )
            assert matches_pattern, f"Invalid timing specification: {timing}"
    
    def test_orders_without_call_templates(self):
        """Test that orders without call generation don't have templates"""
        non_call_orders = [order for order in DISCHARGE_ORDERS if not order.generates_calls]
        
        # Should have some orders that don't generate calls
        assert len(non_call_orders) > 0
        
        for order in non_call_orders:
            # Template should be None for non-call-generating orders
            assert order.call_template is None
    
    def test_backward_compatibility(self):
        """Test that existing day_offset and send_at_hour fields are preserved"""
        for order in DISCHARGE_ORDERS:
            # All orders should have these fields for backward compatibility
            assert hasattr(order, 'day_offset')
            assert hasattr(order, 'send_at_hour')
            assert isinstance(order.day_offset, int)
            assert isinstance(order.send_at_hour, int)
            
            # Should be reasonable values
            assert 0 <= order.day_offset <= 30  # Within a month
            assert 0 <= order.send_at_hour <= 23  # Valid hour
    
    def test_get_selected_orders(self):
        """Test the get_selected_orders function works"""
        selected_orders = get_selected_orders()
        
        # Should return a list
        assert isinstance(selected_orders, list)
        
        # Should contain DischargeOrder objects
        for order in selected_orders:
            assert isinstance(order, DischargeOrder)
        
        # Should match orders from SELECTED_DISCHARGE_ORDERS
        from discharge.discharge_orders import SELECTED_DISCHARGE_ORDERS
        assert len(selected_orders) == len(SELECTED_DISCHARGE_ORDERS)
        
        selected_ids = [order.id for order in selected_orders]
        for order_id in SELECTED_DISCHARGE_ORDERS:
            assert order_id in selected_ids