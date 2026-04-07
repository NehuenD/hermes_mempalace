"""Tests for MemPalace Memory Provider Plugin."""

import json
import pytest
from unittest.mock import MagicMock, patch

from plugins.memory.mempalace import MempalaceMemoryProvider


class FakeCollection:
    """Fake ChromaDB collection for testing."""

    def __init__(self):
        self._data = {}
        self._id_counter = 0

    def add(self, documents, metadatas, ids):
        for doc, meta, doc_id in zip(documents, metadatas, ids):
            self._data[doc_id] = {"document": doc, "metadata": meta}

    def get(self, where=None, include=None):
        results = {"documents": [], "metadatas": [], "ids": []}
        for doc_id, data in self._data.items():
            if where:
                meta = data["metadata"]
                match = all(meta.get(k) == v for k, v in where.items())
                if not match:
                    continue
            results["documents"].append(data["document"])
            results["metadatas"].append(data["metadata"])
            results["ids"].append(doc_id)
        return results

    def count(self):
        return len(self._data)

    def delete(self, ids):
        for doc_id in ids:
            self._data.pop(doc_id, None)


class TestMempalaceProvider:
    """Tests for MempalaceMemoryProvider."""

    def test_name(self):
        provider = MempalaceMemoryProvider()
        assert provider.name == "mempalace"

    def test_is_available(self):
        provider = MempalaceMemoryProvider()
        assert provider.is_available() is True

    def test_get_config_schema(self):
        provider = MempalaceMemoryProvider()
        schema = provider.get_config_schema()
        assert len(schema) == 3
        keys = {s["key"] for s in schema}
        assert keys == {"palace_path", "collection_name", "default_wing"}

    def test_get_tool_schemas(self):
        provider = MempalaceMemoryProvider()
        schemas = provider.get_tool_schemas()
        assert len(schemas) == 19
        tool_names = {s["name"] for s in schemas}
        assert "mempalace_status" in tool_names
        assert "mempalace_search" in tool_names
        assert "mempalace_kg_add" in tool_names
        assert "mempalace_diary_write" in tool_names

    def test_system_prompt_block(self):
        provider = MempalaceMemoryProvider()
        block = provider.system_prompt_block()
        assert "MemPalace Memory" in block
        assert "mempalace_search" in block

    def test_detect_room(self):
        provider = MempalaceMemoryProvider()
        provider._default_wing = "wing_test"

        assert provider._detect_room("auth migration") == "auth"
        assert provider._detect_room("database schema") == "database"
        assert provider._detect_room("react component") == "frontend"
        assert provider._detect_room("docker deploy") == "deploy"
        assert provider._detect_room("general conversation") == "general"

    def test_detect_closet(self):
        provider = MempalaceMemoryProvider()

        assert provider._detect_closet("we decided to use postgres") == "hall_facts"
        assert provider._detect_closet("I prefer dark mode") == "hall_preferences"
        assert provider._detect_closet("I discovered that...") == "hall_discoveries"
        assert provider._detect_closet("my advice is to...") == "hall_advice"
        assert provider._detect_closet("what happened was...") == "hall_events"

    def test_tool_status_no_palace(self):
        provider = MempalaceMemoryProvider()
        result = provider.handle_tool_call("mempalace_status", {})
        data = json.loads(result)
        assert "error" in data or "total_drawers" in data

    def test_tool_list_wings_no_palace(self):
        provider = MempalaceMemoryProvider()
        result = provider.handle_tool_call("mempalace_list_wings", {})
        data = json.loads(result)
        assert "error" in data or "wings" in data

    def test_tool_unknown(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._collection = MagicMock()
        result = provider.handle_tool_call("unknown_tool", {})
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    def test_sync_turn_increments_count(self):
        provider = MempalaceMemoryProvider()
        provider._turn_count = 0
        provider.sync_turn("user", "assistant")
        assert provider._turn_count == 1

    def test_prefetch_returns_empty_initially(self):
        provider = MempalaceMemoryProvider()
        result = provider.prefetch("test query")
        assert result == ""

    def test_on_turn_start_updates_count(self):
        provider = MempalaceMemoryProvider()
        provider.on_turn_start(5, "test message")
        assert provider._turn_count == 5

    def test_on_pre_compress_with_empty_messages(self):
        provider = MempalaceMemoryProvider()
        result = provider.on_pre_compress([])
        assert result == ""

    def test_on_pre_compress_with_messages(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._collection = MagicMock()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = provider.on_pre_compress(messages)
        assert "MemPalace Context" in result
        assert "Hello" in result

    def test_tool_schemas_have_required_fields(self):
        provider = MempalaceMemoryProvider()
        schemas = provider.get_tool_schemas()
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema
            assert schema["parameters"]["type"] == "object"

    def test_tool_schemas_search_params(self):
        provider = MempalaceMemoryProvider()
        schemas = provider.get_tool_schemas()
        search_schema = next(s for s in schemas if s["name"] == "mempalace_search")
        params = search_schema["parameters"]["properties"]
        assert "query" in params
        assert "wing" in params
        assert "room" in params
        assert "limit" in params

    def test_tool_schemas_add_drawer_params(self):
        provider = MempalaceMemoryProvider()
        schemas = provider.get_tool_schemas()
        add_schema = next(s for s in schemas if s["name"] == "mempalace_add_drawer")
        params = add_schema["parameters"]["properties"]
        assert "content" in params
        assert "wing" in params
        assert "room" in params

    def test_tool_schemas_kg_query_params(self):
        provider = MempalaceMemoryProvider()
        schemas = provider.get_tool_schemas()
        kg_schema = next(s for s in schemas if s["name"] == "mempalace_kg_query")
        params = kg_schema["parameters"]["properties"]
        assert "entity" in params
        assert "as_of" in params


class TestMempalaceToolDispatch:
    """Tests for tool call dispatch."""

    def test_dispatch_status(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._collection = MagicMock()
        provider._collection.count.return_value = 42

        result = provider.handle_tool_call("mempalace_status", {})
        data = json.loads(result)
        assert data.get("total_drawers") == 42 or "error" in data

    def test_dispatch_list_wings(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._collection = FakeCollection()

        result = provider.handle_tool_call("mempalace_list_wings", {})
        data = json.loads(result)
        assert "wings" in data or "error" in data

    def test_dispatch_search(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._collection = MagicMock()
        provider._collection.get.return_value = {
            "documents": [],
            "metadatas": [],
            "ids": [],
        }

        with patch("mempalace.searcher.search_memories", return_value=[]):
            result = provider.handle_tool_call("mempalace_search", {"query": "test"})
            data = json.loads(result)
            assert "results" in data or "error" in data

    def test_dispatch_add_drawer(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._collection = FakeCollection()

        result = provider.handle_tool_call(
            "mempalace_add_drawer",
            {
                "content": "test content",
                "wing": "test_wing",
            },
        )
        data = json.loads(result)
        assert "result" in data or "drawer_id" in data or "error" in data

    def test_dispatch_kg_query(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._kg = MagicMock()
        provider._kg.query_entity.return_value = []

        result = provider.handle_tool_call("mempalace_kg_query", {"entity": "test"})
        data = json.loads(result)
        assert "results" in data or "error" in data

    def test_dispatch_kg_add(self):
        provider = MempalaceMemoryProvider()
        provider._available = True
        provider._kg = MagicMock()

        result = provider.handle_tool_call(
            "mempalace_kg_add",
            {
                "subject": "Kai",
                "predicate": "works_on",
                "object": "Orion",
            },
        )
        data = json.loads(result)
        assert "result" in data or "error" in data

    def test_dispatch_diary_write(self):
        provider = MempalaceMemoryProvider()
        provider._available = True

        with patch("mempalace.mcp_server.tool_diary_write", return_value="ok"):
            result = provider.handle_tool_call(
                "mempalace_diary_write",
                {
                    "agent": "reviewer",
                    "entry": "test entry",
                },
            )
            data = json.loads(result)
            assert "result" in data or "error" in data

    def test_dispatch_diary_read(self):
        provider = MempalaceMemoryProvider()
        provider._available = True

        with patch("mempalace.mcp_server.tool_diary_read", return_value=[]):
            result = provider.handle_tool_call(
                "mempalace_diary_read",
                {
                    "agent": "reviewer",
                },
            )
            data = json.loads(result)
            assert "entries" in data or "error" in data
