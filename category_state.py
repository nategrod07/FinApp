"""Category persistence (categories.json) and related session state."""

import json
import os

import streamlit as st

from config import CATEGORY_ICONS, DEFAULT_CATEGORY_ICON

CATEGORY_FILE = "categories.json"


def init_session_state():
    """Set up session_state defaults. Call once, near the top of the app."""
    if "categories" not in st.session_state:
        st.session_state.categories = {"Uncategorized": []}
    if "column_ai_mappings" not in st.session_state:
        st.session_state.column_ai_mappings = {}
    if "manual_categorize_queue" not in st.session_state:
        st.session_state.manual_categorize_queue = []

    if os.path.exists(CATEGORY_FILE):
        with open(CATEGORY_FILE) as f:
            st.session_state.categories = json.load(f)


def save_categories():
    with open(CATEGORY_FILE, "w") as f:
        json.dump(st.session_state.categories, f)


def add_keyword_to_category(category, keyword):
    keyword = keyword.strip()
    if category not in st.session_state.categories:
        st.session_state.categories[category] = []
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False


def category_icon(category):
    return CATEGORY_ICONS.get(str(category).strip().lower(), DEFAULT_CATEGORY_ICON)
