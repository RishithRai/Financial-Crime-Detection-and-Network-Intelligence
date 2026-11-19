CREATE TEMP TABLE stage_accounts (
    source_row bigint PRIMARY KEY,
    bank_name text, raw_bank_id text, account_number text,
    entity_id text, entity_name text
) ON COMMIT DROP;
CREATE TEMP TABLE stage_transactions (
    source_row bigint,
    occurred_at text, raw_from_bank_id text, from_account text,
    raw_to_bank_id text, to_account text, amount_received text,
    receiving_currency text, amount_paid text, payment_currency text,
    payment_format text, is_laundering text, source_record_sha256 bytea
) ON COMMIT DROP;
