import ai_helpers
from ai_helpers import _prune_old, check_and_record_ai_call, extract_json_from_response


class TestExtractJsonFromResponse:
    def test_parses_plain_json(self):
        assert extract_json_from_response('[{"a": 1}]') == [{"a": 1}]

    def test_strips_markdown_json_fences(self):
        text = '```json\n[{"a": 1}]\n```'
        assert extract_json_from_response(text) == [{"a": 1}]

    def test_strips_plain_markdown_fences(self):
        text = '```\n{"a": 1}\n```'
        assert extract_json_from_response(text) == {"a": 1}

    def test_returns_none_on_invalid_json(self):
        assert extract_json_from_response("not json at all") is None


class TestPruneOld:
    def test_drops_timestamps_older_than_window(self):
        import time
        now = time.time()
        timestamps = [now - 7200, now - 10, now]
        result = _prune_old(timestamps, window_seconds=3600)
        assert result == [now - 10, now]


class TestRateLimiter:
    def _reset(self, monkeypatch, *, global_hourly=20, global_monthly=100, session_hourly=5):
        monkeypatch.setattr(ai_helpers, "AI_GLOBAL_HOURLY_LIMIT", global_hourly)
        monkeypatch.setattr(ai_helpers, "AI_GLOBAL_MONTHLY_LIMIT", global_monthly)
        monkeypatch.setattr(ai_helpers, "AI_SESSION_HOURLY_LIMIT", session_hourly)
        ai_helpers._global_rate_limiter_state.clear()

    def test_allows_calls_under_the_limit(self, monkeypatch):
        self._reset(monkeypatch, global_hourly=5, session_hourly=5)
        for _ in range(3):
            allowed, reason = check_and_record_ai_call()
            assert allowed is True
            assert reason is None

    def test_blocks_once_global_hourly_limit_is_hit(self, monkeypatch):
        self._reset(monkeypatch, global_hourly=2, session_hourly=100)
        assert check_and_record_ai_call()[0] is True
        assert check_and_record_ai_call()[0] is True
        allowed, reason = check_and_record_ai_call()
        assert allowed is False
        assert "hour" in reason.lower()

    def test_blocks_once_session_limit_is_hit_even_under_global_cap(self, monkeypatch):
        self._reset(monkeypatch, global_hourly=100, session_hourly=1)
        assert check_and_record_ai_call()[0] is True
        allowed, reason = check_and_record_ai_call()
        assert allowed is False
        assert "session" in reason.lower()

    def test_blocks_once_monthly_limit_is_hit(self, monkeypatch):
        self._reset(monkeypatch, global_hourly=100, global_monthly=1, session_hourly=100)
        assert check_and_record_ai_call()[0] is True
        allowed, reason = check_and_record_ai_call()
        assert allowed is False
        assert "month" in reason.lower()
