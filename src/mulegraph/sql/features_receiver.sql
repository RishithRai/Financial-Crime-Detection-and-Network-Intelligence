SELECT to_bank_id, to_account, occurred_at, source_row, 'receiver',
    from_bank_id, from_account, amount_received, receiving_currency,
    NULL::numeric, NULL::numeric, NULL::text, NULL::text, NULL::text
FROM {core}.transactions WHERE dataset_id = %s
ORDER BY to_bank_id COLLATE "C", to_account COLLATE "C", occurred_at, source_row
