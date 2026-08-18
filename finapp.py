
import streamlit as st
import plotly.express as px

from ai_helpers import ai_available, ai_categorize_details
from category_state import add_keyword_to_category, category_icon, init_session_state, save_categories
from config import MAX_AI_CATEGORIZE_ITEMS
from history import build_history_csv, merge_with_history, read_history_file
from parsing import load_transactions
from secrets_utils import get_secret
from theme import DARK_PALETTE, LIGHT_PALETTE, apply_theme_css, themed_chart

st.set_page_config(page_title="FinApp", page_icon="💰", layout="wide")
init_session_state()


def check_app_password():
    """Optional gate: if APP_PASSWORD is set in secrets, require it before showing the app.

    Off by default (no secret configured = no prompt), so local/solo use is unaffected.
    This exists to stop random visitors to a public deployment URL from burning your
    AI budget or viewing your uploaded financial data.
    """
    required = get_secret("APP_PASSWORD")
    if not required:
        return True
    if st.session_state.get("app_authed"):
        return True

    st.write("")
    st.write("")
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<div style='text-align:center; font-size:3rem;'>💰</div>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align:center; margin-top:-0.5rem;'>FinApp</h2>", unsafe_allow_html=True)
            st.caption("This dashboard is password-protected. Enter the password to continue.")
            pw = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
            if st.button("Unlock", type="primary", use_container_width=True):
                if pw == required:
                    st.session_state.app_authed = True
                    st.rerun()
                else:
                    st.error("Incorrect password")
    return False


def _clear_manual_categorize_widgets():
    for k in ["manual_cat_mode", "manual_cat_existing", "manual_cat_new"]:
        st.session_state.pop(k, None)


@st.dialog("Categorize this transaction")
def categorize_dialog():
    if not st.session_state.manual_categorize_queue:
        return
    item = st.session_state.manual_categorize_queue[0]
    remaining = len(st.session_state.manual_categorize_queue)
    st.write(f"**{item['details']}**")
    st.caption(f"${item['amount']:,.2f} · {remaining} transaction{'s' if remaining != 1 else ''} left to review")

    existing_categories = [c for c in st.session_state.categories.keys() if c != "Uncategorized"]
    mode = st.radio("Assign to:", ["Existing category", "New category"], horizontal=True, key="manual_cat_mode")
    if mode == "Existing category":
        chosen = st.selectbox("Category", options=existing_categories, key="manual_cat_existing")
    else:
        chosen = st.text_input("New category name", key="manual_cat_new").strip()

    col_skip, col_save = st.columns(2)
    with col_skip:
        if st.button("Skip", use_container_width=True):
            _clear_manual_categorize_widgets()
            st.session_state.manual_categorize_queue.pop(0)
            st.rerun()
    with col_save:
        if st.button("Save", type="primary", use_container_width=True):
            if not chosen:
                st.warning("Pick or name a category first.")
            else:
                if chosen not in st.session_state.categories:
                    st.session_state.categories[chosen] = []
                matches = st.session_state.debits_df["Details"] == item["details"]
                st.session_state.debits_df.loc[matches, "Category"] = chosen
                add_keyword_to_category(chosen, item["details"])
                _clear_manual_categorize_widgets()
                st.session_state.manual_categorize_queue.pop(0)
                st.rerun()


def main():
    dark_mode = st.session_state.get("dark_mode_toggle", False)
    palette = DARK_PALETTE if dark_mode else LIGHT_PALETTE
    apply_theme_css(palette)

    if not check_app_password():
        return

    col_title, col_toggle = st.columns([5, 1])
    with col_title:
        st.title("💰 Personal Finance Dashboard")
    with col_toggle:
        st.write("")
        st.toggle("🌙 Dark", key="dark_mode_toggle")

    with st.container(border=True):
        col_upload, col_history = st.columns(2)
        with col_upload:
            st.markdown("**Upload your transaction or bank statement file**")
            uploaded_file = st.file_uploader(
                "Upload your transaction or bank statement file",
                type=["csv", "xlsx", "xls", "pdf"],
                label_visibility="collapsed",
            )
            st.caption("CSV, Excel, or PDF bank/credit card statements.")
        with col_history:
            st.markdown("**📎 Merge with previous history (optional)**")
            history_file = st.file_uploader(
                "History CSV", type=["csv"], key="history_uploader", label_visibility="collapsed"
            )
            st.caption(
                "Have a history file downloaded from this app before? Upload it to combine "
                "with the new statement and build a trend over time."
            )

    if uploaded_file is not None:
        file_type = uploaded_file.name.split(".")[-1].lower()
        st.info(f"Processing {file_type.upper()} file: {uploaded_file.name}")
        df = load_transactions(uploaded_file, file_type)
        if df is not None:
            if history_file is not None:
                history_df = read_history_file(history_file)
                if history_df is not None:
                    new_count = len(df)
                    df = merge_with_history(df, history_df)
                    st.success(f"Merged with history: {len(df)} total transactions ({new_count} from this upload).")

            debits_df = df[df["Debit/Credit"] == "Debit"].copy()
            credits_df = df[df["Debit/Credit"] == "Credit"].copy()
            st.session_state.debits_df = debits_df.copy()

            if st.session_state.manual_categorize_queue:
                categorize_dialog()

            with st.container(border=True):
                metric_cols = st.columns(4)
                metric_cols[0].metric("Total Spent", f"${debits_df['AmountCharged'].sum():,.2f}")
                metric_cols[1].metric("Total Payments", f"${credits_df['AmountCharged'].sum():,.2f}")
                metric_cols[2].metric("Net", f"${credits_df['AmountCharged'].sum() - debits_df['AmountCharged'].sum():,.2f}")
                metric_cols[3].metric("Transactions", f"{len(df):,}")

            tab1, tab2, tab3 = st.tabs(["💸 Expenses (Debits)", "💵 Payments (Credits)", "📈 Trends"])
            with tab1:
                with st.container(border=True):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        new_category = st.text_input("New category Name")
                        add_button = st.button("Add Category", use_container_width=True)
                        if add_button and new_category:
                            if new_category not in st.session_state.categories:
                                st.session_state.categories[new_category] = []
                                save_categories()
                                st.rerun()
                    with col_b:
                        if ai_available():
                            st.write("Let AI sort your uncategorized expenses:")
                            if st.button("🤖 Auto-categorize with AI", use_container_width=True):
                                uncategorized = sorted(
                                    st.session_state.debits_df.loc[
                                        st.session_state.debits_df["Category"] == "Uncategorized", "Details"
                                    ].dropna().unique().tolist()
                                )
                                if not uncategorized:
                                    st.info("Nothing to categorize — everything already has a category.")
                                else:
                                    capped = uncategorized[:MAX_AI_CATEGORIZE_ITEMS]
                                    with st.spinner(f"Asking AI to categorize {len(capped)} transactions..."):
                                        mapping = ai_categorize_details(capped, list(st.session_state.categories.keys()))
                                    if mapping:
                                        applied = 0
                                        unresolved = []
                                        for detail in capped:
                                            category = mapping.get(detail, "Uncategorized")
                                            if category == "Uncategorized" or category not in st.session_state.categories:
                                                unresolved.append(detail)
                                                continue
                                            matches = st.session_state.debits_df["Details"] == detail
                                            st.session_state.debits_df.loc[matches, "Category"] = category
                                            add_keyword_to_category(category, detail)
                                            applied += 1
                                        if unresolved:
                                            queue_items = []
                                            for detail in unresolved:
                                                amt_matches = st.session_state.debits_df.loc[
                                                    st.session_state.debits_df["Details"] == detail, "AmountCharged"
                                                ]
                                                amount = amt_matches.iloc[0] if not amt_matches.empty else 0
                                                queue_items.append({"details": detail, "amount": amount})
                                            st.session_state.manual_categorize_queue = queue_items
                                        st.success(
                                            f"AI categorized {applied} transaction(s). "
                                            f"{len(unresolved)} need your input."
                                        )
                                        st.rerun()
                                    else:
                                        st.error("AI categorization failed. Try again in a moment.")

                with st.container(border=True):
                    st.subheader("Your Expenses")
                    edited_df = st.data_editor(
                        st.session_state.debits_df[["Date", "Details", "AmountCharged", "Category"]],
                        column_config={
                            "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY"),
                            "AmountCharged": st.column_config.NumberColumn("AmountCharged", format="%.2f USD"),
                            "Category": st.column_config.SelectboxColumn(
                                "Category",
                                options=list(st.session_state.categories.keys())
                            )
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="category_editor"
                    )
                    save_button = st.button("Apply Changes", type="primary")
                    if save_button:
                        for idx, row in edited_df.iterrows():
                            new_category = row["Category"]
                            if new_category == st.session_state.debits_df.at[idx, "Category"]:
                                continue
                            details = row["Details"]
                            st.session_state.debits_df.at[idx, "Category"] = new_category
                            add_keyword_to_category(new_category, details)

                with st.container(border=True):
                    st.subheader('Expense Summary')
                    category_totals = st.session_state.debits_df.groupby("Category")["AmountCharged"].sum().reset_index()
                    category_totals = category_totals.sort_values("AmountCharged", ascending=False)
                    category_totals["Category"] = category_totals["Category"].apply(
                        lambda c: f"{category_icon(c)} {c}"
                    )
                    col_table, col_chart = st.columns(2)
                    with col_table:
                        st.dataframe(
                            category_totals,
                            column_config={
                                "AmountCharged": st.column_config.NumberColumn("AmountCharged", format="%.2f USD")
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                    with col_chart:
                        fig = px.pie(
                            category_totals,
                            values="AmountCharged",
                            names="Category",
                            title="Expenses by Category",
                            color_discrete_sequence=palette["chart_colors"]
                        )
                        st.plotly_chart(themed_chart(fig, palette), use_container_width=True)
            with tab2:
                with st.container(border=True):
                    st.subheader("Payment Summary")
                    total_payments = credits_df["AmountCharged"].sum()
                    st.metric("Total payments", f"{total_payments:,.2f} USD")
                    st.dataframe(credits_df, use_container_width=True, hide_index=True)
            with tab3:
                with st.container(border=True):
                    st.subheader("Spending Trends")
                    trend_source = st.session_state.debits_df
                    if trend_source.empty:
                        st.info("No expense data to chart yet.")
                    else:
                        col_view, col_chart_type = st.columns(2)
                        with col_view:
                            view = st.radio(
                                "View", ["Total Spending", "By Category"], horizontal=True, key="trend_view"
                            )
                        with col_chart_type:
                            chart_type = st.radio(
                                "Chart type", ["Bar", "Line", "Area"], horizontal=True, key="trend_chart_type"
                            )

                        trend_df = trend_source.copy()
                        trend_df["Month"] = trend_df["Date"].dt.to_period("M").astype(str)

                        if len(trend_df["Month"].unique()) < 2:
                            st.caption(
                                "Only one month of data so far — download your history below and merge it back "
                                "in next time you upload a statement to build a real trend."
                            )

                        chart_fn = {"Bar": px.bar, "Line": px.line, "Area": px.area}[chart_type]
                        if view == "Total Spending":
                            monthly_totals = trend_df.groupby("Month")["AmountCharged"].sum().reset_index().sort_values("Month")
                            fig_trend = chart_fn(
                                monthly_totals, x="Month", y="AmountCharged",
                                title="Monthly Spending",
                                labels={"AmountCharged": "Total Spent ($)"},
                                color_discrete_sequence=palette["chart_colors"]
                            )
                        else:
                            cat_trend = trend_df.groupby(["Month", "Category"])["AmountCharged"].sum().reset_index().sort_values("Month")
                            chart_kwargs = {"color": "Category"}
                            if chart_type == "Bar":
                                chart_kwargs["barmode"] = "stack"
                            fig_trend = chart_fn(
                                cat_trend, x="Month", y="AmountCharged",
                                title="Monthly Spending by Category",
                                labels={"AmountCharged": "Total Spent ($)"},
                                color_discrete_sequence=palette["chart_colors"],
                                **chart_kwargs
                            )
                        st.plotly_chart(themed_chart(fig_trend, palette), use_container_width=True)

                with st.container(border=True):
                    st.subheader("Save Your History")
                    st.caption(
                        "Download this combined, categorized dataset. Next time you're back, upload it again "
                        "under \"Merge with previous history\" above along with your new statement -- that's "
                        "how this app keeps a running history without needing its own database."
                    )
                    history_csv = build_history_csv(st.session_state.debits_df, credits_df)
                    st.download_button(
                        "⬇️ Download updated history (CSV)",
                        data=history_csv,
                        file_name="finapp_history.csv",
                        mime="text/csv"
                    )
    with st.expander("Help & Instructions"):
        ai_status = "enabled" if ai_available() else "not configured (add an API key to enable it, see README)"
        st.markdown(f"""
        ### Supported File Types
        - **CSV**: Standard comma-separated values files with transaction data
        - **Excel**: Both .xlsx and .xls formats with transaction data
        - **PDF**: Text is pulled from the PDF and, when AI is enabled, structured into transactions automatically

        ### Required Columns
        Your file should have these columns (or a common variant, which is auto-mapped):
        - **Date**: Transaction date
        - **Details**: Description of the transaction
        - **AmountCharged**: Transaction amount
        - **Debit/Credit**: Indicates whether it's an expense (Debit) or payment (Credit)

        ### AI-assisted features (status: {ai_status})
        - **PDF extraction**: reads unstructured statement text and turns it into transaction rows
        - **Column mapping**: when a CSV/Excel file has unrecognized headers, AI can map them for you
        - **Auto-categorize**: assigns categories to uncategorized transactions in one click. Anything AI
          isn't confident about pops up as a quick "categorize this" screen instead of being left alone,
          where you can assign an existing category or create a new one on the spot.

        ### Building a history across months
        This app doesn't store anything on a server between sessions. Instead, the **Trends** tab lets
        you download a "history" CSV after each upload. Next time you come back, upload your new
        statement as usual, then also drop that history file into **"Merge with previous history"**
        above the uploader -- it combines both, skips duplicate transactions, and keeps your category
        corrections intact so trends build up over time.

        ### Starter categories
        A set of common categories (Groceries, Dining Out, Transportation, Rent/Mortgage, Utilities,
        Healthcare, Subscriptions, Entertainment, Income, Fees & Interest, Miscellaneous) comes
        pre-loaded so you're not starting from a blank list -- add, rename, or ignore any of them.

        ### Light / dark mode
        Use the toggle next to the title to switch themes.
        """)


if __name__ == "__main__":
    main()
