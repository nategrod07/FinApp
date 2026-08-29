"""Budget planning: estimated take-home pay and category-based budget allocation.

Pure calculation functions, no Streamlit dependency, so they're easy to unit test
and reuse. See budget_data.py for the approximation caveats on the tax figures.
"""

from collections import defaultdict

from budget_data import (
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD,
    FEDERAL_BRACKETS_2024,
    MEDICARE_RATE,
    NEEDS_CATEGORIES,
    SAVINGS_CATEGORIES,
    SOCIAL_SECURITY_RATE,
    SOCIAL_SECURITY_WAGE_BASE_2024,
    STANDARD_DEDUCTION_2024,
    STATE_TAX_RATES,
    WANTS_CATEGORIES,
)


def annualize_salary(amount, pay_type, hours_per_week=40):
    """Convert an hourly/monthly/yearly salary input into an estimated yearly gross."""
    if amount is None or amount < 0:
        return 0.0
    if pay_type == "Hourly":
        return amount * hours_per_week * 52
    if pay_type == "Monthly":
        return amount * 12
    return float(amount)


def calculate_federal_tax(taxable_income, filing_status):
    """Progressive federal tax across brackets. taxable_income should already
    have the standard deduction subtracted."""
    brackets = FEDERAL_BRACKETS_2024[filing_status]
    tax = 0.0
    previous_cap = 0
    for cap, rate in brackets:
        if taxable_income <= previous_cap:
            break
        taxable_in_bracket = min(taxable_income, cap) - previous_cap
        tax += taxable_in_bracket * rate
        previous_cap = cap
    return tax


def calculate_fica(gross_yearly, filing_status):
    """Social Security (capped at the wage base) + Medicare (plus the additional
    0.9% surtax above the filing-status threshold)."""
    social_security = min(gross_yearly, SOCIAL_SECURITY_WAGE_BASE_2024) * SOCIAL_SECURITY_RATE
    medicare = gross_yearly * MEDICARE_RATE
    threshold = ADDITIONAL_MEDICARE_THRESHOLD.get(filing_status, ADDITIONAL_MEDICARE_THRESHOLD["Single"])
    if gross_yearly > threshold:
        medicare += (gross_yearly - threshold) * ADDITIONAL_MEDICARE_RATE
    return social_security + medicare


def calculate_state_tax(gross_yearly, state):
    return gross_yearly * STATE_TAX_RATES.get(state, 0.0)


def estimate_net_income(gross_yearly, filing_status, state):
    """Estimate take-home pay after federal, state, and FICA taxes."""
    standard_deduction = STANDARD_DEDUCTION_2024[filing_status]
    taxable_income = max(0.0, gross_yearly - standard_deduction)
    federal_tax = calculate_federal_tax(taxable_income, filing_status)
    state_tax = calculate_state_tax(gross_yearly, state)
    fica_tax = calculate_fica(gross_yearly, filing_status)
    total_tax = federal_tax + state_tax + fica_tax
    net_yearly = gross_yearly - total_tax
    return {
        "gross_yearly": gross_yearly,
        "federal_tax": federal_tax,
        "state_tax": state_tax,
        "fica_tax": fica_tax,
        "total_tax": total_tax,
        "net_yearly": net_yearly,
        "net_monthly": net_yearly / 12,
    }


def allocate_budget(net_monthly, bills, other_spend):
    """bills / other_spend: lists of {"name"/"category": str, "amount": float}.
    Returns totals plus a per-category breakdown suitable for a pie chart.
    """
    total_bills = sum(b["amount"] for b in bills if b["amount"] > 0)
    total_other = sum(o["amount"] for o in other_spend if o["amount"] > 0)
    total_allocated = total_bills + total_other
    remaining = net_monthly - total_allocated

    breakdown = []
    if total_bills > 0:
        breakdown.append({"category": "Bills", "amount": total_bills})
    for item in other_spend:
        if item["amount"] > 0:
            breakdown.append({"category": item["category"], "amount": item["amount"]})
    if remaining > 0:
        breakdown.append({"category": "Unallocated / Savings", "amount": remaining})

    return {
        "net_monthly": net_monthly,
        "total_bills": total_bills,
        "total_other": total_other,
        "total_allocated": total_allocated,
        "remaining": remaining,
        "is_over_budget": remaining < 0,
        "breakdown": breakdown,
    }


def compare_actual_vs_budget(budgeted_by_category, actual_by_category):
    """Compare planned spending against real transaction totals, category by category.

    budgeted_by_category / actual_by_category: dicts of {category: amount}. Categories
    that only appear on one side are treated as zero on the other, so an outer join
    of the two dicts' keys is used -- this also surfaces spending in categories that
    were never budgeted for at all.
    """
    categories = set(budgeted_by_category) | set(actual_by_category)
    rows = []
    for category in categories:
        budgeted = budgeted_by_category.get(category, 0.0)
        actual = actual_by_category.get(category, 0.0)
        variance = budgeted - actual
        rows.append({
            "category": category,
            "budgeted": budgeted,
            "actual": actual,
            "variance": variance,
            "is_over": variance < 0,
        })
    rows.sort(key=lambda r: r["variance"])

    total_budgeted = sum(budgeted_by_category.values())
    total_actual = sum(actual_by_category.values())
    return {
        "rows": rows,
        "total_budgeted": total_budgeted,
        "total_actual": total_actual,
        "total_variance": total_budgeted - total_actual,
    }


def suggest_50_30_20_allocation(net_monthly, total_bills):
    """Suggest an "Other Spending" split following the 50/30/20 rule (50% needs,
    30% wants, 20% savings). Bills already cover most of "needs" (rent,
    utilities, insurance), so total_bills is credited against the needs share
    first -- otherwise the preset would double-count them. Each bucket is
    split evenly across its categories; returns {category: amount} for every
    category in NEEDS/WANTS/SAVINGS_CATEGORIES.
    """
    needs_remaining = max(0.0, net_monthly * 0.5 - total_bills)
    wants_total = net_monthly * 0.3
    savings_total = net_monthly * 0.2

    allocation = {}
    for category in NEEDS_CATEGORIES:
        allocation[category] = needs_remaining / len(NEEDS_CATEGORIES)
    for category in WANTS_CATEGORIES:
        allocation[category] = wants_total / len(WANTS_CATEGORIES)
    for category in SAVINGS_CATEGORIES:
        allocation[category] = savings_total / len(SAVINGS_CATEGORIES)
    return allocation


def detect_recurring_bills(transactions, min_months=2):
    """Find likely recurring bills (rent, subscriptions, insurance) in a
    transaction history.

    transactions: list of {"details": str, "amount": float, "month": str}.
    Groups by (details, amount rounded to the nearest dollar) -- a bill that
    charges the same merchant the same amount across at least `min_months`
    distinct months is a strong recurrence signal, unlike one-off purchases
    that happen to share a merchant. Returns [{"name", "amount"}] sorted by
    amount descending, so the biggest recurring bills surface first.
    """
    groups = defaultdict(set)
    amounts = {}
    for t in transactions:
        key = (t["details"], round(t["amount"]))
        groups[key].add(t["month"])
        amounts[key] = t["amount"]

    results = [
        {"name": details, "amount": amounts[(details, rounded_amount)]}
        for (details, rounded_amount), months in groups.items()
        if len(months) >= min_months
    ]
    results.sort(key=lambda r: r["amount"], reverse=True)
    return results
