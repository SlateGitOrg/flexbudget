-- Standard cost of one visit, by variable line and visit type.
-- Supplies and lab send-outs carry a USD-per-visit standard. Clinical labour is priced as
-- standard hours per visit x the network standard wage rate, and keeps the hours for the
-- efficiency split.
CREATE OR REPLACE TABLE std_unit_cost AS
SELECT line, visit_type, value AS unit_cost, CAST(NULL AS DOUBLE) AS std_hours
FROM standards
WHERE driver = 'usd_per_visit'
UNION ALL
SELECT h.line, h.visit_type, h.value * w.value AS unit_cost, h.value AS std_hours
FROM standards AS h
CROSS JOIN (SELECT value FROM standards WHERE driver = 'usd_per_hour') AS w
WHERE h.driver = 'hours_per_visit';

CREATE OR REPLACE TABLE std_wage AS
SELECT value AS rate FROM standards WHERE driver = 'usd_per_hour';
