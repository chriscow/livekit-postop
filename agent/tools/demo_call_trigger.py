#!/usr/bin/env python3
"""
Demo Call Trigger CLI Tool

This tool allows immediate execution of follow-up calls for live demonstrations,
bypassing the normal scheduling system to trigger calls "right now".
"""

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import click
from dotenv import load_dotenv
from tabulate import tabulate

from scheduling.scheduler import CallScheduler
from scheduling.models import CallScheduleItem, CallType, CallStatus, CallRecord
from scheduling.tasks import execute_followup_call
from discharge.transcript_analyzer import analyze_and_schedule_calls


class DemoCallTrigger:
    """Manages demo call triggering and immediate execution"""
    
    def __init__(self, redis_host: str = None, redis_port: int = None):
        self.scheduler = CallScheduler(redis_host=redis_host, redis_port=redis_port)
        
    def list_available_calls(self, patient_filter: str = None) -> List[Dict[str, Any]]:
        """List all available calls that can be triggered for demo"""
        try:
            # Get all pending calls (includes future calls too)
            current_time = datetime.now().timestamp()
            
            # Get call IDs from the by_time sorted set (all scheduled calls)
            all_call_ids = self.scheduler.redis_client.zrange(
                f"{self.scheduler.calls_key}:by_time", 0, -1
            )
            
            all_calls = []
            for call_id in all_call_ids:
                call_data = self.scheduler.redis_client.hgetall(f"{self.scheduler.calls_key}:{call_id}")
                if call_data:
                    try:
                        from scheduling.models import CallScheduleItem, CallStatus
                        call_item = CallScheduleItem.from_dict(call_data)
                        # Only include pending calls
                        if call_item.status == CallStatus.PENDING:
                            all_calls.append(call_item)
                    except Exception as e:
                        continue
            
            # Filter by patient if specified
            if patient_filter:
                all_calls = [call for call in all_calls if patient_filter.lower() in call.patient_id.lower() or patient_filter.lower() in call.patient_phone]
            
            # Convert to display format
            call_list = []
            for call in all_calls:
                # Try to get patient name from metadata, fallback to extracting from patient_id
                patient_name = call.metadata.get('patient_name', 'Unknown')
                if patient_name == 'Unknown' and call.patient_id.startswith('demo-'):
                    # Extract name from demo patient ID format: demo-timestamp-patientname
                    parts = call.patient_id.split('-')
                    if len(parts) >= 3:
                        patient_name = parts[2].replace('', ' ').title()
                
                call_info = {
                    'call_id': call.id,
                    'short_id': call.id[:8] + "...",
                    'patient_name': patient_name,
                    'patient_id': call.patient_id,
                    'patient_phone': call.patient_phone,
                    'call_type': call.call_type.value,
                    'priority': call.priority,
                    'scheduled_time': call.scheduled_time,
                    'status': call.status.value,
                    'is_demo_ready': self._is_demo_ready(call),
                    'llm_prompt_preview': call.llm_prompt[:80] + "..." if len(call.llm_prompt) > 80 else call.llm_prompt
                }
                call_list.append(call_info)
            
            # Sort by scheduled time
            call_list.sort(key=lambda x: x['scheduled_time'])
            return call_list
            
        except Exception as e:
            click.echo(f"❌ Error listing calls: {e}")
            return []
    
    def _is_demo_ready(self, call: CallScheduleItem) -> bool:
        """Check if a call is ready for demo (not too far in future)"""
        now = datetime.now()
        time_until_call = call.scheduled_time - now
        # Demo ready if scheduled within next 24 hours or already past due
        return time_until_call <= timedelta(hours=24)
    
    def trigger_call_immediately(self, call_id: str, mock_execution: bool = False) -> Dict[str, Any]:
        """Trigger a specific call for immediate execution"""
        try:
            # Find the call
            pending_calls = self.scheduler.get_pending_calls(limit=1000)
            target_call = None
            
            for call in pending_calls:
                if call.id.startswith(call_id) or call.id == call_id:
                    target_call = call
                    break
            
            if not target_call:
                return {
                    'success': False,
                    'error': f"Call with ID '{call_id}' not found in pending calls"
                }
            
            if mock_execution:
                # Update call status to in_progress for mock
                self.scheduler.update_call_status(target_call.id, CallStatus.IN_PROGRESS, "Demo execution triggered")
                
                # Mock execution for demo purposes
                result = self._mock_call_execution(target_call)
                
                # Update to completed status
                self.scheduler.update_call_status(
                    target_call.id, 
                    CallStatus.COMPLETED, 
                    "Demo mock execution completed"
                )
            else:
                # Queue for real execution via RQ (don't update status - let the task do it)
                from scheduling.tasks import execute_followup_call
                job = execute_followup_call.delay(target_call.id)  # Only pass call_id
                
                result = {
                    'success': True,
                    'call_id': target_call.id,
                    'job_id': job.id,
                    'execution_type': 'real',
                    'message': 'Call queued for real execution via LiveKit'
                }
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error triggering call: {str(e)}"
            }
    
    def _mock_call_execution(self, call: CallScheduleItem) -> Dict[str, Any]:
        """Mock call execution for demo purposes"""
        import random
        import time
        
        # Simulate call duration
        mock_duration = random.randint(45, 180)  # 45-180 seconds
        
        # Simulate various outcomes
        outcomes = [
            {
                'success': True,
                'outcome': 'Patient confirmed understanding of compression bandage removal',
                'patient_responses': {
                    'bandage_removed': True,
                    'pain_level': '2/10',
                    'questions': 'When can I shower normally?',
                    'compliance': 'following all instructions'
                },
                'satisfaction': 4.8,
                'follow_up_needed': False
            },
            {
                'success': True,
                'outcome': 'Patient reported mild concerns, provided reassurance',
                'patient_responses': {
                    'pain_level': '4/10',
                    'concerns': 'some swelling around injection site',
                    'questions': 'is this normal?',
                    'compliance': 'mostly following instructions'
                },
                'satisfaction': 4.2,
                'follow_up_needed': False
            },
            {
                'success': True,
                'outcome': 'Routine wellness check completed successfully',
                'patient_responses': {
                    'overall_feeling': 'much better',
                    'pain_level': '1/10',
                    'questions': 'none',
                    'compliance': 'excellent'
                },
                'satisfaction': 5.0,
                'follow_up_needed': False
            }
        ]
        
        mock_outcome = random.choice(outcomes)
        
        return {
            'success': True,
            'call_id': call.id,
            'execution_type': 'mock',
            'duration_seconds': mock_duration,
            'room_name': f'demo-call-{call.id[:8]}',
            'participant_identity': 'patient',
            'outcome': mock_outcome['outcome'],
            'patient_responses': mock_outcome['patient_responses'],
            'patient_satisfaction': mock_outcome['satisfaction'],
            'follow_up_needed': mock_outcome['follow_up_needed'],
            'message': f'Mock call completed in {mock_duration} seconds'
        }
    
    def create_demo_patient_call(
        self, 
        patient_name: str, 
        patient_phone: str, 
        call_type: str,
        execute_immediately: bool = False
    ) -> Dict[str, Any]:
        """Create a demo patient call with realistic data"""
        try:
            # Create demo patient ID
            demo_patient_id = f"demo-{int(time.time())}-{patient_name.lower().replace(' ', '')}"
            
            # Define call type templates
            call_templates = {
                'compression_reminder': {
                    'call_type': CallType.DISCHARGE_REMINDER,
                    'priority': 2,
                    'prompt': f"Hi {patient_name}, this is PostOp AI calling to remind you about your compression bandage. According to your discharge instructions, it's time to remove your compression bandage. Have you been able to do this? How is the area looking?"
                },
                'medication_reminder': {
                    'call_type': CallType.MEDICATION_REMINDER,
                    'priority': 2,
                    'prompt': f"Hello {patient_name}, this is a medication reminder from PostOp AI. I wanted to check in about your pain medication schedule. Are you taking your ibuprofen as prescribed? How is your pain level today?"
                },
                'wellness_check': {
                    'call_type': CallType.WELLNESS_CHECK,
                    'priority': 3,
                    'prompt': f"Hi {patient_name}, this is PostOp AI calling for a wellness check. How are you feeling today? Any concerns about your recovery that you'd like to discuss?"
                },
                'activity_guidance': {
                    'call_type': CallType.DISCHARGE_REMINDER,
                    'priority': 2,
                    'prompt': f"Hello {patient_name}, I'm calling to discuss your activity restrictions. According to your discharge instructions, you should be able to gradually return to normal activities now. How has that been going?"
                }
            }
            
            if call_type not in call_templates:
                return {
                    'success': False,
                    'error': f"Unknown call type '{call_type}'. Available: {', '.join(call_templates.keys())}"
                }
            
            template = call_templates[call_type]
            
            # Create call item scheduled for "now" (demo purposes)
            call_item = CallScheduleItem(
                patient_id=demo_patient_id,
                patient_phone=patient_phone,
                scheduled_time=datetime.now() + timedelta(minutes=1),  # 1 minute from now
                call_type=template['call_type'],
                priority=template['priority'],
                llm_prompt=template['prompt'],
                metadata={
                    'demo_call': True,
                    'created_for': 'demonstration',
                    'patient_name': patient_name,
                    'call_category': call_type
                }
            )
            
            # Schedule the call
            if self.scheduler.schedule_call(call_item):
                result = {
                    'success': True,
                    'call_id': call_item.id,
                    'short_id': call_item.id[:8],
                    'patient_name': patient_name,
                    'patient_phone': patient_phone,
                    'call_type': call_type,
                    'scheduled_time': call_item.scheduled_time,
                    'message': f'Demo call created for {patient_name}'
                }
                
                # Execute immediately if requested
                if execute_immediately:
                    exec_result = self.trigger_call_immediately(call_item.id, mock_execution=True)
                    result['execution_result'] = exec_result
                
                return result
            else:
                return {
                    'success': False,
                    'error': 'Failed to schedule demo call'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Error creating demo call: {str(e)}"
            }
    
    def test_llm_analysis_flow(self, patient_name: str = "Demo Patient") -> Dict[str, Any]:
        """Test the complete LLM analysis flow with demo data"""
        try:
            # Create realistic discharge instructions
            sample_instructions = [
                {
                    "text": "Remove the compression bandage in 24 hours. Keep the area clean and dry after removal.",
                    "type": "wound_care"
                },
                {
                    "text": "Take ibuprofen 400mg every 6 hours as needed for pain. Do not exceed 1200mg in 24 hours.",
                    "type": "medication"
                }, 
                {
                    "text": "Avoid strenuous activity for 48 hours, then gradually return to normal activities over the next week.",
                    "type": "activity"
                },
                {
                    "text": "Call our office immediately if you experience fever over 101°F, increased redness, or unusual swelling.",
                    "type": "warning"
                }
            ]
            
            # Run LLM analysis
            demo_session_id = f"demo-llm-{int(time.time())}"
            
            analysis, call_items = asyncio.run(analyze_and_schedule_calls(
                session_id=demo_session_id,
                patient_name=patient_name,
                patient_phone="+15551234567",
                patient_language="english",
                collected_instructions=sample_instructions,
                discharge_time=datetime.now()
            ))
            
            # Schedule the LLM-generated calls
            scheduled_calls = []
            for call_data in call_items:
                # Adjust timing for demo (make calls due soon)
                call_data["scheduled_time"] = datetime.now() + timedelta(minutes=len(scheduled_calls) * 2)
                
                call_item = CallScheduleItem(
                    patient_id=call_data["patient_id"],
                    patient_phone=call_data["patient_phone"],
                    scheduled_time=call_data["scheduled_time"],
                    call_type=CallType.from_string(call_data.get("call_type", "general_followup")),
                    priority=call_data.get("priority", 3),
                    llm_prompt=call_data["llm_prompt"],
                    metadata=call_data.get("metadata", {})
                )
                
                if self.scheduler.schedule_call(call_item):
                    scheduled_calls.append({
                        'call_id': call_item.id[:8],
                        'call_type': call_item.call_type.value,
                        'scheduled_time': call_item.scheduled_time,
                        'priority': call_item.priority,
                        'prompt_preview': call_item.llm_prompt[:100] + "..."
                    })
            
            return {
                'success': True,
                'patient_name': patient_name,
                'session_id': demo_session_id,
                'analysis': {
                    'instructions_analyzed': len(analysis.analyzed_instructions),
                    'overall_complexity': analysis.overall_complexity,
                    'analysis_confidence': analysis.analysis_confidence,
                    'special_considerations': analysis.special_considerations
                },
                'scheduled_calls': scheduled_calls,
                'message': f'LLM analysis flow completed: {len(scheduled_calls)} calls scheduled'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error in LLM analysis flow: {str(e)}"
            }
    
    def clear_demo_data(self, confirm: bool = False) -> Dict[str, Any]:
        """Clear demo-related call data"""
        if not confirm:
            return {'success': False, 'error': 'Confirmation required'}
        
        try:
            # Find demo calls
            all_calls = self.scheduler.get_pending_calls(limit=1000)
            demo_calls = []
            
            for call in all_calls:
                # Check if it's a demo call
                is_demo = (
                    call.patient_id.startswith('demo-') or 
                    call.patient_id.startswith('test-') or
                    'demo_call' in (call.metadata or {})
                )
                
                if is_demo:
                    demo_calls.append(call)
            
            # Remove demo calls
            removed_count = 0
            for call in demo_calls:
                try:
                    # Remove from Redis
                    self.scheduler.redis_client.delete(f"postop:scheduled_calls:{call.id}")
                    self.scheduler.redis_client.zrem("postop:scheduled_calls:by_time", call.id)
                    removed_count += 1
                except Exception as e:
                    click.echo(f"Warning: Failed to remove call {call.id}: {e}")
            
            return {
                'success': True,
                'removed_count': removed_count,
                'message': f'Cleared {removed_count} demo calls'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error clearing demo data: {str(e)}"
            }


# CLI Commands
@click.group()
@click.option('--redis-host', default='redis', help='Redis host (default: redis for Docker)')
@click.option('--redis-port', default=6379, help='Redis port (default: 6379)')
@click.pass_context
def cli(ctx, redis_host, redis_port):
    """PostOp AI Demo Call Trigger CLI"""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj['trigger'] = DemoCallTrigger(redis_host=redis_host, redis_port=redis_port)


@cli.command()
@click.option('--patient-filter', help='Filter calls by patient ID or phone')
@click.option('--demo-ready-only', is_flag=True, help='Show only demo-ready calls')
@click.pass_context
def list_calls(ctx, patient_filter, demo_ready_only):
    """List all available calls that can be triggered for demo"""
    trigger = ctx.obj['trigger']
    calls = trigger.list_available_calls(patient_filter)
    
    if not calls:
        click.echo("📋 No calls available for demo")
        return
    
    if demo_ready_only:
        calls = [call for call in calls if call['is_demo_ready']]
    
    click.echo(f"📞 Found {len(calls)} available calls:")
    
    # Create table
    table_data = []
    for call in calls[:20]:  # Limit to 20 for readability
        status_icon = "🟢" if call['is_demo_ready'] else "🟡"
        table_data.append([
            status_icon,
            call['short_id'],
            call['patient_name'],
            call['call_type'],
            f"P{call['priority']}",
            call['scheduled_time'].strftime('%m/%d %H:%M'),
            call['llm_prompt_preview']
        ])
    
    click.echo(tabulate(
        table_data,
        headers=['Ready', 'Call ID', 'Patient', 'Type', 'Pri', 'Scheduled', 'Prompt Preview'],
        tablefmt='grid'
    ))
    
    if len(calls) > 20:
        click.echo(f"... and {len(calls) - 20} more calls (use --patient-filter to narrow results)")


@cli.command()
@click.argument('call_id')
@click.option('--mock', is_flag=True, help='Mock execution (don\'t make real call)')
@click.pass_context
def execute(ctx, call_id, mock):
    """Execute a specific call immediately"""
    trigger = ctx.obj['trigger']
    
    click.echo(f"🚀 Triggering call {call_id} for immediate execution...")
    
    result = trigger.trigger_call_immediately(call_id, mock_execution=mock)
    
    if result['success']:
        click.echo(f"✅ {result['message']}")
        
        if 'execution_result' in result:
            exec_result = result['execution_result']
            if exec_result.get('success'):
                click.echo(f"📞 Call completed in {exec_result.get('duration_seconds', 0)} seconds")
                click.echo(f"📝 Outcome: {exec_result.get('outcome', 'N/A')}")
                
                if 'patient_responses' in exec_result:
                    click.echo(f"💬 Patient responses:")
                    for key, value in exec_result['patient_responses'].items():
                        click.echo(f"   {key}: {value}")
    else:
        click.echo(f"❌ {result['error']}")


@cli.command()
@click.option('--name', required=True, help='Demo patient name')
@click.option('--phone', default='+15551234567', help='Demo patient phone')
@click.option('--type', 'call_type', required=True, 
              type=click.Choice(['compression_reminder', 'medication_reminder', 'wellness_check', 'activity_guidance']),
              help='Type of demo call to create')
@click.option('--execute-now', is_flag=True, help='Execute the call immediately after creation')
@click.pass_context
def create_demo_call(ctx, name, phone, call_type, execute_now):
    """Create a demo call for a patient"""
    trigger = ctx.obj['trigger']
    
    click.echo(f"🎬 Creating demo {call_type} call for {name}...")
    
    result = trigger.create_demo_patient_call(
        patient_name=name,
        patient_phone=phone,
        call_type=call_type,
        execute_immediately=execute_now
    )
    
    if result['success']:
        click.echo(f"✅ Demo call created: {result['short_id']}")
        click.echo(f"📅 Scheduled for: {result['scheduled_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if execute_now and 'execution_result' in result:
            exec_result = result['execution_result']
            if exec_result.get('success'):
                click.echo(f"🎯 Executed immediately: {exec_result.get('message')}")
            else:
                click.echo(f"⚠️ Execution failed: {exec_result.get('error')}")
    else:
        click.echo(f"❌ {result['error']}")


@cli.command()
@click.option('--patient-name', default='Demo Patient', help='Name for LLM analysis test')
@click.pass_context
def test_llm_flow(ctx, patient_name):
    """Test the complete LLM analysis and call generation flow"""
    trigger = ctx.obj['trigger']
    
    click.echo(f"🧠 Testing LLM analysis flow for {patient_name}...")
    
    result = trigger.test_llm_analysis_flow(patient_name)
    
    if result['success']:
        click.echo(f"✅ LLM analysis completed successfully")
        click.echo(f"📊 Analysis results:")
        
        analysis = result['analysis']
        click.echo(f"   Instructions analyzed: {analysis['instructions_analyzed']}")
        click.echo(f"   Complexity: {analysis['overall_complexity']}")
        click.echo(f"   Confidence: {analysis['analysis_confidence']:.1%}")
        
        if analysis['special_considerations']:
            click.echo(f"   Special considerations: {', '.join(analysis['special_considerations'])}")
        
        click.echo(f"\\n📞 Scheduled calls:")
        for call in result['scheduled_calls']:
            click.echo(f"   • {call['call_id']}: {call['call_type']} (P{call['priority']}) - {call['scheduled_time'].strftime('%H:%M')}")
            click.echo(f"     {call['prompt_preview']}")
        
    else:
        click.echo(f"❌ {result['error']}")


@cli.command()
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def clear_demo_data(ctx, confirm):
    """Clear all demo call data"""
    trigger = ctx.obj['trigger']
    
    if not confirm:
        click.echo("🗑️ This will remove all demo and test calls from the system")
        if not click.confirm("Are you sure you want to continue?"):
            click.echo("❌ Operation cancelled")
            return
    
    result = trigger.clear_demo_data(confirm=True)
    
    if result['success']:
        click.echo(f"✅ {result['message']}")
    else:
        click.echo(f"❌ {result['error']}")


@cli.command()
@click.pass_context
def demo_scenario(ctx):
    """Run a complete demo scenario from discharge to call execution"""
    trigger = ctx.obj['trigger']
    
    click.echo("🎬 Running Complete Demo Scenario")
    click.echo("=" * 40)
    
    # Step 1: LLM Analysis
    click.echo("\\n📋 Step 1: LLM Discharge Analysis")
    llm_result = trigger.test_llm_analysis_flow("Sarah Johnson")
    
    if not llm_result['success']:
        click.echo(f"❌ LLM analysis failed: {llm_result['error']}")
        return
    
    click.echo(f"✅ Analyzed discharge instructions → {len(llm_result['scheduled_calls'])} calls scheduled")
    
    # Step 2: Show scheduled calls
    click.echo("\\n📞 Step 2: Review Scheduled Calls")
    for i, call in enumerate(llm_result['scheduled_calls'], 1):
        click.echo(f"  {i}. {call['call_type']} - Priority {call['priority']} - {call['scheduled_time'].strftime('%H:%M')}")
    
    # Step 3: Execute first call
    if llm_result['scheduled_calls']:
        click.echo("\\n🚀 Step 3: Execute First Call (Demo)")
        first_call = llm_result['scheduled_calls'][0]
        exec_result = trigger.trigger_call_immediately(first_call['call_id'], mock_execution=True)
        
        if exec_result['success']:
            click.echo(f"✅ Call executed: {exec_result.get('message')}")
            if 'patient_responses' in exec_result:
                click.echo(f"💬 Patient feedback: {exec_result['patient_responses']}")
        else:
            click.echo(f"❌ Call execution failed: {exec_result['error']}")
    
    click.echo("\\n🎉 Demo scenario complete!")


if __name__ == '__main__':
    cli()