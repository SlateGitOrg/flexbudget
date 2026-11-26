-- One row per clinic, month and visit type; a missing row means zero visits.
CREATE OR REPLACE TABLE visit_grid AS
SELECT
    c.clinic_id,
    m.month,
    t.visit_type,
    COALESCE(b.visits, 0) AS budget_visits,
    COALESCE(a.visits, 0) AS actual_visits
FROM clinics AS c
CROSS JOIN (SELECT DISTINCT month FROM budget_visits) AS m
CROSS JOIN (SELECT DISTINCT visit_type FROM budget_visits) AS t
LEFT JOIN budget_visits AS b
    ON b.clinic_id = c.clinic_id AND b.month = m.month AND b.visit_type = t.visit_type
LEFT JOIN actual_visits AS a
    ON a.clinic_id = c.clinic_id AND a.month = m.month AND a.visit_type = t.visit_type;

CREATE OR REPLACE TABLE clinic_month_visits AS
SELECT
    clinic_id,
    month,
    SUM(budget_visits) AS budget_total,
    SUM(actual_visits) AS actual_total
FROM visit_grid
GROUP BY clinic_id, month;
