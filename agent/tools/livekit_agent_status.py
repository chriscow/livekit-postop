#!/usr/bin/env python3
"""
LiveKit Agent Status Tool

This tool provides comprehensive status checking for LiveKit agents
to identify registration issues and SIP dispatch configuration problems.

Scientific approach:
1. Query LiveKit API for registered agents
2. Check SIP dispatch rule configuration  
3. Compare local vs Docker agent registration
4. Analyze agent connection patterns
5. Test authentication and permissions
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import livekit.api as lk_api

# Add current directory to Python path for imports  
sys.path.append('/Users/chris/dev/livekit-postop')

class LiveKitAgentStatus:
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
        
        # Initialize LiveKit API client
        self.lk_url = os.getenv('LIVEKIT_URL')
        self.lk_api_key = os.getenv('LIVEKIT_API_KEY')
        self.lk_api_secret = os.getenv('LIVEKIT_API_SECRET')
        self.agent_name = os.getenv('LIVEKIT_AGENT_NAME')
        
        if not all([self.lk_url, self.lk_api_key, self.lk_api_secret]):
            raise ValueError("Missing required LiveKit environment variables")
        
        self.lk_api = lk_api.LiveKitAPI(
            url=self.lk_url,
            api_key=self.lk_api_key,
            api_secret=self.lk_api_secret
        )
        
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
    
    async def test_livekit_api_connectivity(self):
        """Test basic LiveKit API connectivity"""
        try:
            # Simple API call to test connectivity
            rooms = await self.lk_api.room.list_rooms(lk_api.ListRoomsRequest())
            
            self.log_test(
                'livekit_api_connectivity',
                True,
                {
                    'message': f"Successfully connected to LiveKit API at {self.lk_url}",
                    'livekit_url': self.lk_url,
                    'room_count': len(rooms.rooms)
                }
            )
            
        except Exception as e:
            self.log_test(
                'livekit_api_connectivity',
                False,
                {
                    'message': f"Failed to connect to LiveKit API: {str(e)}",
                    'error': str(e),
                    'livekit_url': self.lk_url
                }
            )
    
    def test_agent_registration_status(self):
        """Test agent registration status"""
        try:
            # List all agents
            agents_response = self.lk_api.agent.list_agents(lk_api.ListAgentsRequest())
            
            registered_agents = []
            our_agents = []
            
            for agent in agents_response.agents:
                agent_info = {
                    'name': agent.name,
                    'version': agent.version,
                    'state': agent.state,
                    'created_at': agent.created_at,
                    'metadata': agent.metadata
                }
                registered_agents.append(agent_info)
                
                # Check if this is our agent
                if agent.name == self.agent_name:
                    our_agents.append(agent_info)
            
            our_agent_registered = len(our_agents) > 0
            
            self.log_test(
                'agent_registration_status',
                our_agent_registered,
                {
                    'message': f"Found {len(our_agents)} instances of '{self.agent_name}'" if our_agent_registered 
                             else f"Agent '{self.agent_name}' not found in registered agents",
                    'expected_agent_name': self.agent_name,
                    'our_agents': our_agents,
                    'total_registered_agents': len(registered_agents),
                    'all_registered_agents': registered_agents
                }
            )
            
        except Exception as e:
            self.log_test(
                'agent_registration_status',
                False,
                {
                    'message': f"Failed to list agents: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_sip_configuration(self):
        """Test SIP configuration and dispatch rules"""
        try:
            # List SIP dispatch rules
            sip_response = self.lk_api.sip.list_sip_dispatch_rule(lk_api.ListSIPDispatchRuleRequest())
            
            dispatch_rules = []
            matching_rules = []
            
            for rule in sip_response.items:
                rule_info = {
                    'sip_dispatch_rule_id': rule.sip_dispatch_rule_id,
                    'rule': {
                        'dispatch_rule_direct': rule.rule.dispatch_rule_direct.room_name if rule.rule.dispatch_rule_direct else None,
                        'dispatch_rule_individual': rule.rule.dispatch_rule_individual.room_prefix if rule.rule.dispatch_rule_individual else None
                    },
                    'trunk_ids': list(rule.trunk_ids),
                    'hide_phone_number': rule.hide_phone_number,
                    'name': rule.name,
                    'metadata': rule.metadata
                }
                dispatch_rules.append(rule_info)
                
                # Check if this rule might route to our agent
                # Look for agent name in metadata or room patterns
                rule_text = str(rule_info).lower()
                if self.agent_name and self.agent_name.lower() in rule_text:
                    matching_rules.append(rule_info)
            
            has_matching_rules = len(matching_rules) > 0
            
            self.log_test(
                'sip_dispatch_configuration',
                has_matching_rules,
                {
                    'message': f"Found {len(matching_rules)} dispatch rules that may route to '{self.agent_name}'" if has_matching_rules
                             else f"No dispatch rules found for agent '{self.agent_name}'",
                    'matching_rules': matching_rules,
                    'total_dispatch_rules': len(dispatch_rules),
                    'all_dispatch_rules': dispatch_rules
                },
                warning=not has_matching_rules
            )
            
        except Exception as e:
            self.log_test(
                'sip_dispatch_configuration',
                False,
                {
                    'message': f"Failed to list SIP dispatch rules: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_sip_trunks(self):
        """Test SIP trunk configuration"""
        try:
            # List SIP trunks
            trunks_response = self.lk_api.sip.list_sip_trunk(lk_api.ListSIPTrunkRequest())
            
            trunks = []
            for trunk in trunks_response.items:
                trunk_info = {
                    'sip_trunk_id': trunk.sip_trunk_id,
                    'kind': trunk.kind,
                    'name': trunk.name,
                    'metadata': trunk.metadata,
                    'outbound_address': getattr(trunk, 'outbound_address', None),
                    'outbound_username': getattr(trunk, 'outbound_username', None)
                }
                trunks.append(trunk_info)
            
            has_trunks = len(trunks) > 0
            
            self.log_test(
                'sip_trunk_configuration',
                has_trunks,
                {
                    'message': f"Found {len(trunks)} SIP trunks configured" if has_trunks else "No SIP trunks found",
                    'trunks': trunks
                },
                warning=not has_trunks
            )
            
        except Exception as e:
            self.log_test(
                'sip_trunk_configuration',
                False,
                {
                    'message': f"Failed to list SIP trunks: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_recent_sip_calls(self):
        """Test recent SIP call activity"""
        try:
            # List recent rooms to see call activity
            rooms_response = self.lk_api.room.list_rooms(lk_api.ListRoomsRequest())
            
            sip_rooms = []
            recent_rooms = []
            
            for room in rooms_response.rooms:
                room_info = {
                    'name': room.name,
                    'sid': room.sid,
                    'creation_time': room.creation_time,
                    'metadata': room.metadata,
                    'num_participants': room.num_participants,
                    'num_publishers': room.num_publishers
                }
                recent_rooms.append(room_info)
                
                # Look for SIP-related rooms
                if any(keyword in room.name.lower() for keyword in ['sip', 'call', 'phone']):
                    sip_rooms.append(room_info)
            
            self.log_test(
                'recent_sip_call_activity',
                True,  # This is informational
                {
                    'message': f"Found {len(sip_rooms)} SIP-related rooms out of {len(recent_rooms)} total rooms",
                    'sip_rooms': sip_rooms,
                    'total_rooms': len(recent_rooms),
                    'recent_rooms': recent_rooms[:5]  # Show first 5 rooms
                }
            )
            
        except Exception as e:
            self.log_test(
                'recent_sip_call_activity',
                False,
                {
                    'message': f"Failed to list rooms: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_agent_worker_status(self):
        """Test agent worker status and capabilities"""
        try:
            # List agent workers
            workers_response = self.lk_api.agent.list_agent_dispatch(lk_api.ListAgentDispatchRequest())
            
            agent_workers = []
            our_workers = []
            
            for dispatch in workers_response.agent_dispatches:
                worker_info = {
                    'id': dispatch.id,
                    'agent_name': dispatch.agent_name,
                    'room_name': dispatch.room_name,
                    'metadata': dispatch.metadata
                }
                agent_workers.append(worker_info)
                
                if dispatch.agent_name == self.agent_name:
                    our_workers.append(worker_info)
            
            has_active_workers = len(our_workers) > 0
            
            self.log_test(
                'agent_worker_status',
                True,  # Informational test
                {
                    'message': f"Found {len(our_workers)} active dispatches for '{self.agent_name}'" if has_active_workers
                             else f"No active dispatches for '{self.agent_name}'",
                    'our_workers': our_workers,
                    'total_agent_dispatches': len(agent_workers),
                    'all_agent_dispatches': agent_workers
                }
            )
            
        except Exception as e:
            self.log_test(
                'agent_worker_status',
                False,
                {
                    'message': f"Failed to list agent dispatches: {str(e)}",
                    'error': str(e)
                }
            )
    
    def test_authentication_permissions(self):
        """Test authentication and permissions"""
        try:
            # Test various API calls to check permissions
            permission_tests = []
            
            # Test room list permission
            try:
                rooms = self.lk_api.room.list_rooms(lk_api.ListRoomsRequest())
                permission_tests.append(('list_rooms', True, len(rooms.rooms)))
            except Exception as e:
                permission_tests.append(('list_rooms', False, str(e)))
            
            # Test agent list permission
            try:
                agents = self.lk_api.agent.list_agents(lk_api.ListAgentsRequest())
                permission_tests.append(('list_agents', True, len(agents.agents)))
            except Exception as e:
                permission_tests.append(('list_agents', False, str(e)))
            
            # Test SIP permissions
            try:
                sip_rules = self.lk_api.sip.list_sip_dispatch_rule(lk_api.ListSIPDispatchRuleRequest())
                permission_tests.append(('list_sip_dispatch_rules', True, len(sip_rules.items)))
            except Exception as e:
                permission_tests.append(('list_sip_dispatch_rules', False, str(e)))
            
            all_permissions_ok = all(test[1] for test in permission_tests)
            
            self.log_test(
                'authentication_permissions',
                all_permissions_ok,
                {
                    'message': f"API permissions: {len([t for t in permission_tests if t[1]])}/{len(permission_tests)} working",
                    'permission_tests': permission_tests
                }
            )
            
        except Exception as e:
            self.log_test(
                'authentication_permissions',
                False,
                {
                    'message': f"Failed to test permissions: {str(e)}",
                    'error': str(e)
                }
            )
    
    def run_all_diagnostics(self):
        """Run all diagnostic tests"""
        print("🔬 LiveKit Agent Status Diagnostics")
        print("=" * 50)
        print(f"Testing agent: {self.agent_name}")
        print(f"LiveKit URL: {self.lk_url}")
        print()
        
        # Run all tests
        self.test_livekit_api_connectivity()
        self.test_authentication_permissions()
        self.test_agent_registration_status()
        self.test_sip_configuration()
        self.test_sip_trunks()
        self.test_recent_sip_calls()
        self.test_agent_worker_status()
        
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
            print("🟡 POTENTIAL ISSUES:")
            for name, test in warning_tests:
                print(f"   • {name}: {test['details'].get('message', 'No details')}")
        
        if not failed_tests and not warning_tests:
            print("✅ All LiveKit diagnostics passed!")
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save diagnostic results to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/Users/chris/dev/livekit-postop/livekit_status_{timestamp}.json"
        
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
        diagnostics = LiveKitAgentStatus()
        results = diagnostics.run_all_diagnostics()
        diagnostics.save_results()
        
        # Exit with error code if there are failures
        if results['summary']['failed'] > 0:
            sys.exit(1)
        
    except ValueError as e:
        print(f"❌ Configuration Error: {str(e)}")
        print("Please ensure LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are set in your environment.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Diagnostics interrupted by user")
        sys.exit(1) 
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()