"""Reference data for budget tax estimation: brackets, deductions, state rates.

These are APPROXIMATIONS for budgeting purposes, not tax advice. Federal brackets
and the standard deduction are 2024 figures (the most recent this data is confident
in) -- rates shift slightly most years for inflation, so treat this as a ballpark,
not a paystub replacement. State income tax is simplified to a single blended
effective rate per state rather than full bracket/deduction structures, since
building and maintaining 50 accurate bracket tables is a much bigger undertaking
than a budgeting tool needs; a few states also have local/county income taxes on
top of the state rate that aren't modeled here at all.
"""

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
]

FILING_STATUSES = ["Single", "Married Filing Jointly", "Married Filing Separately", "Head of Household"]

# 2024 federal tax brackets: list of (bracket upper bound, marginal rate),
# applied progressively. The last bracket's bound is infinite.
FEDERAL_BRACKETS_2024 = {
    "Single": [
        (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
        (243725, 0.32), (609350, 0.35), (float("inf"), 0.37),
    ],
    "Married Filing Jointly": [
        (23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
        (487450, 0.32), (731200, 0.35), (float("inf"), 0.37),
    ],
    "Married Filing Separately": [
        (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
        (243725, 0.32), (365600, 0.35), (float("inf"), 0.37),
    ],
    "Head of Household": [
        (16550, 0.10), (63100, 0.12), (100500, 0.22), (191950, 0.24),
        (243700, 0.32), (609350, 0.35), (float("inf"), 0.37),
    ],
}

STANDARD_DEDUCTION_2024 = {
    "Single": 14600,
    "Married Filing Jointly": 29200,
    "Married Filing Separately": 14600,
    "Head of Household": 21900,
}

SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE_2024 = 168600
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD = {
    "Single": 200000,
    "Married Filing Jointly": 250000,
    "Married Filing Separately": 125000,
    "Head of Household": 200000,
}

# Simplified, approximate blended effective state income tax rates -- not full
# bracket tables. 0.0 for the nine states with no wage income tax.
STATE_TAX_RATES = {
    "Alabama": 0.05, "Alaska": 0.0, "Arizona": 0.025, "Arkansas": 0.044,
    "California": 0.093, "Colorado": 0.044, "Connecticut": 0.0699,
    "Delaware": 0.066, "District of Columbia": 0.0895, "Florida": 0.0,
    "Georgia": 0.0539, "Hawaii": 0.079, "Idaho": 0.058, "Illinois": 0.0495,
    "Indiana": 0.0305, "Iowa": 0.038, "Kansas": 0.057, "Kentucky": 0.04,
    "Louisiana": 0.03, "Maine": 0.0715, "Maryland": 0.0575,
    "Massachusetts": 0.05, "Michigan": 0.0425, "Minnesota": 0.0785,
    "Mississippi": 0.044, "Missouri": 0.0495, "Montana": 0.059,
    "Nebraska": 0.0584, "Nevada": 0.0, "New Hampshire": 0.0,
    "New Jersey": 0.0637, "New Mexico": 0.049, "New York": 0.0685,
    "North Carolina": 0.045, "North Dakota": 0.025, "Ohio": 0.035,
    "Oklahoma": 0.0475, "Oregon": 0.0875, "Pennsylvania": 0.0307,
    "Rhode Island": 0.0599, "South Carolina": 0.062, "South Dakota": 0.0,
    "Tennessee": 0.0, "Texas": 0.0, "Utah": 0.0465, "Vermont": 0.066,
    "Virginia": 0.0575, "Washington": 0.0, "West Virginia": 0.0482,
    "Wisconsin": 0.0465, "Wyoming": 0.0,
}

# Predesignated common expenditure categories for the "other spend" input --
# deliberately a fixed list (not free-form) per the feature's own design.
COMMON_EXPENSE_CATEGORIES = [
    "Groceries", "Dining Out", "Transportation/Gas", "Entertainment",
    "Subscriptions", "Personal Care", "Shopping", "Fitness/Health",
    "Savings/Investing", "Miscellaneous",
]
