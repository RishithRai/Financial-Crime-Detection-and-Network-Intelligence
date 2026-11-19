CREATE INDEX IF NOT EXISTS accounts_entity_idx
    ON {core}.accounts (dataset_id, entity_id);
CREATE INDEX IF NOT EXISTS transactions_sender_time_idx
    ON {core}.transactions (dataset_id, from_bank_id, from_account, occurred_at);
CREATE INDEX IF NOT EXISTS transactions_receiver_time_idx
    ON {core}.transactions (dataset_id, to_bank_id, to_account, occurred_at);
CREATE INDEX IF NOT EXISTS transactions_time_idx
    ON {core}.transactions USING brin (occurred_at);
