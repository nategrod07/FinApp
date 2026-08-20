"""Light/dark theming.

Streamlit's config.toml only expresses one static theme, so a runtime light/dark
toggle needs its own CSS injected over the top. config.toml is still set to match
the light palette below, since that's what paints before any session state (and
this CSS) exists on first load.
"""

import streamlit as st

LIGHT_PALETTE = {
    "bg": "#FBF7EE",
    "surface": "#F3ECD9",
    "primary": "#1B4332",
    "primary_light": "#2D6A4F",
    "text": "#26261F",
    "text_muted": "#5C5A4E",
    "border": "#E2D5B7",
    "button_text": "#FBF7EE",
    "plotly_template": "plotly_white",
    "chart_colors": ["#1B4332", "#2D6A4F", "#40916C", "#52B788", "#74C69D", "#95D5B2", "#B7E4C7", "#D8F3DC"],
}
# True black base -- green is an accent color here (buttons, borders, primary
# text), not a tint over the whole page.
DARK_PALETTE = {
    "bg": "#000000",
    "surface": "#141414",
    "primary": "#52B788",
    "primary_light": "#74C69D",
    "text": "#F1EAD9",
    "text_muted": "#9CA39B",
    "border": "#2A3B30",
    "button_text": "#FBF7EE",
    "plotly_template": "plotly_dark",
    "chart_colors": ["#95D5B2", "#74C69D", "#52B788", "#40916C", "#B7E4C7", "#D8F3DC", "#2D6A4F", "#B7E4C7"],
}


def apply_theme_css(palette):
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: {palette['bg']};
        color: {palette['text']};
    }}
    [data-testid="stHeader"] {{
        background-color: transparent;
    }}
    [data-testid="stSidebar"],
    [data-testid="stMetric"],
    [data-testid="stExpander"],
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {palette['surface']};
        border-radius: 12px;
        border: 1px solid {palette['border']};
    }}
    [data-testid="stFileUploaderDropzoneInstructions"] span,
    [data-testid="stFileUploaderDropzoneInstructions"] small,
    [data-testid="stFileUploaderDropzoneInstructions"] svg {{
        color: {palette['text_muted']} !important;
        fill: {palette['text_muted']} !important;
    }}
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
        border: 1px solid {palette['border']};
        border-radius: 8px;
    }}
    [data-testid="stMetric"] {{
        padding: 1rem;
    }}
    h1, h2, h3, h4, p, span, label, div, .stMarkdown {{
        color: {palette['text']};
    }}
    [data-testid="stMetricValue"] {{
        color: {palette['text']} !important;
    }}
    [data-testid="stMetricLabel"] {{
        color: {palette['text_muted']} !important;
    }}
    [data-testid^="stBaseButton"] {{
        border-radius: 8px !important;
        border: 1px solid {palette['primary']} !important;
        background-color: {palette['surface']} !important;
        color: {palette['text']} !important;
    }}
    [data-testid="stBaseButton-primary"] {{
        background-color: {palette['primary']} !important;
        color: {palette['button_text']} !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {palette['text_muted']};
    }}
    .stTabs [aria-selected="true"] {{
        color: {palette['primary']};
    }}
    /* The selectbox's own background is locked to Streamlit's static (light)
       config.toml theme regardless of this toggle, so fighting it to go dark
       just reintroduces invisible text -- instead pin its text dark so it
       always reads against that permanently-light background. */
    [data-baseweb="select"] * {{
        color: {LIGHT_PALETTE['text']} !important;
    }}
    [data-baseweb="popover"], [data-baseweb="menu"], [role="option"] {{
        background-color: {LIGHT_PALETTE['surface']} !important;
        color: {LIGHT_PALETTE['text']} !important;
    }}
    [data-testid="stTextInput"] input, [data-testid="stTextInput"] div {{
        background-color: {palette['surface']} !important;
        color: {palette['text']} !important;
    }}
    body {{
        background-color: {palette['bg']};
    }}
    /* Alert boxes (st.info/success/warning/error) otherwise keep Streamlit's own
       blue/green/orange/red regardless of theme -- normalize the box itself to
       match our cards, leave the icon's natural color as a quiet severity cue. */
    [data-testid="stAlertContainer"] {{
        background-color: {palette['surface']} !important;
        border: 1px solid {palette['border']};
        border-radius: 8px;
    }}
    [data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] span {{
        color: {palette['text']} !important;
    }}
    /* The small hover toolbar (search/download/fullscreen) over tables and charts. */
    [data-testid="stElementToolbar"], [data-testid="stElementToolbarButtonContainer"] {{
        background-color: {palette['surface']} !important;
    }}
    /* The uploaded-file name/size row pins light-mode text regardless of theme. */
    [data-testid="stFileUploaderFileName"], [data-testid="stFileUploaderFile"] small {{
        color: {palette['text']} !important;
    }}
    /* st.dialog's own background is a translucent tan (~25% opacity) that just
       blends with whatever's behind it -- give the backdrop a neutral dark
       scrim instead (works in both themes). The card itself (role="dialog")
       is pinned to Streamlit's native light theme by chained atomic classes
       with higher CSS specificity than an attribute selector can beat, the
       same issue as the select dropdown -- so instead of fighting its
       background, pin its text to always read against that permanently-light
       card, the same fix used there. */
    [data-testid="stDialog"] {{
        background-color: rgba(0, 0, 0, 0.6) !important;
    }}
    /* Excludes <button> and its descendants -- those already correctly follow
       the dynamic palette on their own, and this selector's specificity would
       otherwise win over that and flatten every dialog button back to dark text. */
    [data-testid="stDialog"] [role="dialog"] *:not(button):not(button *) {{
        color: {LIGHT_PALETTE['text']} !important;
    }}
    </style>
    """, unsafe_allow_html=True)


def themed_chart(fig, palette, height=380):
    fig.update_layout(
        template=palette["plotly_template"],
        paper_bgcolor=palette["surface"],
        plot_bgcolor=palette["surface"],
        font_color=palette["text"],
        title_font_color=palette["text"],
        legend_font_color=palette["text"],
        height=height,
        margin={"t": 40, "b": 20, "l": 20, "r": 20},
    )
    return fig
