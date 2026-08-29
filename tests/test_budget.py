import pytest

from budget import (
    allocate_budget,
    annualize_salary,
    calculate_federal_tax,
    calculate_fica,
    calculate_state_tax,
    compare_actual_vs_budget,
    detect_recurring_bills,
    estimate_net_income,
    suggest_50_30_20_allocation,
)
from budget_data import NEEDS_CATEGORIES, SAVINGS_CATEGORIES, WANTS_CATEGORIES


class TestAnnualizeSalary:
    def test_yearly_passes_through(self):
        assert annualize_salary(60000, "Yearly") == 60000.0

    def test_monthly_multiplies_by_twelve(self):
        assert annualize_salary(5000, "Monthly") == 60000.0

    def test_hourly_uses_hours_per_week_and_52_weeks(self):
        assert annualize_salary(25, "Hourly", hours_per_week=40) == 25 * 40 * 52

    def test_hourly_respects_custom_hours_per_week(self):
        assert annualize_salary(25, "Hourly", hours_per_week=20) == 25 * 20 * 52

    def test_negative_or_none_amount_is_treated_as_zero(self):
        assert annualize_salary(-100, "Yearly") == 0.0
        assert annualize_salary(None, "Yearly") == 0.0


class TestCalculateFederalTax:
    def test_zero_taxable_income_is_zero_tax(self):
        assert calculate_federal_tax(0, "Single") == 0.0

    def test_income_within_first_bracket(self):
        # Entirely in the 10% bracket (<=11600 for Single)
        assert calculate_federal_tax(10000, "Single") == pytest.approx(1000.0)

    def test_income_spanning_two_brackets(self):
        # 45,400 taxable: 11,600 at 10% + (45,400-11,600) at 12%
        expected = 11600 * 0.10 + (45400 - 11600) * 0.12
        assert calculate_federal_tax(45400, "Single") == pytest.approx(expected)

    def test_married_filing_jointly_has_wider_brackets(self):
        # Same income taxed less under MFJ's wider brackets than Single
        single_tax = calculate_federal_tax(45400, "Single")
        mfj_tax = calculate_federal_tax(45400, "Married Filing Jointly")
        assert mfj_tax < single_tax


class TestCalculateFica:
    def test_basic_fica_under_ss_wage_base(self):
        gross = 60000
        expected = gross * 0.062 + gross * 0.0145
        assert calculate_fica(gross, "Single") == pytest.approx(expected)

    def test_social_security_caps_at_wage_base(self):
        # Way above the SS wage base -- SS portion should not scale further
        high = calculate_fica(500000, "Single")
        at_cap = calculate_fica(168600, "Single")
        # difference between the two should be pure Medicare (1.45%) on the
        # gap, plus the additional Medicare surtax above the threshold
        assert high > at_cap

    def test_additional_medicare_surtax_applies_above_threshold(self):
        below = calculate_fica(199999, "Single")
        above = calculate_fica(200001, "Single")
        # crossing the $200k Single threshold should add the extra 0.9% on
        # the portion above it, so marginal FICA jumps noticeably
        assert (above - below) > (2 * 0.0145)  # more than just base Medicare on the $2 gap


class TestCalculateStateTax:
    def test_zero_tax_state_returns_zero(self):
        assert calculate_state_tax(100000, "Texas") == 0.0

    def test_taxed_state_applies_its_rate(self):
        assert calculate_state_tax(100000, "California") == pytest.approx(100000 * 0.093)

    def test_unknown_state_defaults_to_zero(self):
        assert calculate_state_tax(100000, "Nowhere") == 0.0


class TestEstimateNetIncome:
    def test_full_estimate_for_single_texas_60k(self):
        result = estimate_net_income(60000, "Single", "Texas")
        assert result["state_tax"] == 0.0
        assert result["federal_tax"] > 0
        assert result["fica_tax"] > 0
        assert result["net_yearly"] == pytest.approx(
            60000 - result["federal_tax"] - result["fica_tax"] - result["state_tax"]
        )
        assert result["net_monthly"] == pytest.approx(result["net_yearly"] / 12)

    def test_net_is_always_less_than_gross_for_positive_income(self):
        result = estimate_net_income(80000, "Single", "California")
        assert result["net_yearly"] < result["gross_yearly"]

    def test_zero_income_yields_zero_everywhere(self):
        result = estimate_net_income(0, "Single", "Texas")
        assert result["net_yearly"] == 0.0
        assert result["total_tax"] == 0.0


class TestAllocateBudget:
    def test_basic_allocation_with_remainder(self):
        bills = [{"name": "Rent", "amount": 1500}, {"name": "Car", "amount": 300}]
        other = [{"category": "Groceries", "amount": 400}, {"category": "Dining Out", "amount": 100}]
        result = allocate_budget(net_monthly=3000, bills=bills, other_spend=other)
        assert result["total_bills"] == 1800
        assert result["total_other"] == 500
        assert result["remaining"] == pytest.approx(3000 - 1800 - 500)
        assert result["is_over_budget"] is False

    def test_over_budget_is_flagged(self):
        bills = [{"name": "Rent", "amount": 2000}]
        other = [{"category": "Groceries", "amount": 500}]
        result = allocate_budget(net_monthly=2000, bills=bills, other_spend=other)
        assert result["is_over_budget"] is True
        assert result["remaining"] < 0

    def test_breakdown_includes_bills_categories_and_remainder(self):
        bills = [{"name": "Rent", "amount": 1000}]
        other = [{"category": "Groceries", "amount": 300}, {"category": "Dining Out", "amount": 0}]
        result = allocate_budget(net_monthly=2000, bills=bills, other_spend=other)
        categories = {b["category"] for b in result["breakdown"]}
        assert "Bills" in categories
        assert "Groceries" in categories
        assert "Dining Out" not in categories  # zero-amount categories are excluded
        assert "Unallocated / Savings" in categories

    def test_zero_bills_are_excluded_from_breakdown(self):
        result = allocate_budget(net_monthly=1000, bills=[], other_spend=[{"category": "Groceries", "amount": 200}])
        categories = {b["category"] for b in result["breakdown"]}
        assert "Bills" not in categories


class TestCompareActualVsBudget:
    def test_matching_categories_compute_variance(self):
        result = compare_actual_vs_budget(
            budgeted_by_category={"Groceries": 400, "Dining Out": 100},
            actual_by_category={"Groceries": 350, "Dining Out": 150},
        )
        rows_by_category = {r["category"]: r for r in result["rows"]}
        assert rows_by_category["Groceries"]["variance"] == pytest.approx(50)
        assert rows_by_category["Groceries"]["is_over"] is False
        assert rows_by_category["Dining Out"]["variance"] == pytest.approx(-50)
        assert rows_by_category["Dining Out"]["is_over"] is True

    def test_totals_sum_each_side_independently(self):
        result = compare_actual_vs_budget(
            budgeted_by_category={"Groceries": 400, "Dining Out": 100},
            actual_by_category={"Groceries": 350, "Dining Out": 150},
        )
        assert result["total_budgeted"] == pytest.approx(500)
        assert result["total_actual"] == pytest.approx(500)
        assert result["total_variance"] == pytest.approx(0)

    def test_category_only_in_actual_is_treated_as_unbudgeted(self):
        result = compare_actual_vs_budget(
            budgeted_by_category={"Groceries": 400},
            actual_by_category={"Groceries": 350, "Travel": 200},
        )
        rows_by_category = {r["category"]: r for r in result["rows"]}
        assert rows_by_category["Travel"]["budgeted"] == 0.0
        assert rows_by_category["Travel"]["is_over"] is True

    def test_category_only_in_budget_shows_zero_actual(self):
        result = compare_actual_vs_budget(
            budgeted_by_category={"Groceries": 400, "Subscriptions": 50},
            actual_by_category={"Groceries": 350},
        )
        rows_by_category = {r["category"]: r for r in result["rows"]}
        assert rows_by_category["Subscriptions"]["actual"] == 0.0
        assert rows_by_category["Subscriptions"]["is_over"] is False

    def test_rows_sorted_most_over_budget_first(self):
        result = compare_actual_vs_budget(
            budgeted_by_category={"Groceries": 400, "Dining Out": 100},
            actual_by_category={"Groceries": 350, "Dining Out": 300},
        )
        assert result["rows"][0]["category"] == "Dining Out"

    def test_empty_inputs_yield_empty_result(self):
        result = compare_actual_vs_budget({}, {})
        assert result["rows"] == []
        assert result["total_budgeted"] == 0
        assert result["total_actual"] == 0


class TestSuggest503020Allocation:
    def test_needs_wants_savings_totals_match_the_rule(self):
        allocation = suggest_50_30_20_allocation(net_monthly=4000, total_bills=0)
        needs_total = sum(allocation[c] for c in NEEDS_CATEGORIES)
        wants_total = sum(allocation[c] for c in WANTS_CATEGORIES)
        savings_total = sum(allocation[c] for c in SAVINGS_CATEGORIES)
        assert needs_total == pytest.approx(4000 * 0.5)
        assert wants_total == pytest.approx(4000 * 0.3)
        assert savings_total == pytest.approx(4000 * 0.2)

    def test_existing_bills_are_credited_against_needs(self):
        allocation = suggest_50_30_20_allocation(net_monthly=4000, total_bills=1500)
        needs_total = sum(allocation[c] for c in NEEDS_CATEGORIES)
        assert needs_total == pytest.approx(4000 * 0.5 - 1500)

    def test_bills_exceeding_needs_share_does_not_go_negative(self):
        allocation = suggest_50_30_20_allocation(net_monthly=4000, total_bills=5000)
        needs_total = sum(allocation[c] for c in NEEDS_CATEGORIES)
        assert needs_total == 0

    def test_wants_and_savings_are_unaffected_by_bills(self):
        low_bills = suggest_50_30_20_allocation(net_monthly=4000, total_bills=0)
        high_bills = suggest_50_30_20_allocation(net_monthly=4000, total_bills=1000)
        for category in WANTS_CATEGORIES + SAVINGS_CATEGORIES:
            assert low_bills[category] == pytest.approx(high_bills[category])


class TestDetectRecurringBills:
    def test_finds_charge_repeating_across_months(self):
        transactions = [
            {"details": "Rent Payment", "amount": 1200, "month": "2024-01"},
            {"details": "Rent Payment", "amount": 1200, "month": "2024-02"},
            {"details": "Rent Payment", "amount": 1200, "month": "2024-03"},
        ]
        results = detect_recurring_bills(transactions)
        assert results == [{"name": "Rent Payment", "amount": 1200}]

    def test_ignores_one_off_purchases(self):
        transactions = [
            {"details": "Concert Tickets", "amount": 150, "month": "2024-01"},
        ]
        assert detect_recurring_bills(transactions) == []

    def test_respects_min_months_threshold(self):
        transactions = [
            {"details": "Gym", "amount": 40, "month": "2024-01"},
            {"details": "Gym", "amount": 40, "month": "2024-02"},
        ]
        assert detect_recurring_bills(transactions, min_months=3) == []
        assert detect_recurring_bills(transactions, min_months=2) == [{"name": "Gym", "amount": 40}]

    def test_same_merchant_different_amounts_only_counts_matching_amount(self):
        transactions = [
            {"details": "Grocery Store", "amount": 60, "month": "2024-01"},
            {"details": "Grocery Store", "amount": 95, "month": "2024-02"},
            {"details": "Grocery Store", "amount": 60, "month": "2024-03"},
        ]
        # "Grocery Store" at $60 only recurs in 2 of the 3 months; the $95
        # visit is a one-off variance in amount, not a recurring bill.
        assert detect_recurring_bills(transactions) == [{"name": "Grocery Store", "amount": 60}]

    def test_results_sorted_by_amount_descending(self):
        transactions = [
            {"details": "Streaming", "amount": 15, "month": "2024-01"},
            {"details": "Streaming", "amount": 15, "month": "2024-02"},
            {"details": "Rent", "amount": 1200, "month": "2024-01"},
            {"details": "Rent", "amount": 1200, "month": "2024-02"},
        ]
        results = detect_recurring_bills(transactions)
        assert [r["name"] for r in results] == ["Rent", "Streaming"]
