import category_state
from category_state import add_keyword_to_category, category_icon


class TestCategoryIcon:
    def test_known_category_returns_its_icon(self):
        assert category_icon("Groceries") == "\U0001f6d2"

    def test_unknown_category_falls_back_to_default(self):
        assert category_icon("Some Custom Category") == "\U0001f3f7️"

    def test_matching_is_case_and_whitespace_insensitive(self):
        assert category_icon("  GROCERIES  ") == category_icon("groceries")


class TestAddKeywordToCategory:
    def test_creates_new_category_and_saves_to_disk(self, tmp_path, monkeypatch):
        # CATEGORY_FILE must be redirected before this runs -- writing to the
        # real project's categories.json from a test would corrupt live data.
        isolated_file = tmp_path / "categories.json"
        monkeypatch.setattr(category_state, "CATEGORY_FILE", str(isolated_file))
        import streamlit as st
        st.session_state.categories = {"Uncategorized": []}

        result = add_keyword_to_category("Shopping", "amazon")

        assert result is True
        assert "amazon" in st.session_state.categories["Shopping"]
        assert isolated_file.exists()

    def test_does_not_duplicate_an_existing_keyword(self, tmp_path, monkeypatch):
        isolated_file = tmp_path / "categories.json"
        monkeypatch.setattr(category_state, "CATEGORY_FILE", str(isolated_file))
        import streamlit as st
        st.session_state.categories = {"Uncategorized": [], "Shopping": ["amazon"]}

        result = add_keyword_to_category("Shopping", "amazon")

        assert result is False
        assert st.session_state.categories["Shopping"] == ["amazon"]
