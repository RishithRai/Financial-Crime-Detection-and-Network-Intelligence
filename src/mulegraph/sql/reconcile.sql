-- %(dataset_id)s is a bound parameter, not interpolated text.
SELECT
    count(*) AS transactions,
    min(t.source_row) AS first_source_row,
    max(t.source_row) AS last_source_row,
    count(l.source_row) AS labels,
    count(*) FILTER (WHERE l.is_laundering = 1) AS laundering,
    count(*) FILTER (WHERE l.is_laundering = 0) AS legitimate,
    min(t.occurred_at)::text AS min_timestamp,
    max(t.occurred_at)::text AS max_timestamp,
    count(*) FILTER (WHERE t.raw_from_bank_id = t.raw_to_bank_id
        AND t.from_account = t.to_account) AS self_transfers,
    count(*) FILTER (WHERE t.receiving_currency <> t.payment_currency)
        AS cross_currency_rows,
    count(*) FILTER (WHERE t.receiving_currency = t.payment_currency
        AND t.amount_received <> t.amount_paid) AS same_currency_unequal_amounts,
    count(*) FILTER (WHERE (t.occurred_at < timestamp '2022-09-01'
        OR t.occurred_at >= timestamp '2022-09-11')
        AND l.is_laundering = 1) AS outside_window_laundering,
    count(*) FILTER (WHERE (t.occurred_at < timestamp '2022-09-01'
        OR t.occurred_at >= timestamp '2022-09-11')
        AND l.is_laundering = 0) AS outside_window_legitimate
FROM {core}.transactions t
LEFT JOIN {labels}.transaction_labels l USING (dataset_id, source_row)
WHERE t.dataset_id = %(dataset_id)s;
