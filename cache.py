"""
Cache en mémoire avec TTL configurable.
En production sur Render/Railway, le process redémarre parfois —
les données sont alors re-scrapées automatiquement.
Pour une persistance entre redémarrages, remplacez par Redis ou SQLite.
"""

import os
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Durée de cache par défaut : 6 heures (les convocations ne changent pas souvent)
DEFAULT_TTL = int(os.getenv("CACHE_TTL_SECONDS", 6 * 3600))


class ConvocationCache:
    def __init__(self, ttl: int = DEFAULT_TTL):
        self._data: Optional[dict] = None
        self._stored_at: float     = 0.0
        self.ttl                   = ttl

    def get(self, ignore_ttl: bool = False) -> Optional[dict]:
        if self._data is None:
            return None
        age = time.time() - self._stored_at
        if not ignore_ttl and age > self.ttl:
            logger.info(f"Cache expiré ({age:.0f}s > TTL {self.ttl}s)")
            return None
        return self._data

    def set(self, data: dict) -> None:
        self._data      = data
        self._stored_at = time.time()
        logger.info("Cache mis à jour")

    def clear(self) -> None:
        self._data      = None
        self._stored_at = 0.0
