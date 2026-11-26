-- Static and flexed budgets for the variable lines, before rounding to cents.
--   static      = budgeted visits by type x standard cost
--   flexed      = actual total visits x budgeted mix x standard cost
--   flexed_mix  = actual visits by type x standard cost
-- A clinic with no actual visits has a flexed budget of exactly zero.
CREATE OR REPLACE TABLE variable_budgets AS
SELECT
    g.clinic_id,
    g.month,
    u.line,
    SUM(g.budget_visits * u.unit_cost) AS static_raw,
    SUM(
        CASE WHEN v.budget_total = 0 THEN 0.0
             ELSE v.actual_total * (g.budget_visits * 1.0 / v.budget_total) * u.unit_cost
        END
    ) AS flexed_raw,
    SUM(g.actual_visits * u.unit_cost) AS flexed_mix_raw,
    SUM(g.actual_visits * COALESCE(u.std_hours, 0.0)) AS std_hours_actual
FROM visit_grid AS g
INNER JOIN clinic_month_visits AS v USING (clinic_id, month)
INNER JOIN std_unit_cost AS u USING (visit_type)
GROUP BY g.clinic_id, g.month, u.line;
