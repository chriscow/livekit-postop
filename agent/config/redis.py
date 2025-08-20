"""
Redis configuration for the PostOp AI scheduling system
"""
import os
from typing import Optional
import redis


def get_redis_config() -> dict:
    """Get Redis configuration from environment variables"""
    return {
        'host': os.getenv('REDIS_HOST', 'localhost'),
        'port': int(os.getenv('REDIS_PORT', '6379')),
        'db': int(os.getenv('REDIS_DB', '0')),
        'password': os.getenv('REDIS_PASSWORD'),
        'socket_timeout': int(os.getenv('REDIS_SOCKET_TIMEOUT', '5')),
        'socket_connect_timeout': int(os.getenv('REDIS_CONNECT_TIMEOUT', '5')),
        'decode_responses': True
    }


def create_redis_connection() -> redis.Redis:
    """Create a Redis connection with proper configuration"""
    config = get_redis_config()
    
    # Remove None values
    config = {k: v for k, v in config.items() if v is not None}
    
    return redis.Redis(**config)


def test_redis_connection() -> bool:
    """Test Redis connection and return True if successful"""
    try:
        r = create_redis_connection()
        r.ping()
        return True
    except Exception as e:
        print(f"Redis connection failed: {e}")
        return False


# Redis URL for RQ (used by RQ workers)
def get_redis_url() -> str:
    """Get Redis URL for RQ workers"""
    config = get_redis_config()
    
    if config.get('password'):
        return f"redis://:{config['password']}@{config['host']}:{config['port']}/{config['db']}"
    else:
        return f"redis://{config['host']}:{config['port']}/{config['db']}"