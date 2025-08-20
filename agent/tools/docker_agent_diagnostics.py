#!/usr/bin/env python3
"""
Docker Agent Diagnostics Tool

This tool provides comprehensive diagnostics for the PostOp AI agent
running in Docker environment to identify why it's not answering inbound calls.

Scientific approach:
1. Test LiveKit API connectivity from Docker
2. Verify agent registration status
3. Check environment variables
4. Test DNS resolution and networking
5. Analyze service dependencies
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, List
import requests
try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    HAS_DNS = False

# Add current directory to Python path for imports
sys.path.append('/Users/chris/dev/livekit-postop')

class DockerAgentDiagnostics:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'summary': {
                'total_tests': 0,
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }
        
    def log_test(self, test_name: str, passed: bool, details: Dict[str, Any], warning: bool = False):
        """Log test results"""
        status = 'WARNING' if warning else ('PASS' if passed else 'FAIL')
        self.results['tests'][test_name] = {
            'status': status,
            'passed': passed,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        
        self.results['summary']['total_tests'] += 1
        if warning:
            self.results['summary']['warnings'] += 1
        elif passed:
            self.results['summary']['passed'] += 1
        else:
            self.results['summary']['failed'] += 1
            
        print(f"{'🟡' if warning else '✅' if passed else '❌'} {test_name}: {status}")
        if details.get('message'):
            print(f"   {details['message']}")
            
    def test_docker_container_status(self):
        """Test if Docker containers are running"""
        try:
            result = subprocess.run(['docker-compose', 'ps'], 
                                  capture_output=True, text=True, 
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                output = result.stdout
                lines = output.strip().split('\n')
                
                # Parse container status
                containers = {}
                for line in lines[2:]:  # Skip header lines
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[0]
                            status = 'Up' if 'Up' in line else 'Down'
                            containers[name] = status
                
                all_up = all(status == 'Up' for status in containers.values())
                
                self.log_test(
                    'docker_container_status',
                    all_up,
                    {
                        'message': f"Container status: {containers}",
                        'containers': containers,
                        'output': output
                    },
                    warning=not all_up
                )
            else:
                self.log_test(
                    'docker_container_status',
                    False,
                    {
                        'message': f"Docker compose ps failed: {result.stderr}",
                        'error': result.stderr
                    }
                )
        except Exception as e:
            self.log_test(
                'docker_container_status',
                False,
                {
                    'message': f"Exception running docker-compose ps: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_environment_variables_in_docker(self):
        """Test environment variables inside Docker container"""
        required_vars = [
            'LIVEKIT_AGENT_NAME',
            'LIVEKIT_API_KEY', 
            'LIVEKIT_API_SECRET',
            'LIVEKIT_URL',
            'REDIS_HOST'
        ]
        
        try:
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'env']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                env_vars = {}
                for line in result.stdout.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key] = value
                
                missing_vars = []
                present_vars = {}
                
                for var in required_vars:
                    if var in env_vars:
                        # Mask sensitive values
                        if 'KEY' in var or 'SECRET' in var:
                            present_vars[var] = '***MASKED***'
                        else:
                            present_vars[var] = env_vars[var]
                    else:
                        missing_vars.append(var)
                
                all_present = len(missing_vars) == 0
                
                self.log_test(
                    'docker_environment_variables',
                    all_present,
                    {
                        'message': f"Missing vars: {missing_vars}" if missing_vars else "All required vars present",
                        'present_vars': present_vars,
                        'missing_vars': missing_vars,
                        'total_env_vars': len(env_vars)
                    }
                )
            else:
                self.log_test(
                    'docker_environment_variables',
                    False,
                    {
                        'message': f"Failed to get env vars: {result.stderr}",
                        'error': result.stderr
                    }
                )
        except Exception as e:
            self.log_test(
                'docker_environment_variables',
                False,
                {
                    'message': f"Exception getting Docker env vars: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_network_connectivity_from_docker(self):
        """Test network connectivity from inside Docker container"""
        test_urls = [
            'https://api.livekit.io',
            'https://google.com',  # Basic internet
            'https://api.deepgram.com',  # Deepgram API
            'https://api.openai.com'  # OpenAI API
        ]
        
        for url in test_urls:
            try:
                cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 
                       'python', '-c', f'''
import requests
import time
try:
    start = time.time()
    response = requests.get("{url}", timeout=10)
    end = time.time()
    print(f"STATUS:{response.status_code}")
    print(f"TIME:{end-start:.2f}")
    print(f"SIZE:{len(response.content)}")
except Exception as e:
    print(f"ERROR:{str(e)}")
''']
                
                result = subprocess.run(cmd, capture_output=True, text=True,
                                      cwd='/Users/chris/dev/livekit-postop', timeout=15)
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    details = {}
                    
                    for line in output.split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            details[key.lower()] = value
                    
                    success = 'error' not in details and details.get('status') == '200'
                    
                    self.log_test(
                        f'network_connectivity_{url.replace("https://", "").replace("/", "_")}',
                        success,
                        {
                            'message': f"{url}: {details.get('status', 'ERROR')} in {details.get('time', 'N/A')}s",
                            'url': url,
                            'response_details': details
                        }
                    )
                else:
                    self.log_test(
                        f'network_connectivity_{url.replace("https://", "").replace("/", "_")}',
                        False,
                        {
                            'message': f"Failed to test {url}: {result.stderr}",
                            'url': url,
                            'error': result.stderr
                        }
                    )
            except subprocess.TimeoutExpired:
                self.log_test(
                    f'network_connectivity_{url.replace("https://", "").replace("/", "_")}',
                    False,
                    {
                        'message': f"Timeout testing {url}",
                        'url': url,
                        'error': 'Timeout after 15 seconds'
                    }
                )
            except Exception as e:
                self.log_test(
                    f'network_connectivity_{url.replace("https://", "").replace("/", "_")}',
                    False,
                    {
                        'message': f"Exception testing {url}: {str(e)}",
                        'url': url,
                        'error': str(e)
                    }
                )
    
    def test_redis_connectivity_from_docker(self):
        """Test Redis connectivity from Docker container"""
        try:
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 
                   'python', '-c', '''
import redis
import os
try:
    # Test default connection (should use REDIS_HOST env var)
    client = redis.Redis(host=os.environ.get("REDIS_HOST", "redis"), 
                        port=int(os.environ.get("REDIS_PORT", 6379)), 
                        decode_responses=True)
    ping_result = client.ping()
    print(f"PING:{ping_result}")
    print(f"HOST:{client.connection_pool.connection_kwargs.get('host')}")
    print(f"PORT:{client.connection_pool.connection_kwargs.get('port')}")
    
    # Test basic operations
    client.set("docker_test", "success")
    get_result = client.get("docker_test")
    client.delete("docker_test")
    print(f"OPS:{get_result == 'success'}")
    
except Exception as e:
    print(f"ERROR:{str(e)}")
''']
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                output = result.stdout.strip()
                details = {}
                
                for line in output.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        details[key.lower()] = value
                
                success = 'error' not in details and details.get('ping') == 'True'
                
                self.log_test(
                    'docker_redis_connectivity',
                    success,
                    {
                        'message': f"Redis connection: {details}",
                        'redis_details': details
                    }
                )
            else:
                self.log_test(
                    'docker_redis_connectivity',
                    False,
                    {
                        'message': f"Failed to test Redis: {result.stderr}",
                        'error': result.stderr
                    }
                )
        except Exception as e:
            self.log_test(
                'docker_redis_connectivity',
                False,
                {
                    'message': f"Exception testing Redis: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_agent_process_in_docker(self):
        """Test if agent process is running inside Docker"""
        try:
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'ps', 'aux']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                processes = result.stdout
                
                # Look for Python agent processes
                python_processes = []
                agent_processes = []
                
                for line in processes.split('\n'):
                    if 'python' in line.lower():
                        python_processes.append(line.strip())
                        if 'main.py' in line or 'discharge' in line:
                            agent_processes.append(line.strip())
                
                agent_running = len(agent_processes) > 0
                
                self.log_test(
                    'docker_agent_process',
                    agent_running,
                    {
                        'message': f"Found {len(agent_processes)} agent processes",
                        'agent_processes': agent_processes,
                        'python_processes': python_processes
                    }
                )
            else:
                self.log_test(
                    'docker_agent_process',
                    False,
                    {
                        'message': f"Failed to check processes: {result.stderr}",
                        'error': result.stderr
                    }
                )
        except Exception as e:
            self.log_test(
                'docker_agent_process',
                False,
                {
                    'message': f"Exception checking processes: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_docker_logs_for_errors(self):
        """Check Docker logs for errors"""
        services = ['postop-agent', 'postop-scheduler', 'postop-worker']
        
        for service in services:
            try:
                cmd = ['docker-compose', 'logs', '--tail=50', service]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                      cwd='/Users/chris/dev/livekit-postop')
                
                if result.returncode == 0:
                    logs = result.stdout
                    
                    # Look for error indicators
                    error_indicators = ['ERROR', 'FAILED', 'Exception', 'Traceback', 'CRITICAL']
                    errors_found = []
                    
                    for line in logs.split('\n'):
                        for indicator in error_indicators:
                            if indicator in line:
                                errors_found.append(line.strip())
                                break
                    
                    has_errors = len(errors_found) > 0
                    
                    self.log_test(
                        f'docker_logs_{service}',
                        not has_errors,
                        {
                            'message': f"Found {len(errors_found)} error lines" if has_errors else "No errors in recent logs",
                            'service': service,
                            'errors_found': errors_found[:10],  # Limit to first 10 errors
                            'total_log_lines': len(logs.split('\n'))
                        },
                        warning=has_errors
                    )
                else:
                    self.log_test(
                        f'docker_logs_{service}',
                        False,
                        {
                            'message': f"Failed to get logs: {result.stderr}",
                            'service': service,
                            'error': result.stderr
                        }
                    )
            except Exception as e:
                self.log_test(
                    f'docker_logs_{service}',
                    False,
                    {
                        'message': f"Exception getting logs: {str(e)}",
                        'service': service,
                        'error': str(e)
                    }
                )
    
    def run_all_diagnostics(self):
        """Run all diagnostic tests"""
        print("🔬 Docker Agent Diagnostics")
        print("=" * 50)
        print("Running comprehensive diagnostics...")
        print()
        
        # Run all tests
        self.test_docker_container_status()
        self.test_environment_variables_in_docker()
        self.test_network_connectivity_from_docker()
        self.test_redis_connectivity_from_docker()
        self.test_agent_process_in_docker()
        self.test_docker_logs_for_errors()
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 DIAGNOSTIC SUMMARY")
        print("=" * 50)
        
        summary = self.results['summary']
        print(f"Total Tests: {summary['total_tests']}")
        print(f"✅ Passed: {summary['passed']}")
        print(f"❌ Failed: {summary['failed']}")
        print(f"🟡 Warnings: {summary['warnings']}")
        
        # Key findings
        print(f"\n🔍 KEY FINDINGS:")
        
        failed_tests = [(name, test) for name, test in self.results['tests'].items() 
                       if test['status'] == 'FAIL']
        
        if failed_tests:
            print("❌ CRITICAL ISSUES:")
            for name, test in failed_tests:
                print(f"   • {name}: {test['details'].get('message', 'No details')}")
        
        warning_tests = [(name, test) for name, test in self.results['tests'].items() 
                        if test['status'] == 'WARNING']
        
        if warning_tests:
            print("🟡 WARNINGS:")
            for name, test in warning_tests:
                print(f"   • {name}: {test['details'].get('message', 'No details')}")
        
        if not failed_tests and not warning_tests:
            print("✅ All diagnostics passed!")
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save diagnostic results to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/Users/chris/dev/livekit-postop/docker_diagnostics_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

def main():
    """Main function"""
    diagnostics = DockerAgentDiagnostics()
    
    try:
        results = diagnostics.run_all_diagnostics()
        diagnostics.save_results()
        
        # Exit with error code if there are failures
        if results['summary']['failed'] > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Diagnostics interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()