"""Fixed rules using current attributes and strictly prior account history."""

from decimal import Decimal, localcontext

import duckdb
import pyarrow as pa

VERSION = "rules-v1"
MIN_CURRENCY_ROWS = 1000
MIN_HISTORY = 5
AMOUNT_MULTIPLIER = 10
SURGE_MULTIPLIER = 5
MIN_HOURLY = 5
MIN_DIRECTION_HISTORY = 10
WARMUP_SECONDS = 86400
ALERT_CAP = 0.01
TIE_SALT = "mulegraph-rules-v1-budget-ties"

REASONS = {
    "SENDER_AMOUNT_SPIKE": (
        "Paid amount exceeds 10× the prior same-currency mean and training p95"
    ),
    "RECEIVER_AMOUNT_SPIKE": (
        "Received amount exceeds 10× the prior same-currency mean and training p95"
    ),
    "SENDER_FREQUENCY_SURGE": (
        "Sender's prior-hour activity exceeds 5× its prior-23-hour hourly rate"
    ),
    "RECEIVER_FREQUENCY_SURGE": (
        "Receiver's prior-hour activity exceeds 5× its prior-23-hour hourly rate"
    ),
    "SENDER_HIGH_ACTIVITY": (
        "Sender's prior-day activity exceeds its training reference cutoff"
    ),
    "RECEIVER_HIGH_ACTIVITY": (
        "Receiver's prior-day activity exceeds its training reference cutoff"
    ),
    "SENDER_DIRECTION_CHANGE": (
        "Historically receiving account now sends a training-p95 amount"
    ),
    "RECEIVER_DIRECTION_CHANGE": (
        "Historically sending account now receives a training-p95 amount"
    ),
}
WEIGHTS = {code: 2 if "AMOUNT_SPIKE" in code else 1 for code in REASONS}
MAX_SCORE = sum(WEIGHTS.values())


def profile_training(connection: duckdb.DuckDBPyConnection) -> dict:
    """Only the train partition determines distributional reference levels."""
    currencies = []
    activity = {}
    for role, column in (("sender", "paid"), ("receiver", "received")):
        currency = "payment_currency" if role == "sender" else "receiving_currency"
        rows = connection.execute(f"""
            SELECT {currency}, count(*), quantile_disc(amount_{column}, .95),
                   quantile_disc(amount_{column}, .995)
            FROM features WHERE split='train' GROUP BY {currency} ORDER BY {currency}
        """).fetchall()
        currencies += [
            {
                "role": role,
                "currency": name,
                "observations": n,
                "p95": str(q95),
                "p995": str(q995),
                "supported": n >= MIN_CURRENCY_ROWS,
            }
            for name, n, q95, q995 in rows
        ]
        n, cutoff = connection.execute(f"""
            SELECT count(*), quantile_disc({role}_count_24h, .99)
            FROM features WHERE split='train' AND {role}_history_age_seconds >= 86400
        """).fetchone()
        activity[role] = {"eligible_training_rows": n, "cutoff": max(20, cutoff or 0)}
    if not currencies:
        raise ValueError("No training observations")
    return {"currencies": currencies, "activity": activity}


def score_row(row: dict, profile: dict) -> dict:
    """Small pure reference implementation used for rule and leakage tests."""
    triggers = {}
    with localcontext() as context:
        context.prec = 60
        for role, amount_name, currency_name in (
            ("sender", "amount_paid", "payment_currency"),
            ("receiver", "amount_received", "receiving_currency"),
        ):
            ref = next(
                (
                    p
                    for p in profile["currencies"]
                    if p["role"] == role
                    and p["currency"] == row[currency_name]
                    and p["supported"]
                ),
                None,
            )
            amount = Decimal(row[amount_name])
            n = row[f"{role}_currency_history_count"]
            total = Decimal(row[f"{role}_currency_history_sum"])
            age = row[f"{role}_history_age_seconds"]
            mature = age is not None and age >= WARMUP_SECONDS
            hour, day = row[f"{role}_count_1h"], row[f"{role}_count_24h"]
            sent, received = row[f"{role}_sent_count"], row[f"{role}_received_count"]
            high_amount = ref is not None and amount > Decimal(ref["p95"])
            triggers[f"{role.upper()}_AMOUNT_SPIKE"] = bool(
                high_amount
                and n >= MIN_HISTORY
                and total > 0
                and amount * n > AMOUNT_MULTIPLIER * total
            )
            triggers[f"{role.upper()}_FREQUENCY_SURGE"] = bool(
                mature
                and hour >= MIN_HOURLY
                and hour * 23 > SURGE_MULTIPLIER * (day - hour)
            )
            triggers[f"{role.upper()}_HIGH_ACTIVITY"] = bool(
                mature and day > profile["activity"][role]["cutoff"]
            )
            changed = (
                sent <= 1 and received >= MIN_DIRECTION_HISTORY
                if role == "sender"
                else received <= 1 and sent >= MIN_DIRECTION_HISTORY
            )
            triggers[f"{role.upper()}_DIRECTION_CHANGE"] = bool(
                mature and high_amount and changed
            )
    ordered = [code for code in REASONS if triggers[code]]
    return {
        "risk_score": sum(WEIGHTS[c] for c in ordered),
        "reason_codes": ordered,
        **triggers,
    }


def scoring_sql(profile: dict) -> str:
    """SQL equivalent of score_row; profile tables contain training references only."""
    predicates = {}
    flags = []
    for role, amount, alias in (
        ("sender", "amount_paid", "ps"),
        ("receiver", "amount_received", "pr"),
    ):
        high = f"{alias}.supported AND {amount} > {alias}.p95"
        mature = f"{role}_history_age_seconds >= {WARMUP_SECONDS}"
        predicates[f"{role.upper()}_AMOUNT_SPIKE"] = (
            f"{high} AND {role}_currency_history_count >= {MIN_HISTORY} "
            f"AND {role}_currency_history_sum > 0 AND "
            f"{amount} * {role}_currency_history_count > "
            f"{AMOUNT_MULTIPLIER} * {role}_currency_history_sum"
        )
        predicates[f"{role.upper()}_FREQUENCY_SURGE"] = (
            f"{mature} AND {role}_count_1h >= {MIN_HOURLY} AND "
            f"{role}_count_1h * 23 > {SURGE_MULTIPLIER} * "
            f"({role}_count_24h - {role}_count_1h)"
        )
        cutoff = int(profile["activity"][role]["cutoff"])
        predicates[f"{role.upper()}_HIGH_ACTIVITY"] = (
            f"{mature} AND {role}_count_24h > {cutoff}"
        )
        old, new = ("received", "sent") if role == "sender" else ("sent", "received")
        predicates[f"{role.upper()}_DIRECTION_CHANGE"] = (
            f"{mature} AND {high} AND {role}_{new}_count <= 1 "
            f"AND {role}_{old}_count >= {MIN_DIRECTION_HISTORY}"
        )
        flags += [
            f"{role}_currency_history_count < {MIN_HISTORY} "
            f"AS {role}_limited_currency_history",
            f"NOT coalesce({alias}.supported, false) AS {role}_unsupported_currency",
        ]
    selected = [f"coalesce(({predicates[code]}), false) AS {code}" for code in REASONS]
    score = " + ".join(f"{code}::INTEGER * {WEIGHTS[code]}" for code in REASONS)
    codes = ", ".join(f"CASE WHEN {code} THEN '{code}' END" for code in REASONS)
    return f"""
        WITH triggers AS (
            SELECT f.dataset_id, f.dataset_fingerprint, f.source_row, f.occurred_at,
                f.split, {", ".join(selected + flags)},
                (payment_format='ACH')::INTEGER AS ach_score,
                coalesce(ps.supported AND amount_paid > ps.p995, false)::INTEGER
                    AS currency_tail_score
            FROM features f
            LEFT JOIN currency_profile ps ON ps.role='sender'
                AND ps.currency=f.payment_currency
            LEFT JOIN currency_profile pr ON pr.role='receiver'
                AND pr.currency=f.receiving_currency
            WHERE f.split = ?
        )
        SELECT *, ({score})::INTEGER AS risk_score, 0::INTEGER AS constant_score,
            list_filter([{codes}], x -> x IS NOT NULL) AS reason_codes
        FROM triggers
    """


def register_profile(connection: duckdb.DuckDBPyConnection, profile: dict) -> None:
    rows = [
        {**r, "p95": Decimal(r["p95"]), "p995": Decimal(r["p995"])}
        for r in profile["currencies"]
    ]
    schema = pa.schema(
        [
            ("role", pa.string()),
            ("currency", pa.string()),
            ("observations", pa.int64()),
            ("p95", pa.decimal128(38, 9)),
            ("p995", pa.decimal128(38, 9)),
            ("supported", pa.bool_()),
        ]
    )
    connection.register("currency_profile", pa.Table.from_pylist(rows, schema=schema))
