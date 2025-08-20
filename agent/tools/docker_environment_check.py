#!/usr/bin/env python3
"""
Docker Environment Check Tool

This tool provides comprehensive comparison between local and Docker environments
to identify configuration differences that might cause agent issues.

Scientific approach:
1. Compare environment variables between local and Docker
2. Test package versions and dependencies
3. Check Python path and module imports
4. Verify file system access and permissions
5. Analyze resource constraints and limits
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, List, Tuple
try:
    import pkg_resources
except ImportError:
    pkg_resources = None

# Add current directory to Python path for imports
sys.path.append('/Users/chris/dev/livekit-postop')

class DockerEnvironmentCheck:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'comparisons': {},
            'summary': {
                'total_checks': 0,
                'matches': 0,
                'differences': 0,
                'errors': 0
            }
        }
        
    def log_comparison(self, check_name: str, local_value: Any, docker_value: Any, 
                      error: str = None, details: Dict[str, Any] = None):
        """Log comparison results"""
        if error:
            status = 'ERROR'
            matches = False
            self.results['summary']['errors'] += 1
        elif local_value == docker_value:
            status = 'MATCH'
            matches = True
            self.results['summary']['matches'] += 1
        else:
            status = 'DIFFERENT'
            matches = False
            self.results['summary']['differences'] += 1
        
        self.results['comparisons'][check_name] = {
            'status': status,
            'matches': matches,
            'local_value': local_value,
            'docker_value': docker_value,
            'error': error,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        
        self.results['summary']['total_checks'] += 1
        
        if error:
            print(f"💥 {check_name}: ERROR")
            print(f"   {error}")
        elif matches:
            print(f"✅ {check_name}: MATCH")
        else:
            print(f"❌ {check_name}: DIFFERENT")
            print(f"   Local: {local_value}")
            print(f"   Docker: {docker_value}")
    
    def get_local_environment_vars(self) -> Dict[str, str]:
        """Get local environment variables"""
        from dotenv import load_dotenv
        load_dotenv()
        
        # Get all environment variables
        return dict(os.environ)
    
    def get_docker_environment_vars(self) -> Dict[str, str]:
        """Get Docker environment variables"""
        try:
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'env']
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                env_vars = {}
                for line in result.stdout.split('\n'):
                    if '=' in line and not line.startswith('_'):  # Skip shell vars
                        key, value = line.split('=', 1)
                        env_vars[key] = value
                return env_vars
            else:
                raise Exception(f"Docker env command failed: {result.stderr}")
                
        except Exception as e:
            raise Exception(f"Failed to get Docker environment: {str(e)}")
    
    def compare_environment_variables(self):
        """Compare environment variables between local and Docker"""
        print("🌍 Comparing Environment Variables...")
        
        try:
            local_env = self.get_local_environment_vars()
            docker_env = self.get_docker_environment_vars()
            
            # Key environment variables to check
            key_vars = [
                'LIVEKIT_AGENT_NAME',
                'LIVEKIT_API_KEY',
                'LIVEKIT_API_SECRET', 
                'LIVEKIT_URL',
                'REDIS_HOST',
                'REDIS_PORT',
                'REDIS_URL',
                'DEEPGRAM_API_KEY',
                'OPENAI_API_KEY',
                'ELEVEN_API_KEY',
                'SIP_OUTBOUND_TRUNK_ID',
                'PYTHONPATH'
            ]
            
            for var in key_vars:
                local_val = local_env.get(var, 'NOT_SET')
                docker_val = docker_env.get(var, 'NOT_SET')
                
                # Mask sensitive values for display
                if any(sensitive in var for sensitive in ['KEY', 'SECRET', 'TOKEN']):
                    local_display = '***MASKED***' if local_val != 'NOT_SET' else 'NOT_SET'
                    docker_display = '***MASKED***' if docker_val != 'NOT_SET' else 'NOT_SET'
                else:
                    local_display = local_val
                    docker_display = docker_val
                
                self.log_comparison(
                    f'env_var_{var}',
                    local_display,
                    docker_display,
                    details={
                        'actual_match': local_val == docker_val,
                        'variable_name': var
                    }
                )
                
        except Exception as e:
            self.log_comparison(
                'environment_variables',
                None,
                None,
                error=str(e)
            )
    
    def get_local_python_info(self) -> Dict[str, Any]:
        """Get local Python environment info"""
        python_info = {
            'version': sys.version,
            'executable': sys.executable,
            'path': sys.path,
            'platform': sys.platform,
            'packages': {}
        }
        
        # Get key package versions
        key_packages = [
            'livekit-agents',
            'livekit-api', 
            'redis',
            'openai',
            'deepgram-sdk',
            'elevenlabs'
        ]
        
        for package in key_packages:
            try:
                if pkg_resources:
                    version = pkg_resources.get_distribution(package).version
                    python_info['packages'][package] = version
                else:
                    python_info['packages'][package] = 'PKG_RESOURCES_UNAVAILABLE'
            except (pkg_resources.DistributionNotFound if pkg_resources else AttributeError, Exception):
                python_info['packages'][package] = 'NOT_FOUND'
                
        return python_info
    
    def get_docker_python_info(self) -> Dict[str, Any]:
        """Get Docker Python environment info"""
        try:
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'python', '-c', '''
import sys
import json
import pkg_resources

info = {
    "version": sys.version,
    "executable": sys.executable,
    "path": sys.path,
    "platform": sys.platform,
    "packages": {}
}

key_packages = [
    "livekit-agents",
    "livekit-api", 
    "redis",
    "openai",
    "deepgram-sdk",
    "elevenlabs"
]

for package in key_packages:
    try:
        version = pkg_resources.get_distribution(package).version
        info["packages"][package] = version
    except pkg_resources.DistributionNotFound:
        info["packages"][package] = "NOT_FOUND"

print(json.dumps(info))
''']
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                return json.loads(result.stdout.strip())
            else:
                raise Exception(f"Docker python command failed: {result.stderr}")
                
        except Exception as e:
            raise Exception(f"Failed to get Docker Python info: {str(e)}")
    
    def compare_python_environments(self):
        """Compare Python environments between local and Docker"""
        print("🐍 Comparing Python Environments...")
        
        try:
            local_python = self.get_local_python_info()
            docker_python = self.get_docker_python_info()
            
            # Compare Python versions
            self.log_comparison(
                'python_version',
                local_python['version'].split()[0],  # Just version number
                docker_python['version'].split()[0],
                details={
                    'local_full': local_python['version'],
                    'docker_full': docker_python['version']
                }
            )
            
            # Compare Python executable paths
            self.log_comparison(
                'python_executable',
                local_python['executable'],
                docker_python['executable']
            )
            
            # Compare platforms
            self.log_comparison(
                'python_platform',
                local_python['platform'],
                docker_python['platform']
            )
            
            # Compare package versions
            for package, local_version in local_python['packages'].items():
                docker_version = docker_python['packages'].get(package, 'NOT_FOUND')
                
                self.log_comparison(
                    f'package_{package.replace("-", "_")}',
                    local_version,
                    docker_version,
                    details={'package_name': package}
                )
                
            # Compare Python paths (just count and key differences)
            local_path_count = len(local_python['path'])
            docker_path_count = len(docker_python['path'])
            
            self.log_comparison(
                'python_path_count',
                local_path_count,
                docker_path_count,
                details={
                    'local_path': local_python['path'][:5],  # First 5 entries
                    'docker_path': docker_python['path'][:5]
                }
            )
            
        except Exception as e:
            self.log_comparison(
                'python_environments',
                None,
                None,
                error=str(e)
            )
    
    def get_local_import_test(self) -> Dict[str, Any]:
        """Test key imports locally"""
        import_results = {}
        
        key_imports = [
            'livekit.agents',
            'livekit.api',
            'discharge.agents',
            'discharge.config',
            'scheduling.scheduler',
            'shared.memory',
            'redis',
            'openai',
            'deepgram'
        ]
        
        for module in key_imports:
            try:
                __import__(module)
                import_results[module] = 'SUCCESS'
            except ImportError as e:
                import_results[module] = f'IMPORT_ERROR: {str(e)}'
            except Exception as e:
                import_results[module] = f'ERROR: {str(e)}'
        
        return import_results
    
    def get_docker_import_test(self) -> Dict[str, Any]:
        """Test key imports in Docker"""
        try:
            cmd = ['docker-compose', 'exec', '-T', 'postop-agent', 'python', '-c', '''
import json
import sys
sys.path.append(".")

import_results = {}
key_imports = [
    "livekit.agents",
    "livekit.api", 
    "discharge.agents",
    "discharge.config",
    "scheduling.scheduler",
    "shared.memory",
    "redis",
    "openai",
    "deepgram"
]

for module in key_imports:
    try:
        __import__(module)
        import_results[module] = "SUCCESS"
    except ImportError as e:
        import_results[module] = f"IMPORT_ERROR: {str(e)}"
    except Exception as e:
        import_results[module] = f"ERROR: {str(e)}"

print(json.dumps(import_results))
''']
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd='/Users/chris/dev/livekit-postop')
            
            if result.returncode == 0:
                return json.loads(result.stdout.strip())
            else:
                raise Exception(f"Docker import test failed: {result.stderr}")
                
        except Exception as e:
            raise Exception(f"Failed to test Docker imports: {str(e)}")
    
    def compare_import_capabilities(self):
        """Compare import capabilities between local and Docker"""
        print("📦 Comparing Import Capabilities...")
        
        try:
            local_imports = self.get_local_import_test()
            docker_imports = self.get_docker_import_test()
            
            for module, local_result in local_imports.items():
                docker_result = docker_imports.get(module, 'NOT_TESTED')
                
                self.log_comparison(
                    f'import_{module.replace(".", "_")}',
                    local_result,
                    docker_result,
                    details={'module_name': module}
                )
                
        except Exception as e:
            self.log_comparison(
                'import_capabilities',
                None,
                None,
                error=str(e)
            )
    
    def get_docker_resources(self) -> Dict[str, Any]:
        """Get Docker container resource information"""
        try:
            # Get container stats
            cmd = ['docker', 'stats', '--no-stream', '--format', 
                   'table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                stats = []
                
                for line in lines[1:]:  # Skip header
                    parts = line.split('\t')
                    if len(parts) >= 6:
                        stats.append({
                            'container': parts[0],
                            'cpu_percent': parts[1],
                            'mem_usage': parts[2],
                            'mem_percent': parts[3],
                            'net_io': parts[4],
                            'block_io': parts[5]
                        })
                
                return {'stats': stats, 'status': 'SUCCESS'}
            else:
                return {'status': 'ERROR', 'error': result.stderr}
                
        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}
    
    def compare_resource_constraints(self):
        """Compare resource constraints"""
        print("💾 Checking Resource Constraints...")
        
        try:
            docker_resources = self.get_docker_resources()
            
            if docker_resources['status'] == 'SUCCESS':
                postop_agent_stats = None
                for stat in docker_resources['stats']:
                    if 'postop-agent' in stat['container']:
                        postop_agent_stats = stat
                        break
                
                if postop_agent_stats:
                    self.log_comparison(
                        'docker_agent_resources',
                        'N/A (Local)',
                        f"CPU: {postop_agent_stats['cpu_percent']}, MEM: {postop_agent_stats['mem_usage']}",
                        details={
                            'docker_stats': postop_agent_stats,
                            'all_containers': docker_resources['stats']
                        }
                    )
                else:
                    self.log_comparison(
                        'docker_agent_resources',
                        'N/A (Local)',
                        'Agent container not found',
                        error='PostOp agent container not found in Docker stats'
                    )
            else:
                self.log_comparison(
                    'docker_agent_resources',
                    'N/A (Local)',
                    'Error getting stats',
                    error=docker_resources['error']
                )
                
        except Exception as e:
            self.log_comparison(
                'resource_constraints',
                None,
                None,
                error=str(e)
            )
    
    def run_all_comparisons(self):
        """Run all comparison tests"""
        print("🔬 Docker Environment Comparison")
        print("=" * 50)
        print("Comparing local vs Docker environments...")
        print()
        
        # Run all comparisons
        self.compare_environment_variables()
        self.compare_python_environments()
        self.compare_import_capabilities()
        self.compare_resource_constraints()
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 COMPARISON SUMMARY")
        print("=" * 50)
        
        summary = self.results['summary']
        print(f"Total Checks: {summary['total_checks']}")
        print(f"✅ Matches: {summary['matches']}")
        print(f"❌ Differences: {summary['differences']}")
        print(f"💥 Errors: {summary['errors']}")
        
        # Key findings
        print(f"\n🔍 KEY DIFFERENCES:")
        
        differences = [(name, comp) for name, comp in self.results['comparisons'].items() 
                      if comp['status'] == 'DIFFERENT']
        
        if differences:
            print("❌ CONFIGURATION DIFFERENCES:")
            for name, comp in differences[:10]:  # Show first 10
                print(f"   • {name}: Local='{comp['local_value']}' vs Docker='{comp['docker_value']}'")
        
        errors = [(name, comp) for name, comp in self.results['comparisons'].items() 
                 if comp['status'] == 'ERROR']
        
        if errors:
            print("💥 ERRORS:")
            for name, comp in errors:
                print(f"   • {name}: {comp['error']}")
        
        if not differences and not errors:
            print("✅ No significant differences found!")
        
        return self.results
    
    def save_results(self, filename: str = None):
        """Save comparison results to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/Users/chris/dev/livekit-postop/env_comparison_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

def main():
    """Main function"""
    checker = DockerEnvironmentCheck()
    
    try:
        results = checker.run_all_comparisons()
        checker.save_results()
        
        # Exit with error code if there are errors
        if results['summary']['errors'] > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Comparison interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()