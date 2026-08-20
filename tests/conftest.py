"""Shared pytest fixtures: a fake st.session_state so app modules can run
without a live Streamlit server, reset fresh before every test.
"""

import pytest
import streamlit as st


class FakeSessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


@pytest.fixture(autouse=True)
def fresh_session_state():
    st.session_state = FakeSessionState()
    yield st.session_state
