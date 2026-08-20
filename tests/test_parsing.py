import pandas as pd
import streamlit as st

from parsing import (
    categorize_transactions,
    clean_amount_and_type_columns,
    clean_dates,
    map_columns_with_aliases,
)


class TestCleanAmountAndTypeColumns:
    def test_strips_dollar_signs_and_commas(self):
        # Regression test: the old code chained .str.replace(",", "") into a
        # plain Series.replace("$", "", regex=True), which never actually
        # stripped dollar signs since "$" is a regex end-of-string anchor --
        # amounts like "$1,234.56" silently became NaN and got dropped.
        df = pd.DataFrame({"AmountCharged": ["$1,234.56", "45.10"], "Debit/Credit": ["Debit", "Debit"]})
        result = clean_amount_and_type_columns(df)
        assert result["AmountCharged"].tolist() == [1234.56, 45.10]
        assert result["AmountCharged"].isna().sum() == 0

    def test_normalizes_debit_credit_casing(self):
        df = pd.DataFrame({"AmountCharged": [1, 2, 3], "Debit/Credit": ["debit", "DEBIT", "credit"]})
        result = clean_amount_and_type_columns(df)
        assert result["Debit/Credit"].tolist() == ["Debit", "Debit", "Credit"]

    def test_leaves_already_numeric_amounts_untouched(self):
        df = pd.DataFrame({"AmountCharged": [1.5, 2.5], "Debit/Credit": ["Debit", "Credit"]})
        result = clean_amount_and_type_columns(df)
        assert result["AmountCharged"].tolist() == [1.5, 2.5]


class TestCleanDates:
    def test_iso_dates_do_not_swap_day_and_month(self):
        # Regression test: pd.to_datetime(..., dayfirst=True) can silently
        # swap day/month even on an unambiguous ISO string when both
        # components are <=12 (e.g. AI-extracted PDF dates in YYYY-MM-DD).
        df = pd.DataFrame({"Date": ["2026-03-06", "2026-01-05", "2026-12-25"]})
        df, problems = clean_dates(df)
        assert problems == 0
        assert df["Date_formatted"].tolist() == ["03/06/2026", "01/05/2026", "12/25/2026"]

    def test_legacy_dayfirst_csv_dates_still_parse_correctly(self):
        df = pd.DataFrame({"Date": ["29/11/2023", "13/02/24"]})
        df, problems = clean_dates(df)
        assert problems == 0
        assert df["Date_formatted"].tolist() == ["11/29/2023", "02/13/2024"]

    def test_invalid_dates_become_nat_and_are_counted_as_problems(self):
        df = pd.DataFrame({"Date": ["not a real date", "29/11/2023"]})
        df, problems = clean_dates(df)
        assert problems == 1


class TestMapColumnsWithAliases:
    def test_maps_known_header_aliases_onto_required_schema(self):
        df = pd.DataFrame({
            "Description": ["x"], "Amount": [1], "Transaction Date": ["1/1/24"], "Type": ["Debit"],
        })
        result_df, missing = map_columns_with_aliases(df)
        assert missing == []
        assert set(result_df.columns) == {"Date", "Details", "AmountCharged", "Debit/Credit"}

    def test_reports_columns_that_are_still_missing(self):
        df = pd.DataFrame({"SomeRandomColumn": [1]})
        _, missing = map_columns_with_aliases(df)
        assert "Date" in missing
        assert "Details" in missing

    def test_does_not_touch_columns_that_already_match(self):
        df = pd.DataFrame({"Date": ["1/1/24"], "Details": ["x"], "AmountCharged": [1], "Debit/Credit": ["Debit"]})
        result_df, missing = map_columns_with_aliases(df)
        assert missing == []
        assert list(result_df.columns) == ["Date", "Details", "AmountCharged", "Debit/Credit"]


class TestCategorizeTransactions:
    def test_matches_keyword_as_case_insensitive_substring(self):
        st.session_state.categories = {"Uncategorized": [], "Groceries": ["kroger"]}
        df = pd.DataFrame({"Details": ["KROGER STORE #123", "Random Merchant"]})
        result = categorize_transactions(df)
        assert result["Category"].tolist() == ["Groceries", "Uncategorized"]

    def test_uncategorized_keywords_are_skipped(self):
        st.session_state.categories = {"Uncategorized": ["should-be-ignored"]}
        df = pd.DataFrame({"Details": ["should-be-ignored merchant"]})
        result = categorize_transactions(df)
        assert result["Category"].tolist() == ["Uncategorized"]
