WITH splits AS (
    SELECT * FROM jsonb_to_recordset(%(splits)s::jsonb)
        AS s(split text, starts_at timestamp, ends_at timestamp)
), base AS (
    SELECT t.*, l.is_laundering, s.split,
        CASE WHEN s.split = 'stress' THEN 'stress'
             WHEN s.split IS NOT NULL THEN 'primary' ELSE 'outside' END AS period,
        (from_bank_id = to_bank_id AND from_account = to_account) AS self_transfer
    FROM {core}.transactions t
    LEFT JOIN {labels}.transaction_labels l USING (dataset_id, source_row)
    LEFT JOIN splits s ON t.occurred_at >= s.starts_at AND t.occurred_at < s.ends_at
    WHERE t.dataset_id = %(dataset_id)s
)
