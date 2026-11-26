-- Exact decomposition of actual - static budget for every clinic, month and cost line.
-- Budgets are rounded to cents first and the parts are differences of the rounded figures, so
--   volume + mix + spending = actual - static
-- holds to the cent with no residual bucket. Fixed lines carry spending variance only.
-- Clinical labour spending is split: wage rate = payroll - actual hours x standard rate, and
-- efficiency = standard rate x (actual hours - standard hours for actual visits), which is the
-- remainder of the labour spending variance to the nearest cent.
CREATE OR REPLACE TABLE variance AS
WITH budgets AS (
    SELECT clinic_id, month, line,
           static_raw, flexed_raw, flexed_mix_raw, std_hours_actual
    FROM variable_budgets
    UNION ALL
    SELECT clinic_id, month, line, amount, amount, amount, 0.0
    FROM fixed_budget
),
rounded AS (
    SELECT
        b.clinic_id,
        b.month,
        b.line,
        ROUND(b.static_raw, 2) AS static_budget,
        ROUND(b.flexed_raw, 2) AS flexed_budget,
        ROUND(b.flexed_mix_raw, 2) AS flexed_budget_actual_mix,
        COALESCE(c.amount, 0.0) AS actual_cost,
        h.hours AS actual_hours
    FROM budgets AS b
    LEFT JOIN actual_cost AS c
        ON c.clinic_id = b.clinic_id AND c.month = b.month AND c.line = b.line
    LEFT JOIN actual_hours AS h
        ON h.clinic_id = b.clinic_id AND h.month = b.month AND b.line = 'clinical_labour'
),
parts AS (
    SELECT
        *,
        ROUND(flexed_budget - static_budget, 2) AS volume_variance,
        ROUND(flexed_budget_actual_mix - flexed_budget, 2) AS mix_variance,
        ROUND(actual_cost - flexed_budget_actual_mix, 2) AS spending_variance,
        ROUND(actual_cost - static_budget, 2) AS total_variance
    FROM rounded
)
SELECT
    p.clinic_id,
    p.month,
    p.line,
    p.static_budget,
    p.flexed_budget,
    p.flexed_budget_actual_mix,
    p.actual_cost,
    p.actual_hours,
    p.volume_variance,
    p.mix_variance,
    p.spending_variance,
    CASE WHEN p.line = 'clinical_labour'
         THEN ROUND(p.actual_cost - p.actual_hours * w.rate, 2) END AS wage_rate_variance,
    CASE WHEN p.line = 'clinical_labour'
         THEN ROUND(p.spending_variance - ROUND(p.actual_cost - p.actual_hours * w.rate, 2), 2)
    END AS efficiency_variance,
    p.total_variance,
    CASE WHEN p.flexed_budget = 0 THEN NULL
         ELSE p.total_variance / p.flexed_budget END AS variance_pct
FROM parts AS p
CROSS JOIN std_wage AS w
ORDER BY p.clinic_id, p.month, p.line;
