-- name: totals
SELECT count(*) AS transactions, count(is_laundering) AS labels,
    count(*) FILTER (WHERE split IS NULL) AS outside_splits,
    min(occurred_at) AS first_timestamp, max(occurred_at) AS last_timestamp
FROM base;
-- name: splits
SELECT s.split, s.starts_at, s.ends_at, count(b.source_row) AS transactions,
    count(*) FILTER (WHERE is_laundering = 1) AS positives,
    count(*) FILTER (WHERE is_laundering = 0) AS negatives
FROM splits s LEFT JOIN base b ON b.split = s.split
GROUP BY s.split, s.starts_at, s.ends_at ORDER BY s.starts_at;
-- name: daily
SELECT occurred_at::date AS day, period, count(*) AS transactions,
    sum(is_laundering) AS positives,
    count(*) FILTER (WHERE self_transfer) AS self_transfers,
    count(*) FILTER (WHERE receiving_currency <> payment_currency) AS cross_currency
FROM base GROUP BY day, period ORDER BY day;
-- name: categories
SELECT period, is_laundering, category, value, count(*) AS transactions
FROM base CROSS JOIN LATERAL (VALUES
    ('payment_format', payment_format),
    ('receiving_currency', receiving_currency),
    ('payment_currency', payment_currency),
    ('self_transfer', self_transfer::text),
    ('cross_currency', (receiving_currency <> payment_currency)::text)
) AS c(category, value)
GROUP BY period, is_laundering, category, value
ORDER BY category, value, period, is_laundering;
-- name: amounts
SELECT period, is_laundering, side, currency, count(*) AS transactions,
    min(amount) AS minimum, percentile_disc(0.5) WITHIN GROUP (ORDER BY amount) AS p50,
    percentile_disc(0.9) WITHIN GROUP (ORDER BY amount) AS p90,
    percentile_disc(0.99) WITHIN GROUP (ORDER BY amount) AS p99,
    max(amount) AS maximum, sum(amount) AS total
FROM base CROSS JOIN LATERAL (VALUES
    ('paid', payment_currency, amount_paid),
    ('received', receiving_currency, amount_received)
) AS a(side, currency, amount)
GROUP BY period, is_laundering, side, currency
ORDER BY side, currency, period, is_laundering;
-- name: hours
SELECT period, is_laundering, extract(hour FROM occurred_at)::int AS hour,
    count(*) AS transactions
FROM base GROUP BY period, is_laundering, hour ORDER BY period, is_laundering, hour;
-- name: ties
SELECT period, count(*) AS distinct_timestamps, max(n) AS largest_group,
    count(*) FILTER (WHERE n > 1) AS tied_timestamps,
    coalesce(sum(n) FILTER (WHERE n > 1), 0) AS transactions_in_ties
FROM (SELECT period, occurred_at, count(*) AS n FROM base
      GROUP BY period, occurred_at) t GROUP BY period ORDER BY period;
-- name: activity
, endpoints AS (
    SELECT split, from_bank_id AS bank_id, from_account AS account_number,
        source_row, occurred_at, is_laundering, 1 AS sent, 0 AS received FROM base
    UNION ALL
    SELECT split, to_bank_id, to_account, source_row, occurred_at,
        is_laundering, 0, 1 FROM base
), active AS (
    SELECT split, bank_id, account_number,
        count(DISTINCT source_row) AS transactions,
        sum(sent) AS sent, sum(received) AS received,
        max(is_laundering) AS touches_positive
    FROM endpoints GROUP BY split, bank_id, account_number
), first_seen AS (
    SELECT bank_id, account_number, min(occurred_at) AS first_seen
    FROM endpoints GROUP BY bank_id, account_number
)
SELECT s.split, count(*) AS active_accounts, sum(touches_positive) AS touches_positive,
    count(*) FILTER (WHERE f.first_seen >= s.starts_at) AS newly_observed_accounts,
    count(*) FILTER (WHERE sent > 0) AS senders,
    count(*) FILTER (WHERE received > 0) AS receivers,
    min(transactions) AS minimum,
    percentile_disc(0.5) WITHIN GROUP (ORDER BY transactions) AS p50,
    percentile_disc(0.9) WITHIN GROUP (ORDER BY transactions) AS p90,
    percentile_disc(0.99) WITHIN GROUP (ORDER BY transactions) AS p99,
    max(transactions) AS maximum
FROM active a JOIN splits s USING (split)
JOIN first_seen f USING (bank_id, account_number)
GROUP BY s.split, s.starts_at ORDER BY s.starts_at;
