#!/usr/bin/env python3
"""
Redis Fix Verification Tool

This tool verifies that the Redis connection issue has been resolved
by testing both the CallScheduler class and CLI tool functionality.
"""

import sys
import os
from typing import Dict, Any, List

def test_call_scheduler_defaults() -> Dict[str, Any]:
    """Test CallScheduler with default parameters"""
    print("🧪 Testing CallScheduler with defaults...")
    
    sys.path.append('.')
    from scheduling.scheduler import CallScheduler
    
    result = {
        'test_name': 'CallScheduler Defaults',
        'success': False,
        'error': None,
        'connection_info': {},
        'ping_result': None
    }
    
    try:
        scheduler = CallScheduler()  # No parameters - should use environment variables
        
        # Get connection info
        result['connection_info'] = {
            'host': scheduler.redis_client.connection_pool.connection_kwargs.get('host'),
            'port': scheduler.redis_client.connection_pool.connection_kwargs.get('port'),
            'db': scheduler.redis_client.connection_pool.connection_kwargs.get('db', 0)
        }
        
        # Test connection
        ping_result = scheduler.redis_client.ping()
        result['ping_result'] = ping_result
        result['success'] = True
        
        print(f"   ✅ SUCCESS - Connected to {result['connection_info']['host']}:{result['connection_info']['port']}")
        print(f"   📡 Ping result: {ping_result}")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"   ❌ FAILED - {e}")
    
    return result

def test_call_scheduler_manager() -> Dict[str, Any]:
    """Test CallSchedulerManager (CLI tool class)"""
    print("\n🧪 Testing CallSchedulerManager...")
    
    sys.path.append('.')
    from tools.call_scheduler_cli import CallSchedulerManager
    
    result = {
        'test_name': 'CallSchedulerManager',
        'success': False,
        'error': None,
        'connection_info': {},
        'ping_result': None
    }
    
    try:
        manager = CallSchedulerManager()  # Should now work with defaults
        
        # Get connection info
        result['connection_info'] = {
            'host': manager.scheduler.redis_client.connection_pool.connection_kwargs.get('host'),
            'port': manager.scheduler.redis_client.connection_pool.connection_kwargs.get('port'),
            'db': manager.scheduler.redis_client.connection_pool.connection_kwargs.get('db', 0)
        }
        
        # Test connection
        ping_result = manager.scheduler.redis_client.ping()
        result['ping_result'] = ping_result
        result['success'] = True
        
        print(f"   ✅ SUCCESS - Connected to {result['connection_info']['host']}:{result['connection_info']['port']}")
        print(f"   📡 Ping result: {ping_result}")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"   ❌ FAILED - {e}")
    
    return result

def test_cli_commands() -> List[Dict[str, Any]]:
    """Test actual CLI commands"""
    print("\n🧪 Testing CLI Commands...")
    
    import subprocess
    
    cli_tests = [
        {
            'name': 'redis-status',
            'command': ['python', 'tools/call_scheduler_cli.py', 'redis-status'],
            'expected_keywords': ['Redis connection:', 'OK']
        },
        {
            'name': 'stats',
            'command': ['python', 'tools/call_scheduler_cli.py', 'stats'],
            'expected_keywords': ['Call Scheduling Statistics', 'Total pending calls']
        }
    ]
    
    results = []
    
    for test in cli_tests:
        print(f"   🔧 Testing CLI command: {test['name']}")
        
        result = {
            'test_name': f"CLI {test['name']}",
            'success': False,
            'error': None,
            'output': None
        }
        
        try:
            proc = subprocess.run(
                test['command'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            result['output'] = proc.stdout + proc.stderr
            
            # Check if expected keywords are in output
            success_indicators = [keyword in result['output'] for keyword in test['expected_keywords']]
            error_indicators = ['Error' in result['output'], 'Connection refused' in result['output']]
            
            if any(success_indicators) and not any(error_indicators):
                result['success'] = True
                print(f"      ✅ SUCCESS")
            else:
                result['success'] = False
                print(f"      ❌ FAILED - Output didn't contain expected keywords or had errors")
                print(f"      📝 Output: {result['output'][:200]}...")
                
        except subprocess.TimeoutExpired:
            result['error'] = "Command timeout"
            print(f"      ❌ FAILED - Command timeout")
        except Exception as e:
            result['error'] = str(e)
            print(f"      ❌ FAILED - {e}")
        
        results.append(result)
    
    return results

def test_functional_operations() -> Dict[str, Any]:
    """Test that we can actually perform Redis operations"""
    print("\n🧪 Testing Functional Operations...")
    
    sys.path.append('.')
    from scheduling.scheduler import CallScheduler
    from scheduling.models import CallScheduleItem, CallType, CallStatus
    from datetime import datetime, timedelta
    
    result = {
        'test_name': 'Functional Operations',
        'success': False,
        'error': None,
        'operations_completed': []
    }
    
    try:
        scheduler = CallScheduler()
        
        # Test 1: Generate test calls
        print("   📞 Testing call generation...")
        calls = scheduler.generate_calls_for_patient(
            patient_id='test-verification-001',
            patient_phone='+1555000999',
            patient_name='Verification Patient',
            discharge_time=datetime.now(),
            selected_order_ids=['vm_compression', 'vm_activity']
        )
        
        if len(calls) > 0:
            result['operations_completed'].append('call_generation')
            print(f"      ✅ Generated {len(calls)} calls")
        
        # Test 2: Schedule calls
        print("   💾 Testing call scheduling...")
        scheduled_count = 0
        for call in calls:
            if scheduler.schedule_call(call):
                scheduled_count += 1
        
        if scheduled_count == len(calls):
            result['operations_completed'].append('call_scheduling')
            print(f"      ✅ Scheduled {scheduled_count} calls")
        
        # Test 3: Retrieve calls
        print("   📋 Testing call retrieval...")
        pending_calls = scheduler.get_pending_calls(limit=10)
        verification_calls = [c for c in pending_calls if c.patient_id == 'test-verification-001']
        
        if len(verification_calls) > 0:
            result['operations_completed'].append('call_retrieval')
            print(f"      ✅ Retrieved {len(verification_calls)} verification calls")
        
        # Test 4: Update call status
        print("   🔄 Testing status updates...")
        if verification_calls:
            test_call = verification_calls[0]
            if scheduler.update_call_status(test_call.id, CallStatus.COMPLETED, "Verification test"):
                result['operations_completed'].append('status_update')
                print(f"      ✅ Updated call status")
        
        # Cleanup
        print("   🧹 Cleaning up test data...")
        for call in verification_calls:
            scheduler.redis_client.delete(f"postop:scheduled_calls:{call.id}")
        
        result['success'] = len(result['operations_completed']) >= 3
        
    except Exception as e:
        result['error'] = str(e)
        print(f"   ❌ FAILED - {e}")
    
    return result

def run_comprehensive_verification():
    """Run all verification tests"""
    print("🔬 Redis Fix Comprehensive Verification")
    print("=" * 50)
    
    # Environment check
    print(f"🌍 Environment Check:")
    print(f"   REDIS_HOST: {os.environ.get('REDIS_HOST', 'NOT_SET')}")
    print(f"   REDIS_PORT: {os.environ.get('REDIS_PORT', 'NOT_SET')}")
    print(f"   REDIS_DB: {os.environ.get('REDIS_DB', 'NOT_SET')}")
    
    # Run all tests
    all_results = []
    
    # Core class tests
    all_results.append(test_call_scheduler_defaults())
    all_results.append(test_call_scheduler_manager())
    
    # CLI tests
    cli_results = test_cli_commands()
    all_results.extend(cli_results)
    
    # Functional tests
    all_results.append(test_functional_operations())
    
    # Summary
    print(f"\n📊 VERIFICATION SUMMARY")
    print("=" * 30)
    
    successful_tests = [r for r in all_results if r['success']]
    failed_tests = [r for r in all_results if not r['success']]
    
    print(f"✅ Successful tests: {len(successful_tests)}/{len(all_results)}")
    print(f"❌ Failed tests: {len(failed_tests)}")
    
    if successful_tests:
        print(f"\n🎯 WORKING TESTS:")
        for test in successful_tests:
            print(f"   ✅ {test['test_name']}")
    
    if failed_tests:
        print(f"\n💥 FAILED TESTS:")
        for test in failed_tests:
            print(f"   ❌ {test['test_name']}: {test.get('error', 'Unknown error')}")
    
    # Overall result
    success_rate = len(successful_tests) / len(all_results)
    
    if success_rate >= 0.8:  # 80% success rate
        print(f"\n🎉 VERIFICATION PASSED! ({success_rate:.1%} success rate)")
        print("✅ Redis connection issue has been resolved!")
        return True
    else:
        print(f"\n❌ VERIFICATION FAILED! ({success_rate:.1%} success rate)")
        print("🔧 Additional fixes may be needed.")
        return False

if __name__ == '__main__':
    success = run_comprehensive_verification()
    sys.exit(0 if success else 1)