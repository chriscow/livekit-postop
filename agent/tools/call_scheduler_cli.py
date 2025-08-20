#!/usr/bin/env python3
"""
Call Scheduler CLI Tool

This tool provides management and testing commands for the PostOp AI call scheduling system.
Useful for generating test calls, monitoring scheduled calls, and integration testing.

Usage:
    python tools/call_scheduler_cli.py generate-test-calls --patient-name "John Doe" --phone "+1234567890"
    python tools/call_scheduler_cli.py list-pending --limit 10
    python tools/call_scheduler_cli.py list-all-calls --status PENDING
    python tools/call_scheduler_cli.py simulate-discharge --patient-count 5
    python tools/call_scheduler_cli.py execute-call <call-id> --mock
    python tools/call_scheduler_cli.py stats
    python tools/call_scheduler_cli.py clear-test-data
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

import click
from dotenv import load_dotenv
from tabulate import tabulate

from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallRecord, CallStatus, CallType
from discharge.discharge_orders import SELECTED_DISCHARGE_ORDERS, get_order_by_id


class CallSchedulerManager:
    """Manages call scheduling operations for testing and monitoring"""
    
    def __init__(self, redis_host: str = None, redis_port: int = None):
        """Initialize the call scheduler manager"""
        self.scheduler = CallScheduler(redis_host=redis_host, redis_port=redis_port)
    
    def generate_test_calls(
        self, 
        patient_name: str, 
        patient_phone: str,
        patient_id: Optional[str] = None,
        discharge_orders: Optional[List[str]] = None
    ) -> List[CallScheduleItem]:
        """
        Generate test calls for a patient
        
        Args:
            patient_name: Name of the test patient
            patient_phone: Phone number for the test patient
            patient_id: Optional patient ID (will generate one if not provided)
            discharge_orders: List of discharge order IDs to use (defaults to common ones)
        
        Returns:
            List of generated CallScheduleItems
        """
        if not patient_id:
            patient_id = f"test-patient-{uuid.uuid4().hex[:8]}"
        
        if not discharge_orders:
            # Use common discharge orders for testing
            discharge_orders = ['vm_compression', 'vm_activity', 'vm_medication', 'vm_followup']
        
        # Generate calls
        calls = self.scheduler.generate_calls_for_patient(
            patient_id=patient_id,
            patient_phone=patient_phone,
            patient_name=patient_name,
            discharge_time=datetime.now(),
            selected_order_ids=discharge_orders
        )
        
        return calls
    
    def simulate_hospital_discharge(
        self, 
        patient_count: int = 1,
        base_phone: str = "+1555000"
    ) -> List[Dict[str, Any]]:
        """
        Simulate multiple patient discharges for testing
        
        Args:
            patient_count: Number of patients to discharge
            base_phone: Base phone number (will append patient number)
        
        Returns:
            List of patient discharge summaries
        """
        discharge_summaries = []
        
        # Common discharge order combinations
        order_combinations = [
            ['vm_compression', 'vm_activity'],
            ['vm_medication', 'vm_followup'],
            ['vm_compression', 'vm_medication', 'vm_school'],
            ['vm_activity', 'vm_followup', 'vm_emergency'],
            ['vm_bleomycin', 'vm_followup'],
        ]
        
        for i in range(patient_count):
            patient_name = f"Test Patient {i+1:02d}"
            patient_phone = f"{base_phone}{i+1:04d}"
            patient_id = f"sim-patient-{i+1:03d}"
            
            # Rotate through order combinations
            orders = order_combinations[i % len(order_combinations)]
            
            # Generate calls for this patient
            calls = self.generate_test_calls(
                patient_name=patient_name,
                patient_phone=patient_phone,
                patient_id=patient_id,
                discharge_orders=orders
            )
            
            discharge_summaries.append({
                'patient_id': patient_id,
                'patient_name': patient_name,
                'patient_phone': patient_phone,
                'discharge_orders': orders,
                'calls_generated': len(calls),
                'call_ids': [call.id for call in calls]
            })
        
        return discharge_summaries
    
    def get_call_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about scheduled calls"""
        # Get all pending calls (this is what we have available)
        pending_calls = self.scheduler.get_pending_calls(limit=1000)  # Large limit to get most calls
        
        if not pending_calls:
            return {
                'total_pending_calls': 0,
                'by_type': {},
                'by_priority': {},
                'upcoming_24h': 0,
                'overdue': 0
            }
        
        stats = {
            'total_pending_calls': len(pending_calls),
            'by_type': {},
            'by_priority': {},
            'upcoming_24h': 0,
            'overdue': 0
        }
        
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        for call in pending_calls:
            # Type breakdown
            type_key = call.call_type.value
            stats['by_type'][type_key] = stats['by_type'].get(type_key, 0) + 1
            
            # Priority breakdown
            stats['by_priority'][call.priority] = stats['by_priority'].get(call.priority, 0) + 1
            
            # Timing analysis
            if call.scheduled_time <= tomorrow:
                stats['upcoming_24h'] += 1
            
            if call.scheduled_time < now:
                stats['overdue'] += 1
        
        return stats
    
    def clear_test_data(self, confirm: bool = False) -> int:
        """
        Clear test call data from Redis
        
        Args:
            confirm: Whether to skip confirmation prompt
            
        Returns:
            Number of items cleared
        """
        if not confirm:
            # This would need to be confirmed by the CLI command
            return 0
        
        # Find test-related keys
        test_patterns = [
            "postop:calls:test-*",
            "postop:calls:sim-*", 
            "postop:schedule:*test*"
        ]
        
        cleared_count = 0
        for pattern in test_patterns:
            keys = self.scheduler.redis_client.keys(pattern)
            if keys:
                self.scheduler.redis_client.delete(*keys)
                cleared_count += len(keys)
        
        return cleared_count


# CLI Commands
@click.group()
@click.option('--redis-host', default='redis', help='Redis host (default: redis for Docker)')
@click.option('--redis-port', default=6379, help='Redis port (default: 6379)')
@click.pass_context
def cli(ctx, redis_host, redis_port):
    """PostOp AI Call Scheduler Management CLI"""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj['manager'] = CallSchedulerManager(redis_host=redis_host, redis_port=redis_port)


@cli.command()
@click.option('--patient-name', required=True, help="Name of the test patient")
@click.option('--phone', required=True, help="Phone number for the test patient")
@click.option('--patient-id', help="Patient ID (will generate if not provided)")
@click.option('--orders', help="Comma-separated list of discharge order IDs")
@click.pass_context
def generate_test_calls(ctx, patient_name, phone, patient_id, orders):
    """Generate test calls for a specific patient"""
    manager = ctx.obj['manager']
    
    # Parse discharge orders
    discharge_orders = None
    if orders:
        discharge_orders = [order.strip() for order in orders.split(',')]
        # Validate order IDs
        for order_id in discharge_orders:
            try:
                get_order_by_id(order_id)
            except ValueError:
                click.echo(f"❌ Invalid discharge order ID: {order_id}")
                return
    
    try:
        calls = manager.generate_test_calls(
            patient_name=patient_name,
            patient_phone=phone,
            patient_id=patient_id,
            discharge_orders=discharge_orders
        )
        
        click.echo(f"✅ Generated {len(calls)} test calls for {patient_name}")
        click.echo(f"📞 Patient Phone: {phone}")
        click.echo(f"🆔 Patient ID: {calls[0].patient_id if calls else 'N/A'}")
        
        if calls:
            click.echo(f"\n📋 Generated Calls:")
            for i, call in enumerate(calls, 1):
                click.echo(f"  {i}. {call.call_type.value} - {call.scheduled_time.strftime('%Y-%m-%d %H:%M')}")
                click.echo(f"     ID: {call.id[:12]}...")
                click.echo(f"     Priority: {call.priority}")
                
    except Exception as e:
        click.echo(f"❌ Error generating test calls: {e}")


@cli.command()
@click.option('--patient-count', default=3, help="Number of patients to simulate")
@click.option('--base-phone', default="+1555000", help="Base phone number")
@click.pass_context
def simulate_discharge(ctx, patient_count, base_phone):
    """Simulate multiple patient discharges for testing"""
    manager = ctx.obj['manager']
    
    try:
        click.echo(f"🏥 Simulating discharge of {patient_count} patients...")
        
        summaries = manager.simulate_hospital_discharge(
            patient_count=patient_count,
            base_phone=base_phone
        )
        
        total_calls = sum(s['calls_generated'] for s in summaries)
        click.echo(f"✅ Simulation complete! Generated {total_calls} calls for {patient_count} patients")
        
        # Display summary table
        table_data = []
        for summary in summaries:
            table_data.append([
                summary['patient_name'],
                summary['patient_phone'],
                ', '.join(summary['discharge_orders']),
                summary['calls_generated']
            ])
        
        click.echo(f"\n📊 Discharge Summary:")
        click.echo(tabulate(
            table_data,
            headers=['Patient', 'Phone', 'Discharge Orders', 'Calls'],
            tablefmt='grid'
        ))
        
    except Exception as e:
        click.echo(f"❌ Error simulating discharges: {e}")


@cli.command()
@click.option('--limit', default=20, help="Maximum number of calls to show")
@click.option('--upcoming-only', is_flag=True, help="Show only upcoming calls")
@click.pass_context
def list_pending(ctx, limit, upcoming_only):
    """List pending calls"""
    manager = ctx.obj['manager']
    
    try:
        calls = manager.scheduler.get_pending_calls(limit=limit)
        
        if upcoming_only:
            now = datetime.now()
            calls = [call for call in calls if call.scheduled_time >= now]
        
        if not calls:
            click.echo("📋 No pending calls found")
            return
        
        click.echo(f"📞 Found {len(calls)} pending calls:")
        
        # Group by patient for better readability
        by_patient = {}
        for call in calls:
            patient_key = f"{call.patient_id} ({call.patient_phone})"
            if patient_key not in by_patient:
                by_patient[patient_key] = []
            by_patient[patient_key].append(call)
        
        for patient_key, patient_calls in by_patient.items():
            click.echo(f"\n👤 {patient_key}")
            for call in patient_calls:
                status_emoji = "⏰" if call.scheduled_time > datetime.now() else "⚠️"
                click.echo(f"  {status_emoji} {call.call_type.value} - {call.scheduled_time.strftime('%Y-%m-%d %H:%M')}")
                click.echo(f"     ID: {call.id[:12]}... | Priority: {call.priority}")
                
    except Exception as e:
        click.echo(f"❌ Error listing pending calls: {e}")


@cli.command()
@click.option('--status', type=click.Choice(['PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'VOICEMAIL']), 
              help="Filter by call status")
@click.option('--limit', default=50, help="Maximum number of calls to show")
@click.pass_context
def list_all_calls(ctx, status, limit):
    """List all calls with optional status filtering"""
    manager = ctx.obj['manager']
    
    try:
        # For now, we can only get pending calls
        if status and status != 'PENDING':
            click.echo(f"⚠️  Only PENDING calls are available through the current API")
            click.echo(f"📋 Showing pending calls instead:")
        
        all_calls = manager.scheduler.get_pending_calls(limit=limit or 1000)
        
        if limit:
            all_calls = all_calls[:limit]
        
        if not all_calls:
            click.echo(f"📋 No pending calls found")
            return
        
        click.echo(f"📊 Found {len(all_calls)} pending calls:")
        
        # Create table data
        table_data = []
        for call in all_calls:
            table_data.append([
                call.id[:8] + "...",
                call.call_type.value[:15],
                "PENDING",  # All retrieved calls are pending
                f"P{call.priority}",
                call.scheduled_time.strftime('%m/%d %H:%M'),
                call.patient_phone
            ])
        
        click.echo(tabulate(
            table_data,
            headers=['Call ID', 'Type', 'Status', 'Pri', 'Scheduled', 'Phone'],
            tablefmt='grid'
        ))
        
    except Exception as e:
        click.echo(f"❌ Error listing calls: {e}")


@cli.command()
@click.pass_context
def stats(ctx):
    """Show comprehensive call scheduling statistics"""
    manager = ctx.obj['manager']
    
    try:
        stats = manager.get_call_statistics()
        
        click.echo("📊 Call Scheduling Statistics")
        click.echo(f"📞 Total pending calls: {stats['total_pending_calls']}")
        
        if stats['total_pending_calls'] == 0:
            click.echo("   No pending calls found. Try generating some test calls first!")
            return
        
        # Type breakdown
        click.echo(f"\n📱 By Call Type:")
        for call_type, count in stats['by_type'].items():
            percentage = (count / stats['total_pending_calls']) * 100
            click.echo(f"   {call_type}: {count} ({percentage:.1f}%)")
        
        # Priority breakdown
        click.echo(f"\n⭐ By Priority:")
        for priority, count in sorted(stats['by_priority'].items()):
            priority_label = {1: "Urgent", 2: "Important", 3: "Routine"}.get(priority, f"P{priority}")
            percentage = (count / stats['total_pending_calls']) * 100
            click.echo(f"   {priority_label}: {count} ({percentage:.1f}%)")
        
        # Timing information
        click.echo(f"\n⏰ Timing:")
        click.echo(f"   Upcoming (24h): {stats['upcoming_24h']}")
        click.echo(f"   Overdue: {stats['overdue']}")
        
    except Exception as e:
        click.echo(f"❌ Error getting statistics: {e}")


@cli.command()
@click.argument('call_id')
@click.option('--mock', is_flag=True, help="Mock the call execution (don't actually make a call)")
@click.pass_context
def execute_call(ctx, call_id, mock):
    """Execute a specific call (for testing)"""
    manager = ctx.obj['manager']
    
    try:
        # Find the call among pending calls (since we don't have get_call_by_id)
        pending_calls = manager.scheduler.get_pending_calls(limit=1000)
        call = None
        for c in pending_calls:
            if c.id.startswith(call_id) or c.id == call_id:
                call = c
                break
        
        if not call:
            click.echo(f"❌ Call with ID '{call_id}' not found in pending calls")
            click.echo(f"   Use 'list-pending' to see available call IDs")
            return
        
        click.echo(f"📞 Executing call: {call.id}")
        click.echo(f"   Type: {call.call_type.value}")
        click.echo(f"   Patient: {call.patient_phone}")
        click.echo(f"   Scheduled: {call.scheduled_time}")
        
        if mock:
            # Mock execution
            click.echo(f"🧪 Mock execution mode")
            manager.scheduler.update_call_status(call.id, CallStatus.IN_PROGRESS, "Mock execution started")
            click.echo(f"   ✅ Status updated to IN_PROGRESS")
            
            # Simulate completion after a moment
            import time
            time.sleep(1)
            manager.scheduler.update_call_status(call.id, CallStatus.COMPLETED, "Mock execution completed")
            click.echo(f"   ✅ Status updated to COMPLETED")
        else:
            click.echo(f"🚨 Real call execution not implemented in CLI")
            click.echo(f"   Use --mock flag for testing")
            
    except Exception as e:
        click.echo(f"❌ Error executing call: {e}")


@cli.command()
@click.option('--confirm', is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def clear_test_data(ctx, confirm):
    """Clear test call data from Redis"""
    manager = ctx.obj['manager']
    
    if not confirm:
        click.echo("🗑️ This will clear all test call data from Redis")
        click.echo("   This includes calls with IDs starting with 'test-' or 'sim-'")
        if not click.confirm("Are you sure you want to continue?"):
            click.echo("❌ Operation cancelled")
            return
    
    try:
        cleared_count = manager.clear_test_data(confirm=True)
        
        if cleared_count > 0:
            click.echo(f"✅ Cleared {cleared_count} test data items from Redis")
        else:
            click.echo("📋 No test data found to clear")
            
    except Exception as e:
        click.echo(f"❌ Error clearing test data: {e}")


@cli.command()
@click.pass_context
def redis_status(ctx):
    """Check Redis connection and PostOp data status"""
    manager = ctx.obj['manager']
    
    try:
        # Test Redis connection
        ping_result = manager.scheduler.redis_client.ping()
        click.echo(f"✅ Redis connection: {'OK' if ping_result else 'Failed'}")
        
        # Count PostOp keys
        postop_keys = manager.scheduler.redis_client.keys("postop:*")
        click.echo(f"📊 PostOp keys in Redis: {len(postop_keys)}")
        
        # Breakdown by key type
        key_types = {}
        for key in postop_keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            if ':calls:' in key_str:
                key_types['calls'] = key_types.get('calls', 0) + 1
            elif ':schedule:' in key_str:
                key_types['schedule'] = key_types.get('schedule', 0) + 1
            else:
                key_types['other'] = key_types.get('other', 0) + 1
        
        if key_types:
            click.echo(f"📋 Key breakdown:")
            for key_type, count in key_types.items():
                click.echo(f"   {key_type}: {count}")
        
    except Exception as e:
        click.echo(f"❌ Error checking Redis status: {e}")


if __name__ == '__main__':
    cli()