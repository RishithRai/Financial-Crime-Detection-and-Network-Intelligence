-- Schema version 1. Identifiers are substituted with psycopg.sql.Identifier.
CREATE SCHEMA IF NOT EXISTS {core};
CREATE SCHEMA IF NOT EXISTS {labels};
REVOKE ALL ON SCHEMA {labels} FROM PUBLIC;

CREATE TABLE {core}.schema_version (
    version integer PRIMARY KEY CHECK (version = 1),
    definition_sha256 text NOT NULL
);

-- ASCII digits only; no integer cast, truncation, or account normalization.
CREATE FUNCTION {core}.normalize_bank_id(raw text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT CASE WHEN raw ~ '^[0-9]+$'
        THEN coalesce(nullif(ltrim(raw, '0'), ''), '0') END
$$;

CREATE TABLE {core}.datasets (
    dataset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_key text NOT NULL UNIQUE,
    fingerprint text NOT NULL UNIQUE CHECK (fingerprint ~ '^[0-9a-f]{{64}}$'),
    normalization_version text NOT NULL CHECK (normalization_version = 'bank-padding-v1'),
    status text NOT NULL CHECK (status IN ('loading', 'complete')),
    provenance jsonb NOT NULL,
    validation jsonb NOT NULL,
    reconciliation jsonb,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CHECK ((status = 'complete') = (completed_at IS NOT NULL))
);

CREATE TABLE {core}.source_files (
    dataset_id bigint NOT NULL REFERENCES {core}.datasets,
    file_name text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    source_url text NOT NULL,
    PRIMARY KEY (dataset_id, file_name)
);

CREATE TABLE {core}.banks (
    dataset_id bigint NOT NULL REFERENCES {core}.datasets,
    bank_id text NOT NULL CHECK (bank_id ~ '^(0|[1-9][0-9]*)$'),
    bank_name text NOT NULL CHECK (btrim(bank_name) <> ''),
    PRIMARY KEY (dataset_id, bank_id)
);

CREATE TABLE {core}.entities (
    dataset_id bigint NOT NULL REFERENCES {core}.datasets,
    entity_id text NOT NULL CHECK (btrim(entity_id) <> ''),
    entity_name text NOT NULL CHECK (btrim(entity_name) <> ''),
    PRIMARY KEY (dataset_id, entity_id)
);

CREATE TABLE {core}.accounts (
    dataset_id bigint NOT NULL REFERENCES {core}.datasets,
    source_row bigint NOT NULL CHECK (source_row > 0),
    raw_bank_id text NOT NULL,
    bank_id text GENERATED ALWAYS AS ({core}.normalize_bank_id(raw_bank_id)) STORED NOT NULL,
    account_number text NOT NULL CHECK (
        account_number <> '' AND account_number = btrim(account_number)),
    entity_id text NOT NULL,
    PRIMARY KEY (dataset_id, source_row),
    UNIQUE (dataset_id, bank_id, account_number),
    FOREIGN KEY (dataset_id, bank_id) REFERENCES {core}.banks,
    FOREIGN KEY (dataset_id, entity_id) REFERENCES {core}.entities
);

CREATE TABLE {core}.transactions (
    dataset_id bigint NOT NULL REFERENCES {core}.datasets,
    source_row bigint NOT NULL CHECK (source_row > 0),
    occurred_at timestamp without time zone NOT NULL CHECK (isfinite(occurred_at)),
    raw_from_bank_id text NOT NULL,
    from_bank_id text GENERATED ALWAYS AS
        ({core}.normalize_bank_id(raw_from_bank_id)) STORED NOT NULL,
    from_account text NOT NULL,
    raw_to_bank_id text NOT NULL,
    to_bank_id text GENERATED ALWAYS AS
        ({core}.normalize_bank_id(raw_to_bank_id)) STORED NOT NULL,
    to_account text NOT NULL,
    amount_received numeric NOT NULL CHECK (
        amount_received >= 0 AND amount_received < 'Infinity'::numeric),
    receiving_currency text NOT NULL CHECK (btrim(receiving_currency) <> ''),
    amount_paid numeric NOT NULL CHECK (
        amount_paid >= 0 AND amount_paid < 'Infinity'::numeric),
    payment_currency text NOT NULL CHECK (btrim(payment_currency) <> ''),
    payment_format text NOT NULL CHECK (btrim(payment_format) <> ''),
    PRIMARY KEY (dataset_id, source_row),
    FOREIGN KEY (dataset_id, from_bank_id, from_account)
        REFERENCES {core}.accounts (dataset_id, bank_id, account_number),
    FOREIGN KEY (dataset_id, to_bank_id, to_account)
        REFERENCES {core}.accounts (dataset_id, bank_id, account_number)
);

CREATE TABLE {labels}.transaction_labels (
    dataset_id bigint NOT NULL,
    source_row bigint NOT NULL,
    is_laundering smallint NOT NULL CHECK (is_laundering IN (0, 1)),
    -- Includes the label, so the full-source-row digest is isolated here too.
    source_record_sha256 bytea NOT NULL CHECK (octet_length(source_record_sha256) = 32),
    PRIMARY KEY (dataset_id, source_row),
    FOREIGN KEY (dataset_id, source_row) REFERENCES {core}.transactions
);
REVOKE ALL ON ALL TABLES IN SCHEMA {labels} FROM PUBLIC;
