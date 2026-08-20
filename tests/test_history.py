import pandas as pd

from history import build_history_csv, merge_with_history, read_history_file


class TestMergeWithHistory:
    def test_dedupes_on_transaction_identity_keeping_historys_category(self):
        # History rows win on duplicates so a manual category correction from
        # a prior session isn't clobbered by a fresh keyword-match re-run.
        history_df = pd.DataFrame({
            "Date": pd.to_datetime(["2024-04-01"]),
            "Details": ["Kroger Grocery"],
            "AmountCharged": [98.40],
            "Debit/Credit": ["Debit"],
            "Category": ["Groceries"],
        })
        new_df = pd.DataFrame({
            "Date": pd.to_datetime(["2024-04-01", "2024-04-02"]),
            "Details": ["Kroger Grocery", "New Merchant"],
            "AmountCharged": [98.40, 20.00],
            "Debit/Credit": ["Debit", "Debit"],
            "Category": ["Uncategorized", "Uncategorized"],
        })
        result = merge_with_history(new_df, history_df)
        assert len(result) == 2
        kroger_row = result[result["Details"] == "Kroger Grocery"].iloc[0]
        assert kroger_row["Category"] == "Groceries"

    def test_no_history_returns_new_data_unchanged(self):
        new_df = pd.DataFrame({"Details": ["x"]})
        result = merge_with_history(new_df, None)
        assert result is new_df

    def test_empty_history_returns_new_data_unchanged(self):
        new_df = pd.DataFrame({"Details": ["x"]})
        result = merge_with_history(new_df, pd.DataFrame())
        assert result is new_df

    def test_distinct_transactions_are_not_deduped(self):
        history_df = pd.DataFrame({
            "Date": pd.to_datetime(["2024-04-01"]),
            "Details": ["Kroger Grocery"],
            "AmountCharged": [98.40],
            "Debit/Credit": ["Debit"],
            "Category": ["Groceries"],
        })
        new_df = pd.DataFrame({
            "Date": pd.to_datetime(["2024-05-01"]),
            "Details": ["Kroger Grocery"],
            "AmountCharged": [110.00],
            "Debit/Credit": ["Debit"],
            "Category": ["Uncategorized"],
        })
        result = merge_with_history(new_df, history_df)
        assert len(result) == 2


class TestBuildHistoryCsv:
    def test_round_trip_produces_expected_columns_and_values(self):
        debits = pd.DataFrame({
            "Date": pd.to_datetime(["2024-04-01"]),
            "Details": ["Kroger"],
            "AmountCharged": [98.40],
            "Debit/Credit": ["Debit"],
            "Category": ["Groceries"],
        })
        credits = pd.DataFrame({
            "Date": pd.to_datetime(["2024-04-15"]),
            "Details": ["Paycheck"],
            "AmountCharged": [3000.0],
            "Debit/Credit": ["Credit"],
            "Category": ["Income"],
        })
        csv_bytes = build_history_csv(debits, credits)
        text = csv_bytes.decode("utf-8")
        assert "Kroger" in text
        assert "Paycheck" in text
        assert "2024-04-01" in text
        assert "2024-04-15" in text


class TestReadHistoryFile:
    def test_missing_required_column_is_rejected(self):
        import io
        bad_csv = io.BytesIO(b"Date,Details,AmountCharged\n2024-04-01,x,1\n")
        result = read_history_file(bad_csv)
        assert result is None

    def test_valid_history_file_round_trips_correctly(self):
        import io
        good_csv = io.BytesIO(
            b"Date,Details,AmountCharged,Debit/Credit,Category\n"
            b"2024-04-01,Kroger,98.40,debit,Groceries\n"
        )
        result = read_history_file(good_csv)
        assert result is not None
        assert result["Debit/Credit"].tolist() == ["Debit"]
        assert result["AmountCharged"].tolist() == [98.40]
