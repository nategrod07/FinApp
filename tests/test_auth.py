import auth
from auth import check_password_lockout, record_failed_password_attempt, verify_password


class TestVerifyPassword:
    def test_correct_password_matches(self):
        assert verify_password("hunter2", "hunter2") is True

    def test_incorrect_password_does_not_match(self):
        assert verify_password("wrong", "hunter2") is False

    def test_non_string_required_value_is_handled(self):
        # st.secrets can hand back a non-str for a numeric-looking TOML value.
        assert verify_password("1234", 1234) is True


class TestPasswordLockout:
    def _reset(self, monkeypatch, *, max_attempts=5, window_seconds=900):
        monkeypatch.setattr(auth, "PASSWORD_MAX_ATTEMPTS", max_attempts)
        monkeypatch.setattr(auth, "PASSWORD_LOCKOUT_WINDOW_SECONDS", window_seconds)
        auth._password_lockout_state.clear()

    def test_not_locked_initially(self, monkeypatch):
        self._reset(monkeypatch)
        locked, retry_after = check_password_lockout()
        assert locked is False
        assert retry_after == 0

    def test_not_locked_under_the_attempt_cap(self, monkeypatch):
        self._reset(monkeypatch, max_attempts=5)
        for _ in range(4):
            record_failed_password_attempt()
        locked, _ = check_password_lockout()
        assert locked is False

    def test_locks_out_once_attempt_cap_is_hit(self, monkeypatch):
        self._reset(monkeypatch, max_attempts=3)
        for _ in range(3):
            record_failed_password_attempt()
        locked, retry_after = check_password_lockout()
        assert locked is True
        assert retry_after > 0

    def test_retry_after_is_within_the_lockout_window(self, monkeypatch):
        self._reset(monkeypatch, max_attempts=1, window_seconds=600)
        record_failed_password_attempt()
        locked, retry_after = check_password_lockout()
        assert locked is True
        assert retry_after <= 600
