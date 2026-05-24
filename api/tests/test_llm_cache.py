"""Unit tests for app.services.llm.cache — fingerprint stability + key.

DB-backed paths (get_cached / store / purge_expired) are exercised by
the orchestrator integration tests; the pure-logic surface tested here
is what callers compose to drive those.
"""

from __future__ import annotations

from app.services.llm import cache as c


class TestComputeDataFingerprint:
    def test_same_input_same_fingerprint(self):
        a = c.compute_data_fingerprint({"x": 1, "y": [1, 2, 3]})
        b = c.compute_data_fingerprint({"x": 1, "y": [1, 2, 3]})
        assert a == b
        # sha256 length
        assert len(a) == 64

    def test_key_order_independent(self):
        a = c.compute_data_fingerprint({"x": 1, "y": 2})
        b = c.compute_data_fingerprint({"y": 2, "x": 1})
        assert a == b

    def test_change_in_input_changes_fingerprint(self):
        a = c.compute_data_fingerprint({"x": 1})
        b = c.compute_data_fingerprint({"x": 2})
        assert a != b

    def test_list_order_matters(self):
        # Lists are order-significant — sort upstream if order shouldn't matter.
        a = c.compute_data_fingerprint({"ids": [1, 2, 3]})
        b = c.compute_data_fingerprint({"ids": [3, 2, 1]})
        assert a != b


class TestComputeCacheKey:
    def test_key_includes_tenant_isolation(self):
        a = c.compute_cache_key("tenant-a", "fleet", None, "fp", "v1")
        b = c.compute_cache_key("tenant-b", "fleet", None, "fp", "v1")
        assert a != b

    def test_key_includes_scope(self):
        a = c.compute_cache_key("t", "fleet", None, "fp", "v1")
        b = c.compute_cache_key("t", "site", "s1", "fp", "v1")
        assert a != b

    def test_key_includes_template_version(self):
        a = c.compute_cache_key("t", "fleet", None, "fp", "v1")
        b = c.compute_cache_key("t", "fleet", None, "fp", "v2")
        assert a != b

    def test_key_is_64_hex(self):
        key = c.compute_cache_key("t", "fleet", None, "fp", "v1")
        assert len(key) == 64
        int(key, 16)  # Should parse as hex
