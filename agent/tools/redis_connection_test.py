#!/usr/bin/env python3
"""
Redis Connection Diagnostic Tool

This tool systematically tests Redis connections with different parameters
to diagnose connection issues in the PostOp AI system.
"""

import os
import redis
import sys
from typing import Dict, Any

def test_redis_connection(host: str, port: int, db: int = 0) -> Dict[str, Any]:
    """
    Test Redis connection with given parameters
    
    Returns:
        Dict with connection test results
    """
    result = {
        'host': host,
        'port': port,
        'db': db,
        'connected': False,
        'ping_result': None,
        'error': None,
        'connection_info': {}
    }
    
    try:
        client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        
        # Test connection
        ping_result = client.ping()
        result['connected'] = True
        result['ping_result'] = ping_result
        
        # Get connection info
        result['connection_info'] = {
            'host': client.connection_pool.connection_kwargs.get('host'),
            'port': client.connection_pool.connection_kwargs.get('port'),
            'db': client.connection_pool.connection_kwargs.get('db'),
        }
        
        # Test basic operations
        client.set('test_key', 'test_value')
        test_get = client.get('test_key')
        client.delete('test_key')
        result['basic_ops'] = test_get == 'test_value'
        
    except Exception as e:
        result['error'] = str(e)
    
    return result

def run_comprehensive_redis_test():
    """Run comprehensive Redis connection tests"""
    
    print("🔬 Redis Connection Diagnostic Tool")
    print("=" * 50)
    
    # Test scenarios
    test_scenarios = [
        {
            'name': 'Environment Variables',
            'host': os.environ.get('REDIS_HOST', 'localhost'),
            'port': int(os.environ.get('REDIS_PORT', 6379)),
            'db': int(os.environ.get('REDIS_DB', 0))
        },
        {
            'name': 'Docker Container Name',
            'host': 'redis',
            'port': 6379,
            'db': 0
        },
        {
            'name': 'Localhost (Traditional)',
            'host': 'localhost',
            'port': 6379,
            'db': 0
        },
        {
            'name': 'IP Address (if available)',
            'host': '172.19.0.2',  # From DNS resolution test
            'port': 6379,
            'db': 0
        }
    ]
    
    results = []
    
    for scenario in test_scenarios:
        print(f"\n🧪 Testing: {scenario['name']}")
        print(f"   Connection: {scenario['host']}:{scenario['port']}/{scenario['db']}")
        
        result = test_redis_connection(scenario['host'], scenario['port'], scenario['db'])
        results.append(result)
        
        if result['connected']:
            print(f"   ✅ SUCCESS - Ping: {result['ping_result']}, Basic Ops: {result.get('basic_ops', False)}")
        else:
            print(f"   ❌ FAILED - Error: {result['error']}")
    
    # Summary
    print(f"\n📊 DIAGNOSTIC SUMMARY")
    print("=" * 30)
    
    successful_connections = [r for r in results if r['connected']]
    failed_connections = [r for r in results if not r['connected']]
    
    print(f"✅ Successful connections: {len(successful_connections)}")
    print(f"❌ Failed connections: {len(failed_connections)}")
    
    if successful_connections:
        print(f"\n🎯 WORKING CONNECTIONS:")
        for conn in successful_connections:
            print(f"   • {conn['host']}:{conn['port']} - Ping: {conn['ping_result']}")
    
    if failed_connections:
        print(f"\n💥 FAILED CONNECTIONS:")
        for conn in failed_connections:
            print(f"   • {conn['host']}:{conn['port']} - {conn['error']}")
    
    # Environment analysis
    print(f"\n🌍 ENVIRONMENT ANALYSIS:")
    print(f"   REDIS_HOST: {os.environ.get('REDIS_HOST', 'NOT_SET')}")
    print(f"   REDIS_PORT: {os.environ.get('REDIS_PORT', 'NOT_SET')}")
    print(f"   REDIS_DB: {os.environ.get('REDIS_DB', 'NOT_SET')}")
    print(f"   REDIS_URL: {os.environ.get('REDIS_URL', 'NOT_SET')}")
    
    return results

def test_call_scheduler_connection():
    """Test the actual CallScheduler class connection"""
    print(f"\n🎯 TESTING CALLSCHEDULER CLASS")
    print("=" * 40)
    
    # Add current directory to path
    sys.path.append('.')
    
    try:
        from scheduling.scheduler import CallScheduler
        
        # Test default
        print("Testing CallScheduler with defaults...")
        try:
            scheduler_default = CallScheduler()
            ping_result = scheduler_default.redis_client.ping()
            host = scheduler_default.redis_client.connection_pool.connection_kwargs.get('host')
            port = scheduler_default.redis_client.connection_pool.connection_kwargs.get('port')
            print(f"✅ Default CallScheduler works: {host}:{port} - Ping: {ping_result}")
        except Exception as e:
            print(f"❌ Default CallScheduler failed: {e}")
        
        # Test with environment variables
        print("Testing CallScheduler with environment variables...")
        try:
            redis_host = os.environ.get('REDIS_HOST', 'localhost')
            redis_port = int(os.environ.get('REDIS_PORT', 6379))
            scheduler_env = CallScheduler(redis_host=redis_host, redis_port=redis_port)
            ping_result = scheduler_env.redis_client.ping()
            print(f"✅ Environment CallScheduler works: {redis_host}:{redis_port} - Ping: {ping_result}")
        except Exception as e:
            print(f"❌ Environment CallScheduler failed: {e}")
            
    except ImportError as e:
        print(f"❌ Could not import CallScheduler: {e}")

if __name__ == '__main__':
    results = run_comprehensive_redis_test()
    test_call_scheduler_connection()