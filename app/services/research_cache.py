import json
import time
from typing import Optional, Dict, Any
from pathlib import Path

from app.core.config import get_settings


class ResearchCache:
    def __init__(self):
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.settings = get_settings()
    
    def _get_key(self, query: str) -> str:
        import hashlib
        return hashlib.sha256(query.lower().strip().encode()).hexdigest()
    
    def get(self, query: str) -> Optional[Dict[str, Any]]:
        key = self._get_key(query)
        cache_file = self.cache_dir / f"{key}.json"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if time.time() - data['timestamp'] > self.settings.research_cache_ttl:
                cache_file.unlink()
                return None
            return data['results']
        except Exception:
            return None
    
    def set(self, query: str, results: Dict[str, Any]):
        key = self._get_key(query)
        cache_file = self.cache_dir / f"{key}.json"
        try:
            data = {
                'timestamp': time.time(),
                'query': query,
                'results': results
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
    
    def clear_expired(self):
        now = time.time()
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if now - data['timestamp'] > self.settings.research_cache_ttl:
                    cache_file.unlink()
            except Exception:
                try:
                    cache_file.unlink()
                except Exception:
                    pass


research_cache = ResearchCache()
