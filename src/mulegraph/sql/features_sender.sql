SELECT from_bank_id, from_account, occurred_at, source_row, 'sender',
    to_bank_id, to_account, amount_paid, payment_currency,
    amount_paid, amount_received, payment_currency, receiving_currency, payment_format
FROM {core}.transactions WHERE dataset_id = %s
ORDER BY from_bank_id COLLATE "C", from_account COLLATE "C", occurred_at, source_row
