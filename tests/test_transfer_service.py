"""Tests for TransferService routing logic."""
import os
import pytest
from unittest.mock import patch, MagicMock

from app.services.transfer_service import (
    normalize_language_code,
    resolve_transfer_queue_for_language,
    resolve_transfer_destination_for_queue,
    find_queue_by_name,
)
from app.models import Language


class TestNormalizeLanguageCode:
    def test_none(self):
        assert normalize_language_code(None) == "en"

    def test_empty_string(self):
        assert normalize_language_code("") == "en"

    def test_english_enum(self):
        assert normalize_language_code(Language.ENGLISH) == "en"

    def test_spanish_enum(self):
        assert normalize_language_code(Language.SPANISH) == "es"

    def test_chinese_enum(self):
        assert normalize_language_code(Language.CHINESE) == "zh"

    def test_string_en(self):
        assert normalize_language_code("en") == "en"

    def test_string_uppercase(self):
        assert normalize_language_code("ES") == "es"

    def test_whitespace_padded(self):
        assert normalize_language_code("  zh  ") == "zh"


class TestResolveTransferQueueForLanguage:
    def test_english(self):
        assert resolve_transfer_queue_for_language(Language.ENGLISH) == "scheduling_en"

    def test_spanish(self):
        assert resolve_transfer_queue_for_language(Language.SPANISH) == "scheduling_es"

    def test_chinese_defaults_to_en(self):
        assert resolve_transfer_queue_for_language(Language.CHINESE) == "scheduling_en"

    def test_unknown_language(self):
        assert resolve_transfer_queue_for_language("fr") == "scheduling_en"

    def test_none_defaults_to_en(self):
        assert resolve_transfer_queue_for_language(None) == "scheduling_en"

    def test_env_override(self):
        with patch.dict(os.environ, {"LANGUAGE_QUEUE_MAP": '{"fr": "scheduling_fr"}'}):
            assert resolve_transfer_queue_for_language("fr") == "scheduling_fr"

    def test_env_override_replaces_default(self):
        with patch.dict(os.environ, {"LANGUAGE_QUEUE_MAP": '{"es": "custom_spanish_queue"}'}):
            assert resolve_transfer_queue_for_language(Language.SPANISH) == "custom_spanish_queue"


class TestResolveTransferDestinationForQueue:
    def test_env_var_override(self):
        with patch.dict(os.environ, {"TRANSFER_TARGET_SCHEDULING_EN": "sip:en@pbx.local"}):
            result = resolve_transfer_destination_for_queue("scheduling_en")
            assert result == "sip:en@pbx.local"

    def test_json_env_override(self):
        with patch.dict(os.environ, {"QUEUE_TRANSFER_TARGETS": '{"scheduling_en": "+15551112222"}'}):
            result = resolve_transfer_destination_for_queue("scheduling_en")
            assert result == "+15551112222"

    def test_no_config_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            # Clear relevant env vars
            for k in list(os.environ):
                if k.startswith("TRANSFER_TARGET_") or k == "QUEUE_TRANSFER_TARGETS":
                    del os.environ[k]
            result = resolve_transfer_destination_for_queue("scheduling_en")
            assert result is None

    def test_json_takes_precedence(self):
        with patch.dict(os.environ, {
            "QUEUE_TRANSFER_TARGETS": '{"scheduling_en": "from_json"}',
            "TRANSFER_TARGET_SCHEDULING_EN": "from_env",
        }):
            result = resolve_transfer_destination_for_queue("scheduling_en")
            assert result == "from_json"


class TestFindQueueByName:
    def test_found(self):
        q = MagicMock()
        q.Queue = "scheduling_en"
        state = MagicMock()
        state.queues = [q]
        assert find_queue_by_name(state, "scheduling_en") == q

    def test_case_insensitive(self):
        q = MagicMock()
        q.Queue = "Scheduling_EN"
        state = MagicMock()
        state.queues = [q]
        assert find_queue_by_name(state, "scheduling_en") == q

    def test_not_found(self):
        q = MagicMock()
        q.Queue = "scheduling_en"
        state = MagicMock()
        state.queues = [q]
        assert find_queue_by_name(state, "scheduling_es") is None

    def test_empty_queues(self):
        state = MagicMock()
        state.queues = []
        assert find_queue_by_name(state, "scheduling_en") is None
