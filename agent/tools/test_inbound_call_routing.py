#!/usr/bin/env python3
"""
Inbound Call Routing Test

This tool tests whether inbound calls are properly routed to the Docker agent
by checking SIP dispatch rules and agent registration.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any

# Add current directory to Python path for imports
sys.path.append('/Users/chris/dev/livekit-postop')

class InboundCallRoutingTest:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'agent_name': os.getenv('LIVEKIT_AGENT_NAME'),
            'hypothesis': 'Docker agent is registered but not receiving calls due to dispatch rule mismatch'
        }
        
    def log_test(self, test_name: str, result: Any, details: Dict[str, Any] = None):
        """Log test results"""
        self.results['tests'][test_name] = {
            'result': result,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"🔍 {test_name}")
        print(f"   Result: {result}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
        print()
    
    def check_docker_agent_registration(self):
        """Check if Docker agent is properly registered"""
        try:
            # Check Docker agent logs for registration
            cmd = ['docker-compose', 'logs', '--tail=50', 'postop-agent']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                logs = result.stdout
                
                # Look for registration success
                registration_lines = []
                worker_id = None
                
                for line in logs.split('\n'):
                    if 'registered worker' in line:
                        registration_lines.append(line.strip())
                        # Extract worker ID
                        if '"id":' in line:
                            try:
                                start = line.find('"id": "') + 7
                                end = line.find('"', start)
                                if start > 6 and end > start:
                                    worker_id = line[start:end]
                            except:
                                pass
                
                is_registered = len(registration_lines) > 0
                
                self.log_test(
                    'docker_agent_registration',
                    'REGISTERED' if is_registered else 'NOT_REGISTERED',
                    {
                        'registration_count': len(registration_lines),
                        'worker_id': worker_id,
                        'latest_registration': registration_lines[-1] if registration_lines else None,
                        'agent_name': self.results['agent_name']
                    }
                )
                
                return is_registered, worker_id
            else:
                self.log_test(
                    'docker_agent_registration',
                    'ERROR',
                    {'error': result.stderr}
                )
                return False, None
                
        except Exception as e:
            self.log_test(
                'docker_agent_registration',
                'EXCEPTION',
                {'error': str(e)}
            )
            return False, None
    
    def check_agent_name_consistency(self):
        """Check if agent name is consistent across all configurations"""
        try:
            # Check Docker environment variable
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'printenv', 'LIVEKIT_AGENT_NAME']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            docker_agent_name = result.stdout.strip() if result.returncode == 0 else 'ERROR'
            local_agent_name = os.getenv('LIVEKIT_AGENT_NAME', 'NOT_SET')
            
            # Check docker-compose.yml
            try:
                with open('/Users/chris/dev/livekit-postop/docker-compose.yml', 'r') as f:
                    compose_content = f.read()
                    
                # Look for agent name in compose file
                compose_has_agent_name = 'LIVEKIT_AGENT_NAME' in compose_content
                
            except Exception as e:
                compose_has_agent_name = f"ERROR: {str(e)}"
            
            names_match = docker_agent_name == local_agent_name
            
            self.log_test(
                'agent_name_consistency',
                'CONSISTENT' if names_match else 'INCONSISTENT',
                {
                    'local_agent_name': local_agent_name,
                    'docker_agent_name': docker_agent_name,
                    'compose_has_agent_name': compose_has_agent_name,
                    'names_match': names_match
                }
            )
            
            return names_match
            
        except Exception as e:
            self.log_test(
                'agent_name_consistency',
                'EXCEPTION',
                {'error': str(e)}
            )
            return False
    
    def check_sip_phone_number_availability(self):
        """Check if there's a phone number configured for inbound calls"""
        # This is informational - we can't easily check the LiveKit dashboard programmatically
        # but we can check environment variables
        
        phone_related_vars = [
            'SIP_INBOUND_NUMBER',
            'SIP_PHONE_NUMBER', 
            'TWILIO_PHONE_NUMBER',
            'PHONE_NUMBER'
        ]
        
        found_vars = {}
        for var in phone_related_vars:
            # Check local environment
            local_val = os.getenv(var)
            if local_val:
                found_vars[f'local_{var}'] = local_val
            
            # Check Docker environment
            try:
                cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'printenv', var]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                      cwd='/Users/chris/dev/livekit-postop')
                if result.returncode == 0 and result.stdout.strip():
                    found_vars[f'docker_{var}'] = result.stdout.strip()
            except:
                pass
        
        self.log_test(
            'sip_phone_number_config',
            'FOUND_VARS' if found_vars else 'NO_PHONE_VARS_FOUND',
            {
                'phone_related_vars': found_vars,
                'note': 'Phone number is typically configured in LiveKit dashboard, not env vars'
            }
        )
        
        return len(found_vars) > 0
    
    def test_direct_agent_communication(self):
        """Test if we can communicate with the Docker agent directly"""
        try:
            # Try to connect to the agent's health check port (if available)
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'python', '-c', '''
import os
import sys
sys.path.append(".")

try:
    from discharge.config import LIVEKIT_AGENT_NAME, LIVEKIT_URL
    print(f"AGENT_NAME:{LIVEKIT_AGENT_NAME}")
    print(f"LIVEKIT_URL:{LIVEKIT_URL}")
    print("CONFIG_OK:True")
except Exception as e:
    print(f"CONFIG_ERROR:{str(e)}")
''']
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                output = result.stdout.strip()
                config_info = {}
                
                for line in output.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        config_info[key] = value
                
                config_ok = config_info.get('CONFIG_OK') == 'True'
                
                self.log_test(
                    'docker_agent_config_test',
                    'CONFIG_OK' if config_ok else 'CONFIG_ERROR',
                    config_info
                )
                
                return config_ok
            else:
                self.log_test(
                    'docker_agent_config_test',
                    'EXEC_ERROR',
                    {'error': result.stderr}
                )
                return False
                
        except Exception as e:
            self.log_test(
                'docker_agent_config_test',
                'EXCEPTION',
                {'error': str(e)}
            )
            return False
    
    def analyze_call_routing_hypothesis(self):
        """Analyze the call routing based on test results"""
        
        # Get test results
        tests = self.results['tests']
        
        # Check if agent is registered
        registration_test = tests.get('docker_agent_registration', {})
        is_registered = registration_test.get('result') == 'REGISTERED'
        
        # Check if names are consistent
        name_test = tests.get('agent_name_consistency', {})
        names_consistent = name_test.get('result') == 'CONSISTENT'
        
        # Check if config is working
        config_test = tests.get('docker_agent_config_test', {})
        config_ok = config_test.get('result') == 'CONFIG_OK'
        
        # Analyze the situation
        if is_registered and names_consistent and config_ok:
            hypothesis = "LIKELY_SIP_DISPATCH_ISSUE"
            explanation = ("Docker agent is properly registered with correct name and config. "
                          "Issue is likely in LiveKit SIP dispatch rules not routing calls to this agent.")
            
            recommendations = [
                "Check LiveKit dashboard SIP dispatch rules",
                "Verify dispatch rule agent name matches LIVEKIT_AGENT_NAME",
                "Check if dispatch rule is active and properly configured",
                "Test with a simple room creation to verify agent can handle calls"
            ]
            
        elif is_registered and not names_consistent:
            hypothesis = "AGENT_NAME_MISMATCH"
            explanation = ("Docker agent is registered but with wrong name. "
                          "SIP dispatch rules probably reference a different agent name.")
            
            recommendations = [
                "Fix agent name consistency between local and Docker environments",
                "Update docker-compose.yml LIVEKIT_AGENT_NAME to match dispatch rules",
                "Restart Docker agent after fixing name"
            ]
            
        elif not is_registered:
            hypothesis = "REGISTRATION_FAILURE"
            explanation = "Docker agent is not successfully registering with LiveKit."
            
            recommendations = [
                "Check LiveKit API credentials in Docker environment",
                "Verify network connectivity from Docker to LiveKit",
                "Check Docker agent logs for registration errors"
            ]
            
        else:
            hypothesis = "CONFIGURATION_ISSUE"
            explanation = "Docker agent has configuration problems preventing proper operation."
            
            recommendations = [
                "Check all environment variables in Docker",
                "Verify Python imports and dependencies",
                "Review Docker agent startup logs for errors"
            ]
        
        self.log_test(
            'call_routing_analysis',
            hypothesis,
            {
                'explanation': explanation,
                'recommendations': recommendations,
                'test_summary': {
                    'is_registered': is_registered,
                    'names_consistent': names_consistent,
                    'config_ok': config_ok
                }
            }
        )
        
        return hypothesis, explanation, recommendations
    
    def run_all_tests(self):
        """Run all routing tests"""
        print("🔬 Inbound Call Routing Diagnostics")
        print("=" * 50)
        print(f"Testing agent: {self.results['agent_name']}")
        print()
        
        # Run tests
        self.check_docker_agent_registration()
        self.check_agent_name_consistency()
        self.check_sip_phone_number_availability()
        self.test_direct_agent_communication()
        
        # Analyze results
        hypothesis, explanation, recommendations = self.analyze_call_routing_hypothesis()
        
        print("=" * 50)
        print("🧪 SCIENTIFIC ANALYSIS")
        print("=" * 50)
        print(f"Hypothesis: {hypothesis}")
        print(f"\nExplanation: {explanation}")
        print(f"\nRecommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save test results to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/Users/chris/dev/livekit-postop/call_routing_test_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

def main():
    """Main function"""
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        tester = InboundCallRoutingTest()
        results = tester.run_all_tests()
        tester.save_results()
        
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()