
import pandas as pd
import plotly.express as px
import streamlit as st

from ai_helpers import ai_available, ai_categorize_details
from auth import check_password_lockout, record_failed_password_attempt, verify_password
from budget import allocate_budget, annualize_salary, compare_actual_vs_budget, estimate_net_income
from budget_data import COMMON_EXPENSE_CATEGORIES, FILING_STATUSES, US_STATES
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

    is_locked, retry_after = check_password_lockout()

    st.write("")
    st.write("")
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<div style='text-align:center; font-size:3rem;'>💰</div>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align:center; margin-top:-0.5rem;'>FinApp</h2>", unsafe_allow_html=True)
            st.caption("This dashboard is password-protected. Enter the password to continue.")
            if is_locked:
                minutes = max(1, int(retry_after // 60) + 1)
                st.error(f"Too many incorrect attempts. Try again in about {minutes} minute{'s' if minutes != 1 else ''}.")
            else:
                pw = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
                if st.button("Unlock", type="primary", use_container_width=True):
                    if verify_password(pw, required):
                        st.session_state.app_authed = True
                        st.rerun()
                    else:
                        record_failed_password_attempt()
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


def render_budget_planner(palette):
    st.subheader("Estimate Your Take-Home Pay")
    st.caption(
        "A rough budgeting estimate, not tax advice -- federal brackets are 2024 figures and "
        "state tax is a single blended rate per state, not full bracket tables. Local/county "
        "income taxes aren't included. Check a real paystub or tax tool for anything that needs "
        "to be exact."
    )

    with st.container(border=True):
        col_pay, col_filing, col_result = st.columns(3)
        with col_pay:
            pay_type = st.radio("Pay type", ["Yearly", "Monthly", "Hourly"], horizontal=True, key="budget_pay_type")
            if pay_type == "Hourly":
                amount = st.number_input("Hourly rate ($)", min_value=0.0, value=20.0, step=0.5, key="budget_amount")
                hours_per_week = st.number_input(
                    "Hours per week", min_value=1, max_value=80, value=40, key="budget_hours"
                )
            elif pay_type == "Monthly":
                amount = st.number_input(
                    "Monthly salary ($)", min_value=0.0, value=5000.0, step=100.0, key="budget_amount"
                )
                hours_per_week = 40
            else:
                amount = st.number_input(
                    "Yearly salary ($)", min_value=0.0, value=60000.0, step=1000.0, key="budget_amount"
                )
                hours_per_week = 40
        with col_filing:
            state = st.selectbox("State", options=US_STATES, index=US_STATES.index("Texas"), key="budget_state")
            filing_status = st.selectbox("Filing status", options=FILING_STATUSES, key="budget_filing_status")
        gross_yearly = annualize_salary(amount, pay_type, hours_per_week)
        tax_result = estimate_net_income(gross_yearly, filing_status, state)
        with col_result:
            st.metric("Est. Gross Yearly", f"${gross_yearly:,.0f}")
            st.metric("Est. Net Monthly (take-home)", f"${tax_result['net_monthly']:,.0f}")

    with st.expander("See the estimated tax breakdown"):
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Federal Tax / yr", f"${tax_result['federal_tax']:,.0f}")
        b2.metric("State Tax / yr", f"${tax_result['state_tax']:,.0f}")
        b3.metric("FICA / yr", f"${tax_result['fica_tax']:,.0f}")
        b4.metric("Total Tax / yr", f"${tax_result['total_tax']:,.0f}")

    st.divider()
    st.subheader("Build Your Budget")
    st.caption(f"Allocating from an estimated **${tax_result['net_monthly']:,.0f}/month** take-home.")

    col_bills, col_other = st.columns(2)
    with col_bills:
        st.markdown("**Bills** (add or remove rows as needed)")
        bills_df = st.data_editor(
            pd.DataFrame({"Bill": ["Rent/Mortgage", "", ""], "Amount": [0.0, 0.0, 0.0]}),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="budget_bills_editor",
            column_config={
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f USD", min_value=0.0),
            },
        )
    with col_other:
        st.markdown("**Other Spending**")
        other_df = st.data_editor(
            pd.DataFrame({
                "Category": COMMON_EXPENSE_CATEGORIES,
                "Amount": [0.0] * len(COMMON_EXPENSE_CATEGORIES),
            }),
            num_rows="fixed",
            use_container_width=True,
            hide_index=True,
            key="budget_other_editor",
            column_config={
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f USD", min_value=0.0),
            },
        )

    bills = [
        {"name": row["Bill"], "amount": row["Amount"] or 0}
        for _, row in bills_df.iterrows() if str(row["Bill"]).strip()
    ]
    other_spend = [{"category": row["Category"], "amount": row["Amount"] or 0} for _, row in other_df.iterrows()]
    allocation = allocate_budget(tax_result["net_monthly"], bills, other_spend)

    with st.container(border=True):
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Bills", f"${allocation['total_bills']:,.2f}")
        m2.metric("Total Other Spending", f"${allocation['total_other']:,.2f}")
        m3.metric(
            "Over Budget By" if allocation["is_over_budget"] else "Remaining",
            f"${abs(allocation['remaining']):,.2f}",
        )
        if allocation["is_over_budget"]:
            st.warning("Your bills and spending add up to more than your estimated take-home pay.")

        if allocation["breakdown"]:
            breakdown_df = pd.DataFrame(allocation["breakdown"])
            fig = px.pie(
                breakdown_df, values="amount", names="category",
                title="Monthly Budget Allocation",
                color_discrete_sequence=palette["chart_colors"],
            )
            st.plotly_chart(themed_chart(fig, palette), use_container_width=True)
        else:
            st.info("Fill in some bills or spending above to see your allocation.")

    st.divider()
    st.subheader("Actual vs. Budgeted")

    debits_df = st.session_state.get("debits_df")
    if debits_df is None or debits_df.empty:
        st.info(
            "Upload a statement in the Transactions tab to compare your actual spending "
            "against this budget."
        )
        return

    budgeted_by_category = {}
    for item in bills + other_spend:
        name = item.get("name") or item.get("category")
        amount = item["amount"]
        if not name or amount <= 0:
            continue
        budgeted_by_category[name] = budgeted_by_category.get(name, 0.0) + amount

    trend_df = debits_df.copy()
    trend_df["Month"] = trend_df["Date"].dt.to_period("M").astype(str)
    months = sorted(trend_df["Month"].unique(), reverse=True)
    selected_month = st.selectbox("Month", options=months, key="budget_compare_month")

    actual_by_category = (
        trend_df[trend_df["Month"] == selected_month]
        .groupby("Category")["AmountCharged"].sum().to_dict()
    )

    comparison = compare_actual_vs_budget(budgeted_by_category, actual_by_category)

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Budgeted", f"${comparison['total_budgeted']:,.2f}")
        c2.metric("Actual", f"${comparison['total_actual']:,.2f}")
        c3.metric(
            "Over" if comparison["total_variance"] < 0 else "Under",
            f"${abs(comparison['total_variance']):,.2f}",
        )

        if not comparison["rows"]:
            st.info("No budgeted amounts or transactions to compare for this month.")
        else:
            table_rows = []
            for row in comparison["rows"]:
                table_rows.append({
                    "Category": f"{category_icon(row['category'])} {row['category']}",
                    "Budgeted": f"${row['budgeted']:,.2f}",
                    "Actual": f"${row['actual']:,.2f}",
                    "Variance": f"{'-' if row['is_over'] else '+'}${abs(row['variance']):,.2f}",
                    "": "🔴 Over" if row["is_over"] else "🟢 Under",
                })
            comparison_display = pd.DataFrame(table_rows)
            comparison_display.index = [""] * len(comparison_display)
            st.table(comparison_display)

            chart_df = pd.DataFrame(comparison["rows"])
            fig_compare = px.bar(
                chart_df, x="category", y=["budgeted", "actual"],
                barmode="group",
                title=f"Budgeted vs. Actual -- {selected_month}",
                labels={"category": "Category", "value": "Amount ($)", "variable": ""},
                color_discrete_sequence=palette["chart_colors"],
            )
            st.plotly_chart(themed_chart(fig_compare, palette), use_container_width=True)


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

    page_tab1, page_tab2 = st.tabs(["📊 Transactions", "💰 Budget Planner"])

    with page_tab1:
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
                            # st.dataframe/st.data_editor render via a canvas grid whose
                            # colors come from Streamlit's static config.toml theme, not
                            # CSS -- unreachable by the dark-mode toggle. st.table is a
                            # plain HTML table, so it actually themes correctly.
                            table_display = category_totals.copy()
                            table_display["AmountCharged"] = table_display["AmountCharged"].apply(lambda a: f"{a:,.2f} USD")
                            table_display.index = [""] * len(table_display)
                            st.table(table_display)
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
                        if credits_df.empty:
                            st.info("No payments in this file.")
                        else:
                            payments_display = credits_df[["Date_formatted", "Details", "AmountCharged", "Category"]].copy()
                            payments_display = payments_display.rename(columns={"Date_formatted": "Date"})
                            payments_display["AmountCharged"] = payments_display["AmountCharged"].apply(lambda a: f"{a:,.2f} USD")
                            payments_display.index = [""] * len(payments_display)
                            st.table(payments_display)
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
                                cat_trend = (
                                    trend_df.groupby(["Month", "Category"])["AmountCharged"]
                                    .sum().reset_index().sort_values("Month")
                                )
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
                            # Without this, a single-month "Month" value (e.g. "2024-04")
                            # reads as date-like to Plotly's axis-type auto-detection,
                            # which then renders confusing sub-second tick labels.
                            fig_trend.update_xaxes(type="category")
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

    with page_tab2:
        render_budget_planner(palette)

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

        ### Budget Planner
        The **Budget Planner** tab works independently of any uploaded statement. Enter your
        pay (hourly, monthly, or yearly), state, and filing status for an estimated take-home
        pay after federal, state, and FICA taxes -- this is a rough estimate for budgeting, not
        tax advice. Then list your bills and fill in amounts for common spending categories to
        see how your take-home pay breaks down, visualized as a pie chart. Nothing here is saved
        between sessions.
        """)


if __name__ == "__main__":
    main()
