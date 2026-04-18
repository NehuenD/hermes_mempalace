"""MemPalace client wrapper.

Thin wrapper around MemPalace Python API for use by the Hermes memory provider.
Handles import safety and provides utility functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MEMPALACE_IMPORT_ERROR = """
MemPalace not installed. Install with:
    pip install mempalace

Or for development:
    git clone https://github.com/milla-jovovich/mempalace.git
    cd mempalace && pip install -e .
"""


def is_available() -> bool:
    """Check if mempalace is installed and importable."""
    try:
        import mempalace
        import chromadb
        import yaml

        return True
    except ImportError:
        return False


def get_import_error() -> str:
    return MEMPALACE_IMPORT_ERROR


class MempalaceClient:
    """Thin wrapper around MemPalace API."""

    def __init__(
        self,
        palace_path: str = "~/.mempalace/",
        collection_name: str = "mempalace_drawers",
    ):
        self.palace_path = Path(palace_path).expanduser()
        self.collection_name = collection_name
        self._chroma_client = None
        self._collection = None
        self._kg = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize ChromaDB client and knowledge graph."""
        if self._initialized:
            return True

        try:
            import chromadb
            from mempalace.knowledge_graph import KnowledgeGraph

            palace_dir = self.palace_path / "palace"
            palace_dir.mkdir(parents=True, exist_ok=True)

            self._chroma_client = chromadb.PersistentClient(path=str(palace_dir))
            self._collection = self._chroma_client.get_or_create_collection(
                self.collection_name
            )
            self._kg = KnowledgeGraph()
            self._initialized = True
            return True
        except ImportError as e:
            logger.error("Missing dependency: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to initialize MemPalace: %s", e)
            return False

    @property
    def collection(self):
        """Get the ChromaDB collection."""
        if not self._initialized:
            self.initialize()
        return self._collection

    @property
    def knowledge_graph(self):
        """Get the KnowledgeGraph instance."""
        if not self._initialized:
            self.initialize()
        return self._kg

    def search(
        self,
        query: str,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Semantic search over stored memories."""
        if not self.collection:
            return []

        try:
            from mempalace.searcher import search_memories

            results = search_memories(
                query,
                palace_path=str(self.palace_path),
                n_results=n_results,
            )
            filtered = []
            for r in results:
                meta = r.get("metadata", {})
                if wing and meta.get("wing") != wing:
                    continue
                if room and meta.get("room") != room:
                    continue
                filtered.append(r)
            return filtered
        except ImportError:
            return []

    def add_drawer(
        self,
        content: str,
        wing: str = "wing_general",
        room: str = "general",
        closet: str = "hall_general",
    ) -> str:
        """Add content to a wing/room/closet."""
        import uuid

        if not self.collection:
            raise RuntimeError("Palace not initialized")

        doc_id = str(uuid.uuid4())
        self.collection.add(
            documents=[content],
            metadatas=[{"wing": wing, "room": room, "closet": closet}],
            ids=[doc_id],
        )
        return doc_id

    def delete_drawer(self, drawer_id: str) -> bool:
        """Delete a drawer by ID."""
        if not self.collection:
            return False
        try:
            self.collection.delete(ids=[drawer_id])
            return True
        except Exception:
            return False

    def get_taxonomy(self) -> Dict[str, Dict[str, int]]:
        """Get full wing → room → count taxonomy."""
        if not self.collection:
            return {}

        # Try to load from cache file first
        cache_file = (
            self.palace_path / "taxonomy_cache.json" if self.palace_path else None
        )
        if cache_file and cache_file.exists():
            import json as json_lib

            try:
                return json_lib.loads(cache_file.read_text())
            except Exception:
                pass

        # Full scan fallback
        taxonomy = {}
        try:
            all_data = self.collection.get(include=["metadatas"])
            for m in all_data.get("metadatas", []) or []:
                w = m.get("wing", "unknown")
                r = m.get("room", "unknown")
                if w not in taxonomy:
                    taxonomy[w] = {}
                taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
        except Exception:
            pass
        return taxonomy

    def get_wings(self) -> Dict[str, int]:
        """Get all wings with drawer counts."""
        if not self.collection:
            return {}
        wings = {}
        try:
            all_data = self.collection.get(include=["metadatas"])
            for m in all_data.get("metadatas", []):
                w = m.get("wing", "unknown")
                wings[w] = wings.get(w, 0) + 1
        except Exception:
            pass
        return wings

    def get_rooms(self, wing: str) -> Dict[str, int]:
        """Get rooms within a wing."""
        if not self.collection:
            return {}
        rooms = {}
        try:
            results = self.collection.get(where={"wing": wing}, include=["metadatas"])
            for m in results.get("metadatas", []):
                r = m.get("room", "unknown")
                rooms[r] = rooms.get(r, 0) + 1
        except Exception:
            pass
        return rooms

    def kg_query(
        self, entity: str, as_of: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query knowledge graph for entity relationships."""
        if not self.knowledge_graph:
            return []
        return self.knowledge_graph.query_entity(entity, as_of=as_of)

    def kg_add(
        self, subject: str, predicate: str, obj: str, valid_from: Optional[str] = None
    ) -> bool:
        """Add a fact triple to the knowledge graph."""
        if not self.knowledge_graph:
            return False
        try:
            self.knowledge_graph.add_triple(
                subject, predicate, obj, valid_from=valid_from
            )
            return True
        except Exception:
            return False

    def kg_invalidate(
        self, subject: str, predicate: str, obj: str, ended: Optional[str] = None
    ) -> bool:
        """Invalidate a fact triple."""
        if not self.knowledge_graph:
            return False
        try:
            self.knowledge_graph.invalidate(subject, predicate, obj, ended=ended)
            return True
        except Exception:
            return False

    def kg_timeline(self, entity: str) -> List[Dict[str, Any]]:
        """Get chronological timeline for an entity."""
        if not self.knowledge_graph:
            return []
        return self.knowledge_graph.timeline(entity)

    def kg_stats(self) -> Dict[str, Any]:
        """Get knowledge graph statistics."""
        if not self.knowledge_graph:
            return {}
        return self.knowledge_graph.get_stats()

    def check_duplicate(self, content: str, wing: Optional[str] = None) -> bool:
        """Check if content already exists."""
        if not self.collection:
            return False
        try:
            results = self.collection.get(
                where={"wing": wing} if wing else None, include=["documents"]
            )
            for doc in results.get("documents", []):
                if content.lower() in doc.lower():
                    return True
        except Exception:
            pass
        return False
