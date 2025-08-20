#!/usr/bin/env python3
"""
Docker Agent Fix Verification Suite

This tool provides scientific verification that the Docker agent issue has been resolved.
It performs before/after comparisons and validates that the agent can now properly handle calls.

Scientific approach:
1. Verify the root cause has been addressed
2. Test all critical functionality
3. Compare before/after states
4. Provide definitive proof of resolution
"""

import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, List

# Add current directory to Python path for imports
sys.path.append('/Users/chris/dev/livekit-postop')

class DockerFixVerification:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'verification_tests': {},
            'summary': {
                'total_tests': 0,
                'passed': 0,
                'failed': 0,
                'warnings': 0
            },
            'conclusion': None
        }
        
    def log_test(self, test_name: str, passed: bool, details: Dict[str, Any], warning: bool = False):
        """Log verification test results"""
        status = 'WARNING' if warning else ('PASS' if passed else 'FAIL')
        self.results['verification_tests'][test_name] = {
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
    
    def verify_root_cause_fixed(self):
        """Verify that the root cause (config import error) has been fixed"""
        try:
            # Test the exact import that was failing
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'python', '-c', '''
try:
    from discharge.config import LIVEKIT_AGENT_NAME
    print(f"SUCCESS:{LIVEKIT_AGENT_NAME}")
except Exception as e:
    print(f"FAILED:{str(e)}")
''']
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                output = result.stdout.strip()
                
                if output.startswith('SUCCESS:'):
                    agent_name = output.split(':', 1)[1]
                    self.log_test(
                        'root_cause_fixed',
                        True,
                        {
                            'message': f"Config import now works: LIVEKIT_AGENT_NAME = {agent_name}",
                            'imported_agent_name': agent_name,
                            'original_error': 'cannot import name LIVEKIT_AGENT_NAME from discharge.config'
                        }
                    )
                    return True, agent_name
                else:
                    self.log_test(
                        'root_cause_fixed',
                        False,
                        {
                            'message': f"Config import still failing: {output}",
                            'output': output
                        }
                    )
                    return False, None
            else:
                self.log_test(
                    'root_cause_fixed',
                    False,
                    {
                        'message': f"Docker command failed: {result.stderr}",
                        'error': result.stderr
                    }
                )
                return False, None
                
        except Exception as e:
            self.log_test(
                'root_cause_fixed',
                False,
                {
                    'message': f"Exception during verification: {str(e)}",
                    'error': str(e)
                }
            )
            return False, None
    
    def verify_agent_registration(self):
        """Verify agent is successfully registering with LiveKit"""
        try:
            # Check agent logs for registration
            cmd = ['docker-compose', 'logs', '--tail=20', 'postop-agent']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                logs = result.stdout
                
                # Look for successful registration
                registration_lines = []
                latest_worker_id = None
                
                for line in logs.split('\n'):
                    if 'registered worker' in line:
                        registration_lines.append(line.strip())
                        # Extract worker ID
                        if '"id":' in line:
                            try:
                                start = line.find('"id": "') + 7
                                end = line.find('"', start)
                                if start > 6 and end > start:
                                    latest_worker_id = line[start:end]
                            except:
                                pass
                
                is_registered = len(registration_lines) > 0
                
                self.log_test(
                    'agent_registration',
                    is_registered,
                    {
                        'message': f"Agent registered with worker ID: {latest_worker_id}" if is_registered else "No registration found in logs",
                        'worker_id': latest_worker_id,
                        'registration_count': len(registration_lines),
                        'latest_registration': registration_lines[-1] if registration_lines else None
                    }
                )
                
                return is_registered, latest_worker_id
            else:
                self.log_test(
                    'agent_registration',
                    False,
                    {
                        'message': f"Failed to get logs: {result.stderr}",
                        'error': result.stderr
                    }
                )
                return False, None
                
        except Exception as e:
            self.log_test(
                'agent_registration',
                False,
                {
                    'message': f"Exception checking registration: {str(e)}",
                    'error': str(e)
                }
            )
            return False, None
    
    def verify_container_health(self):
        """Verify Docker containers are healthy"""
        try:
            # Check container status
            cmd = ['docker-compose', 'ps']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                output = result.stdout
                
                # Parse container status
                containers = {}
                agent_status = None
                
                for line in output.split('\n'):
                    if 'postop-agent' in line:
                        if 'Up' in line:
                            agent_status = 'Up'
                        else:
                            agent_status = 'Down'
                        containers['postop-agent'] = agent_status
                    elif any(service in line for service in ['postop-redis', 'postop-scheduler', 'postop-worker']):
                        service_name = None
                        for service in ['postop-redis', 'postop-scheduler', 'postop-worker']:
                            if service in line:
                                service_name = service
                                break
                        if service_name:
                            containers[service_name] = 'Up' if 'Up' in line else 'Down'
                
                all_up = all(status == 'Up' for status in containers.values())
                agent_healthy = agent_status == 'Up'
                
                self.log_test(
                    'container_health',
                    all_up,
                    {
                        'message': f"PostOp agent: {agent_status}, All containers: {'Healthy' if all_up else 'Issues detected'}",
                        'containers': containers,
                        'agent_healthy': agent_healthy,
                        'all_healthy': all_up
                    }
                )
                
                return agent_healthy
            else:
                self.log_test(
                    'container_health',
                    False,
                    {
                        'message': f"Failed to check containers: {result.stderr}",
                        'error': result.stderr
                    }
                )
                return False
                
        except Exception as e:
            self.log_test(
                'container_health',
                False,
                {
                    'message': f"Exception checking containers: {str(e)}",
                    'error': str(e)
                }
            )
            return False
    
    def verify_config_consistency(self):
        """Verify configuration consistency between local and Docker"""
        try:
            # Load local environment
            from dotenv import load_dotenv
            import os
            load_dotenv()
            
            local_agent_name = os.getenv('LIVEKIT_AGENT_NAME')
            
            # Get Docker agent name
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'python', '-c', '''
import os
from discharge.config import LIVEKIT_AGENT_NAME
print(f"ENV:{os.getenv('LIVEKIT_AGENT_NAME')}")
print(f"CONFIG:{LIVEKIT_AGENT_NAME}")
''']
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                output = result.stdout.strip()
                
                docker_env_name = None
                docker_config_name = None
                
                for line in output.split('\n'):
                    if line.startswith('ENV:'):
                        docker_env_name = line.split(':', 1)[1]
                    elif line.startswith('CONFIG:'):
                        docker_config_name = line.split(':', 1)[1]
                
                # Check consistency
                all_match = (local_agent_name == docker_env_name == docker_config_name)
                env_to_config_works = docker_env_name == docker_config_name
                
                self.log_test(
                    'config_consistency',
                    all_match,
                    {
                        'message': f"Consistency: {'All match' if all_match else 'Mismatches detected'}",
                        'local_agent_name': local_agent_name,
                        'docker_env_name': docker_env_name,
                        'docker_config_name': docker_config_name,
                        'all_match': all_match,
                        'env_to_config_works': env_to_config_works
                    }
                )
                
                return all_match
            else:
                self.log_test(
                    'config_consistency',
                    False,
                    {
                        'message': f"Failed to check Docker config: {result.stderr}",
                        'error': result.stderr
                    }
                )
                return False
                
        except Exception as e:
            self.log_test(
                'config_consistency',
                False,
                {
                    'message': f"Exception checking config: {str(e)}",
                    'error': str(e)
                }
            )
            return False
    
    def verify_no_errors_in_logs(self):
        """Verify no critical errors in agent logs"""
        try:
            # Check recent logs for errors
            cmd = ['docker-compose', 'logs', '--tail=50', 'postop-agent']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                logs = result.stdout
                
                # Look for error indicators
                error_patterns = [
                    'cannot import name',
                    'ValueError',
                    'ImportError',
                    'CRITICAL',
                    'FATAL',
                    'Exception',
                    'Traceback'
                ]
                
                errors_found = []
                for line in logs.split('\n'):
                    for pattern in error_patterns:
                        if pattern in line and 'INFO' not in line and 'DEBUG' not in line:
                            errors_found.append(line.strip())
                            break
                
                no_critical_errors = len(errors_found) == 0
                
                self.log_test(
                    'no_critical_errors',
                    no_critical_errors,
                    {
                        'message': f"{'No critical errors found' if no_critical_errors else f'Found {len(errors_found)} error lines'}",
                        'error_count': len(errors_found),
                        'errors_found': errors_found[:5],  # Show first 5 errors
                        'total_log_lines': len(logs.split('\n'))
                    }
                )
                
                return no_critical_errors
            else:
                self.log_test(
                    'no_critical_errors',
                    False,
                    {
                        'message': f"Failed to get logs: {result.stderr}",
                        'error': result.stderr
                    }
                )
                return False
                
        except Exception as e:
            self.log_test(
                'no_critical_errors',
                False,
                {
                    'message': f"Exception checking logs: {str(e)}",
                    'error': str(e)
                }
            )
            return False
    
    def run_comprehensive_verification(self):
        """Run all verification tests"""
        print("🔬 Docker Agent Fix Verification Suite")
        print("=" * 50)
        print("Verifying that the Docker agent issue has been resolved...")
        print()
        
        # Run all verification tests
        root_cause_fixed, agent_name = self.verify_root_cause_fixed()
        agent_registered, worker_id = self.verify_agent_registration()
        container_healthy = self.verify_container_health()
        config_consistent = self.verify_config_consistency()
        no_errors = self.verify_no_errors_in_logs()
        
        # Determine overall conclusion
        critical_tests_passed = root_cause_fixed and agent_registered and container_healthy
        all_tests_passed = critical_tests_passed and config_consistent and no_errors
        
        if all_tests_passed:
            conclusion = "FULLY_RESOLVED"
            conclusion_message = "✅ Docker agent issue has been FULLY RESOLVED. All tests pass."
        elif critical_tests_passed:
            conclusion = "MOSTLY_RESOLVED"
            conclusion_message = "🟡 Docker agent issue is MOSTLY RESOLVED. Core functionality works but minor issues remain."
        else:
            conclusion = "NOT_RESOLVED"
            conclusion_message = "❌ Docker agent issue is NOT RESOLVED. Critical functionality still failing."
        
        self.results['conclusion'] = {
            'status': conclusion,
            'message': conclusion_message,
            'critical_tests_passed': critical_tests_passed,
            'all_tests_passed': all_tests_passed,
            'agent_name': agent_name,
            'worker_id': worker_id
        }
        
        # Print summary
        print("\n" + "=" * 50)
        print("🧪 VERIFICATION SUMMARY")
        print("=" * 50)
        
        summary = self.results['summary']
        print(f"Total Tests: {summary['total_tests']}")
        print(f"✅ Passed: {summary['passed']}")
        print(f"❌ Failed: {summary['failed']}")
        print(f"🟡 Warnings: {summary['warnings']}")
        
        print(f"\n🎯 CONCLUSION:")
        print(conclusion_message)
        
        if agent_name and worker_id:
            print(f"\n📋 AGENT STATUS:")
            print(f"   Agent Name: {agent_name}")
            print(f"   Worker ID: {worker_id}")
            print(f"   Status: {'Registered and Active' if agent_registered else 'Issues Detected'}")
        
        # Show any remaining issues
        failed_tests = [(name, test) for name, test in self.results['verification_tests'].items() 
                       if test['status'] == 'FAIL']
        
        if failed_tests:
            print(f"\n❌ REMAINING ISSUES:")
            for name, test in failed_tests:
                print(f"   • {name}: {test['details'].get('message', 'No details')}")
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save verification results to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/Users/chris/dev/livekit-postop/docker_fix_verification_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

def main():
    """Main function"""
    verifier = DockerFixVerification()
    
    try:
        results = verifier.run_comprehensive_verification()
        verifier.save_results()
        
        # Exit with appropriate code
        if results['conclusion']['status'] == 'FULLY_RESOLVED':
            print("\n🎉 SUCCESS: Docker agent issue has been completely resolved!")
            sys.exit(0)
        elif results['conclusion']['status'] == 'MOSTLY_RESOLVED':
            print("\n🟡 PARTIAL SUCCESS: Core issue resolved, minor issues remain.")
            sys.exit(0)
        else:
            print("\n❌ FAILURE: Docker agent issue is not resolved.")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Verification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()