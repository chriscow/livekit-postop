"""
System Diagnostics Module

Provides runtime diagnostic information about the system and database.
"""

import socket
import shutil
import psutil
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from .database import get_database


class SystemDiagnostics:
    """Collects and provides system diagnostic information"""

    def __init__(self):
        self._cached_info = {}
        self._last_update = None
        self._cache_duration = 60  # seconds

    async def get_info(self, requested_items: Optional[list] = None) -> Dict[str, Any]:
        """
        Get diagnostic information for requested items.

        Args:
            requested_items: List of info types to return. If None, returns basic info.
                           Options: 'hostname', 'ip', 'disk_space', 'memory', 'cpu',
                                   'database_stats', 'uptime', 'load_average'
        """
        # Update cache if needed
        await self._update_cache_if_needed()

        if requested_items is None:
            requested_items = ['hostname', 'ip', 'database_stats']

        result = {}
        for item in requested_items:
            if item in self._cached_info:
                result[item] = self._cached_info[item]

        return result

    async def _update_cache_if_needed(self):
        """Update cache if it's stale or empty"""
        now = datetime.now()
        if (self._last_update is None or
            (now - self._last_update).total_seconds() > self._cache_duration):
            await self._update_cache()
            self._last_update = now

    async def _update_cache(self):
        """Update all diagnostic information in cache"""
        try:
            # System information
            self._cached_info['hostname'] = socket.gethostname()
            self._cached_info['ip'] = self._get_local_ip()
            self._cached_info['disk_space'] = self._get_disk_space()
            self._cached_info['memory'] = self._get_memory_info()
            self._cached_info['cpu'] = self._get_cpu_info()
            self._cached_info['uptime'] = self._get_uptime()
            self._cached_info['load_average'] = self._get_load_average()

            # Database information (async)
            self._cached_info['database_stats'] = await self._get_database_stats()

        except Exception as e:
            # If any individual metric fails, log but continue
            print(f"Warning: Failed to update some diagnostic info: {e}")

    def _get_local_ip(self) -> str:
        """Get the local IP address"""
        try:
            # Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "Unknown"

    def _get_disk_space(self) -> Dict[str, str]:
        """Get disk space information for current directory"""
        try:
            total, used, free = shutil.disk_usage(".")
            return {
                'total': self._format_bytes(total),
                'used': self._format_bytes(used),
                'free': self._format_bytes(free),
                'used_percent': f"{(used / total * 100):.1f}%"
            }
        except Exception:
            return {'error': 'Unable to get disk space'}

    def _get_memory_info(self) -> Dict[str, str]:
        """Get memory usage information"""
        try:
            memory = psutil.virtual_memory()
            return {
                'total': self._format_bytes(memory.total),
                'available': self._format_bytes(memory.available),
                'used': self._format_bytes(memory.used),
                'used_percent': f"{memory.percent:.1f}%"
            }
        except Exception:
            return {'error': 'Unable to get memory info'}

    def _get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU usage information"""
        try:
            return {
                'usage_percent': f"{psutil.cpu_percent(interval=1):.1f}%",
                'count': psutil.cpu_count(),
                'count_logical': psutil.cpu_count(logical=True)
            }
        except Exception:
            return {'error': 'Unable to get CPU info'}

    def _get_uptime(self) -> str:
        """Get system uptime"""
        try:
            import time
            uptime_seconds = time.time() - psutil.boot_time()
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{days}d {hours}h {minutes}m"
        except Exception:
            return "Unknown"

    def _get_load_average(self) -> Dict[str, float]:
        """Get system load average (Unix-like systems only)"""
        try:
            load1, load5, load15 = psutil.getloadavg()
            return {
                '1min': round(load1, 2),
                '5min': round(load5, 2),
                '15min': round(load15, 2)
            }
        except Exception:
            return {'error': 'Load average not available'}

    async def _get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics with timeout protection"""
        try:
            # Add timeout to database connection and queries
            db = await asyncio.wait_for(get_database(), timeout=5.0)

            async with db.pool.acquire() as conn:
                # Get total conversation count with timeout
                total_sessions = await asyncio.wait_for(
                    conn.fetchval("SELECT COUNT(*) FROM sessions"), timeout=3.0
                )

                # Get evaluation session count with timeout
                eval_sessions = await asyncio.wait_for(
                    conn.fetchval(
                        "SELECT COUNT(*) FROM sessions WHERE session_id LIKE 'eval_%' OR is_evaluation = true"
                    ), timeout=3.0
                )

                # Get sessions with conversations with timeout
                sessions_with_messages = await asyncio.wait_for(
                    conn.fetchval("SELECT COUNT(*) FROM sessions WHERE jsonb_array_length(transcript) > 0"),
                    timeout=3.0
                )

                # Get recent session count (last 24 hours) with timeout
                recent_sessions = await asyncio.wait_for(
                    conn.fetchval(
                        """SELECT COUNT(*) FROM sessions
                           WHERE created_at > NOW() - INTERVAL '24 hours'"""
                    ), timeout=3.0
                )

                return {
                    'total_sessions': total_sessions,
                    'evaluation_sessions': eval_sessions,
                    'sessions_with_messages': sessions_with_messages,
                    'recent_sessions_24h': recent_sessions,
                    'organic_sessions': total_sessions - eval_sessions
                }

        except asyncio.TimeoutError:
            return {'error': 'Database query timed out'}
        except Exception as e:
            return {'error': f'Unable to get database stats: {e}'}

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes into human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"


# Global instance
_diagnostics = SystemDiagnostics()


async def get_diagnostic_info(requested_items: Optional[list] = None) -> Dict[str, Any]:
    """
    Get diagnostic information for requested items.

    Args:
        requested_items: List of info types to return. Available options:
                        'hostname', 'ip', 'disk_space', 'memory', 'cpu',
                        'database_stats', 'uptime', 'load_average'

    Returns:
        Dictionary containing requested diagnostic information
    """
    return await _diagnostics.get_info(requested_items)