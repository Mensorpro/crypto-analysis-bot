"""Simple cache to reduce API calls"""
import time
from typing import Dict, Optional


class CacheManager:
    def __init__(self, ttl_seconds: int = 60):
        """
        Initialize cache manager
        ttl_seconds: Time to live for cached data (default 60 seconds)
        """
        self.cache: Dict[str, tuple] = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached data if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return data
            else:
                # Expired, remove it
                del self.cache[key]
        return None
    
    def set(self, key: str, data: Dict):
        """Store data in cache with current timestamp"""
        self.cache[key] = (data, time.time())
    
    def clear_expired(self):
        """Remove all expired entries"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if current_time - timestamp >= self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            "total_entries": len(self.cache),
            "ttl_seconds": self.ttl
        }
