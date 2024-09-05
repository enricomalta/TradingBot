CREATE VIEW IF NOT EXISTS profit_percentages AS
WITH DateDiffs AS (
    SELECT 
        id,
        date_buy,
        date_sell,
        strftime('%Y-%m-%d', date_sell) AS formatted_date_sell,
        strftime('%Y-%m-%d', date_buy) AS formatted_date_buy,
        (julianday(date_sell) - julianday(date_buy)) AS days_difference,
        profit
    FROM orders
    WHERE date_sell IS NOT NULL
),
AggregatedData AS (
    SELECT
        'Monthly' AS period,
        strftime('%Y-%m', formatted_date_sell) AS period_date,
        SUM(profit) AS total_profit
    FROM DateDiffs
    GROUP BY strftime('%Y-%m', formatted_date_sell)

    UNION ALL

    SELECT
        'Yearly' AS period,
        strftime('%Y', formatted_date_sell) AS period_date,
        SUM(profit) AS total_profit
    FROM DateDiffs
    GROUP BY strftime('%Y', formatted_date_sell)
)
SELECT 
    period,
    period_date,
    total_profit
FROM AggregatedData
ORDER BY period, period_date;
