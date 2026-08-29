import budget_state
from budget_state import load_budget_state, save_budget_state


class TestBudgetStatePersistence:
    def test_returns_empty_dict_when_nothing_saved_yet(self, tmp_path, monkeypatch):
        isolated_file = tmp_path / "budget_state.json"
        monkeypatch.setattr(budget_state, "BUDGET_STATE_FILE", str(isolated_file))

        assert load_budget_state() == {}

    def test_round_trips_saved_state(self, tmp_path, monkeypatch):
        isolated_file = tmp_path / "budget_state.json"
        monkeypatch.setattr(budget_state, "BUDGET_STATE_FILE", str(isolated_file))
        state = {
            "pay_type": "Yearly",
            "amount": 75000,
            "state": "Texas",
            "filing_status": "Single",
            "bills": [{"Bill": "Rent/Mortgage", "Amount": 1500.0}],
            "other_spend": [{"Category": "Groceries", "Amount": 400.0}],
        }

        save_budget_state(state)

        assert isolated_file.exists()
        assert load_budget_state() == state

    def test_corrupt_file_falls_back_to_empty_dict(self, tmp_path, monkeypatch):
        isolated_file = tmp_path / "budget_state.json"
        isolated_file.write_text("not valid json{")
        monkeypatch.setattr(budget_state, "BUDGET_STATE_FILE", str(isolated_file))

        assert load_budget_state() == {}
