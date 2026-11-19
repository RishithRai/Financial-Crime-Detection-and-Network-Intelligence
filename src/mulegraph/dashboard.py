"""Local investigation workspace; backend evidence remains authoritative."""

import os
from datetime import datetime, timedelta

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from mulegraph.dashboard_data import DashboardData
from mulegraph.explanations import ExplanationService

NAV = [
    "Home",
    "Transaction Queue",
    "Network Explorer",
    "Investigation Cases",
    "Model Evaluation",
]
BLUE, PURPLE, AMBER = "#7C9CFF", "#AD91ED", "#F0BD69"


def chart(fig: go.Figure) -> None:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=30, b=30),
        font=dict(color="#CED8EB"),
    )
    st.plotly_chart(fig, width="stretch")


def table(rows: list[dict], key: str) -> None:
    if not rows:
        st.info("No evidence in this selection.")
        return
    page = st.number_input("Evidence page", 1, max(1, (len(rows) + 24) // 25), key=key)
    visible = rows[(page - 1) * 25 : page * 25]
    if visible and "from_bank_id" in visible[0]:
        visible = [
            {
                "Source": t["source_row"],
                "Time": t["occurred_at"],
                "From": f"{t['from_bank_id']} / {t['from_account']}",
                "To": f"{t['to_bank_id']} / {t['to_account']}",
                "Paid": f"{t['amount_paid']} {t['payment_currency']}",
                "Received": f"{t['amount_received']} {t['receiving_currency']}",
                "Score": t.get("score"),
                "Coverage": t.get("score_status", "Pattern evidence")
                .replace("_", " ")
                .lower(),
            }
            for t in visible
        ]
    st.dataframe(
        visible, hide_index=True, width="stretch", alt="Paginated evidence records"
    )
    st.caption(
        f"{len(rows):,} records • 25 per page • distinct source rows remain distinct transfers"  # noqa: E501
    )


def explanation(
    source: int, report: dict | None = None, *, scope: str = "main"
) -> None:  # noqa: E501
    if st.button("Explain selected transaction", key=f"explain-{scope}-{source}"):
        with st.spinner("Verifying frozen inputs and computing TreeSHAP…"):
            service = ExplanationService()
            if report:
                result = service.annotate_case_report(report, [source])[
                    "transaction_explanations"
                ]["items"][0]
            else:
                result = service.explain([source])[0]
        st.session_state["explanation"] = result
    result = st.session_state.get("explanation", {})
    if result.get("source_row") != source:
        return
    if result["status"] != "EXPLAINED":
        st.info(
            result["status"].replace("_", " ").title()
            + ". No in-sample score substituted."
        )
        return
    cols = st.columns(3)
    cols[0].metric("Saved review score", f"{result['saved_review_score']:.6f}")
    cols[1].metric("Raw model margin", f"{result['raw_margin']:.4f}")
    cols[2].metric("Additivity error", f"{result['additivity_error']:.2e}")
    values = sorted(
        result["contributions"], key=lambda r: abs(r["raw_contribution"]), reverse=True
    )
    top = values[:10]
    chart(
        go.Figure(
            go.Bar(
                x=[v["raw_contribution"] for v in top][::-1],
                y=[v["description"] for v in top][::-1],
                orientation="h",
                marker_color=[
                    BLUE if v["raw_contribution"] > 0 else PURPLE for v in top
                ][::-1],
            )
        ).update_layout(
            height=460, xaxis_title="Contribution to raw margin (not probability)"
        )
    )
    st.caption(
        f"Training-path baseline {result['base_value']:.6f}. Top 10 shown; all contributions below sum with the baseline to the raw output. Blue increases the score; purple decreases it. Neither direction is causal evidence."  # noqa: E501
    )
    with st.expander("All encoded feature contributions and observed values"):
        table(values, "shap-page")


def overview(data: DashboardData) -> None:
    st.caption("ARCHIVED EVALUATION • Separate from live investigation evidence")
    st.title("Detection overview")
    st.write(
        "A frozen model. A bounded investigation workflow. Evidence you can trace."
    )
    results = data.overview()
    split = (
        st.segmented_control(
            "Evaluation population", ["test", "stress"], default="test"
        )
        or "test"
    )
    metrics = results["splits"][split]["metrics"]
    m = metrics["lightgbm"]
    cols = st.columns(4)
    for col, label, value in zip(
        cols,
        [
            "Evaluation transactions",
            "Average precision",
            "Recall at 1% budget",
            "Frozen-threshold alert rate",
        ],
        [
            f"{m['rows']:,}",
            f"{m['ap']:.4f}",
            f"{m['budget']['recall']:.2%}",
            f"{m['alert_rate']:.2%}",
        ],
        strict=True,
    ):
        col.metric(label, value)
    st.caption(
        f"Dataset: 5,078,345 transactions • {split} prevalence: {m['prevalence']:.4%} • Frozen threshold: {m['threshold']:.10f}"  # noqa: E501
    )
    left, right = st.columns(2)
    groups = results["splits"][split]["groups"]
    with left:
        st.subheader("Transaction volume")
        chart(
            go.Figure(
                go.Bar(
                    x=[r[0] for r in groups["day"]],
                    y=[r[1] for r in groups["day"]],
                    marker_color=BLUE,
                )
            ).update_layout(yaxis_title="Transactions", height=300)
        )
    with right:
        st.subheader("Alerts by payment format")
        chart(
            go.Figure(
                go.Bar(
                    x=[r[0] for r in groups["payment_format"]],
                    y=[r[3] for r in groups["payment_format"]],
                    marker_color=AMBER,
                )
            ).update_layout(yaxis_title="Frozen-threshold alerts", height=300)
        )
    st.subheader("Frozen model comparison")
    st.dataframe(
        [
            {
                "Method": name,
                "AP": v["ap"],
                "ROC-AUC": v["roc_auc"],
                "Precision@100": v["at_100"]["precision"],
                "Precision@1,000": v["at_1000"]["precision"],
                "Recall@1%": v["budget"]["recall"],
                "Alerts": v["alerts"],
            }
            for name, v in metrics.items()
        ],
        hide_index=True,
        width="stretch",
    )
    st.warning(
        "Development holdouts, previously inspected in aggregate. Stress has a small, shifted, all-ACH population; AP across populations is not directly comparable. All supervised threshold true positives on primary test were ACH. Review scores are uncalibrated."  # noqa: E501
    )
    st.caption(
        "These saved aggregate statistics use historical evaluation labels. No row-level labels are exposed to investigators or fetched by this application."  # noqa: E501
    )


def select_transaction(row: dict) -> None:
    """Store complete focal context, clear stale evidence, and schedule one query."""
    st.session_state["focal_context"] = row
    for key in ("report", "explanation", "investigation_error"):
        st.session_state.pop(key, None)
    st.session_state["pending_investigation"] = True
    st.session_state["next_nav"] = "Network Explorer"


def transaction_cards(rows: list[dict], scope: str) -> None:
    for row in rows:
        with st.container(border=True):
            left, middle, action = st.columns([2, 3, 1], vertical_alignment="center")
            left.markdown(f"**{row['amount_paid']} {row['payment_currency']}**")
            left.caption(f"{row['payment_format']} · #{row['source_row']}")
            middle.text(
                f"{row['from_bank_id']} / {row['from_account']} → "
                f"{row['to_bank_id']} / {row['to_account']}"
            )
            middle.caption(str(row["occurred_at"]))
            action.markdown(f"**{row['score']:.4f}** review score")
            action.button(
                "Investigate",
                key=f"investigate-{scope}-{row['source_row']}",
                type="primary",
                width="stretch",
                on_click=select_transaction,
                args=(row,),
            )


def home(data: DashboardData) -> None:
    st.caption("INVESTIGATION WORKSPACE · SAVED TRANSACTIONS")
    st.title("Start with a transaction. Follow the evidence.")
    st.write(
        "Review the highest-scoring saved transfers, then open their earlier network "
        "with one click. No identifier copying required."
    )
    st.caption(
        "Primary test · September 9–10, 2022 · Historical review, not live alerts"
    )
    if "home_rows" not in st.session_state or st.button(
        "Refresh prioritized transactions"
    ):
        with st.spinner("Verifying saved scores…"):
            st.session_state["home_rows"] = data.queue(size=5, alerts_only=True)[0]
    rows = st.session_state["home_rows"]
    if rows:
        transaction_cards(rows, "home")
    else:
        st.info(
            "No saved transactions meet the frozen threshold in this period. "
            "Open Transaction Queue to explore other periods or all scores."
        )
    st.caption(
        "Review scores are uncalibrated. A high score or network pattern does not "
        "establish wrongdoing. Evaluation metrics are in Model Evaluation."
    )


def score_summary(summary: dict) -> None:
    cols = st.columns(3)
    maximum = summary["max_transaction_score"]
    coverage = summary["score_coverage"]
    cols[0].metric(
        "Highest transaction score", "Unscored" if maximum is None else f"{maximum:.4f}"
    )
    cols[1].metric(
        "Scored transactions",
        f"{summary['scored_transactions']} / {summary['distinct_transactions']}",
    )
    cols[2].metric(
        "Score coverage", "No transactions" if coverage is None else f"{coverage:.1%}"
    )
    for reason, count in summary["unscored_reasons"].items():
        st.caption(
            f"{count} transactions: {reason.replace('_', ' ').lower()}. "
            "No substitute predictions."
        )


def account_summary(account: dict) -> None:
    score_summary(account["ml_summary"])
    h = account["history"]
    st.write(
        f"{h['incoming']} incoming · {h['outgoing']} outgoing · "
        f"{h['unique_counterparties']} distinct counterparties"
    )
    st.caption(
        "History covers the requested window."
        if h["complete_for_account"]
        else "Partial local history: this neighbor's full activity is not certified."
    )
    st.caption(" · ".join(r.replace("_", " ").lower() for r in account["reason_codes"]))


def run_investigation(
    data: DashboardData,
    start: datetime,
    cutoff: datetime,
    account: tuple[str, str],
    focal: int | None,
    hops: int = 1,
    nodes: int = 150,
    edges: int = 1000,
) -> None:
    st.session_state.pop("report", None)
    st.session_state.pop("explanation", None)
    if start.tzinfo or cutoff.tzinfo or start >= cutoff:
        raise ValueError(
            "Use source timestamps without timezone; start must precede cutoff"
        )
    if not all(account):
        raise ValueError("Both bank and account are required")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        st.error(
            "Database is not configured. Restart with --env-file .env, then retry."
        )
        return
    with st.spinner("Opening earlier history and finding supporting evidence…"):
        st.session_state["report"] = data.investigate(
            dsn,
            start,
            cutoff,
            account=account,
            focal=focal,
            hops=hops,
            nodes=nodes,
            edges=edges,
        )


def parse_source(value: str) -> int | None:
    if not value:
        return None
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise ValueError("Source ID must contain positive digits only")
    return int(value)


def queue(data: DashboardData) -> None:
    st.title("Transaction queue")
    st.write(
        "Prioritize saved review scores, then inspect the evidence behind a transfer."
    )
    with st.form("queue-filters"):
        cols = st.columns(3)
        split = cols[0].selectbox(
            "Saved-score period", ["test", "validation", "stress"]
        )
        order = cols[1].selectbox("Sort", ["Highest score", "Newest", "Source ID"])
        source = cols[2].text_input("Exact source ID (optional)")
        cols = st.columns(3)
        bank = cols[0].text_input("Bank ID (exact)")
        account = cols[1].text_input("Account ID (exact)")
        fmt = cols[2].text_input("Payment format (exact, optional)")
        alerts = st.checkbox("Frozen-threshold alerts only")
        page = st.number_input("Page (10 transactions)", 1, 1001)
        submitted = st.form_submit_button("Search saved transactions", type="primary")
    st.caption(
        "Training-period transactions have no saved predictions and are absent from this queue. Search a training source ID with the explanation lookup below to see its explicit unscored status."  # noqa: E501
    )
    if submitted or "queue_rows" not in st.session_state:
        st.session_state.pop("queue_rows", None)
        with st.spinner("Checking artifacts and retrieving one bounded page…"):
            rows, more = data.queue(
                split,
                page=page - 1,
                size=10,
                order=order,
                source=parse_source(source),
                bank=bank,
                account=account,
                payment_format=fmt,
                alerts_only=alerts,
            )
        st.session_state["queue_rows"] = rows
        st.session_state["queue_caption"] = f"{split} • Page {page} • {order} • " + (
            "More results available; increase page." if more else "End of results."
        )
    rows = st.session_state.get("queue_rows", [])
    if "queue_rows" in st.session_state:
        st.caption(st.session_state["queue_caption"])
        if not rows:
            st.info("No transactions match these filters.")
        else:
            transaction_cards(rows, "queue")
    with st.expander("Direct explanation lookup, including unscored transactions"):
        source_id = st.number_input("Source ID", min_value=1, step=1)
        explanation(int(source_id), scope="lookup")


def network_figure(report: dict, selected: tuple[str, str]) -> go.Figure:
    graph = nx.DiGraph()
    graph.add_nodes_from(tuple(a["account"]) for a in report["accounts"])
    for t in report["transactions"]:
        graph.add_edge(
            (t["from_bank_id"], t["from_account"]), (t["to_bank_id"], t["to_account"])
        )
    # Display only selected account's incident relationships; full evidence remains below.  # noqa: E501
    keep = {selected, *graph.predecessors(selected), *graph.successors(selected)}
    view = graph.subgraph(keep)
    pos = nx.circular_layout(sorted(view.nodes))
    fig = go.Figure()
    for a, b in view.edges:
        if a == b:
            continue  # self transfers are explicitly listed in the evidence inspector
        x, y = pos[a], pos[b]
        fig.add_annotation(
            x=float(y[0] * 0.85 + x[0] * 0.15),
            y=float(y[1] * 0.85 + x[1] * 0.15),
            ax=float(x[0] * 0.85 + y[0] * 0.15),
            ay=float(x[1] * 0.85 + y[1] * 0.15),
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#51688C",
            arrowsize=1,
        )
    nodes = list(view.nodes)
    fig.add_trace(
        go.Scatter(
            x=[pos[n][0] for n in nodes],
            y=[pos[n][1] for n in nodes],
            mode="markers",
            customdata=[list(n) for n in nodes],
            text=[f"Bank {n[0]} / {n[1]}" for n in nodes],
            hovertemplate="%{text}<extra></extra>",
            marker=dict(
                size=[22 if n == selected else 13 for n in nodes],
                color=[AMBER if n == selected else BLUE for n in nodes],
            ),
        )
    )
    fig.update_layout(
        height=440,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, scaleanchor="x"),
        showlegend=False,
    )
    return fig


def investigations(data: DashboardData, cases: bool = False) -> None:
    st.title("Investigation cases" if cases else "Network explorer")
    st.write("Organize descriptive evidence around an explicit historical cutoff.")
    focal = st.session_state.get("focal_context")
    if focal:
        st.info(
            f"Focal transaction #{focal['source_row']} • history strictly before {focal['occurred_at']}. The focal is separate from all case evidence."  # noqa: E501
        )
        if st.button("Clear focal context"):
            st.session_state.pop("focal_context", None)
            st.session_state.pop("report", None)
            st.rerun()
    if st.session_state.pop("pending_investigation", False) and focal:
        cutoff_time = focal["occurred_at"]
        if isinstance(cutoff_time, str):
            cutoff_time = datetime.fromisoformat(cutoff_time)
        run_investigation(
            data,
            max(datetime(2022, 9, 1), cutoff_time - timedelta(days=1)),
            cutoff_time,
            (focal["from_bank_id"], focal["from_account"]),
            focal["source_row"],
        )
    if focal:
        with st.expander("Selected transfer · details and SHAP"):
            st.write(
                f"Paid {focal['amount_paid']} {focal['payment_currency']} · "
                f"Received {focal['amount_received']} {focal['receiving_currency']}"
            )
            st.text(
                f"Sender {focal['from_bank_id']} / {focal['from_account']} → "
                f"Receiver {focal['to_bank_id']} / {focal['to_account']}"
            )
            explanation(focal["source_row"], scope="focal")
    with st.expander(
        "Advanced settings · change investigation scope",
        expanded=not focal and "report" not in st.session_state,
    ):
        with st.form("investigate"):
            cols = st.columns(2)
            bank = cols[0].text_input(
                "Root bank", value=focal["from_bank_id"] if focal else ""
            )
            account = cols[1].text_input(
                "Root account", value=focal["from_account"] if focal else ""
            )
            cols = st.columns(2)
            start = cols[0].text_input(
                "History start (inclusive)", "2022-09-01T00:00:00"
            )
            cutoff = cols[1].text_input(
                "Cutoff (exclusive)",
                str(focal["occurred_at"]) if focal else "2022-09-11T00:00:00",
                disabled=bool(focal),
            )
            cols = st.columns(3)
            hops = cols[0].slider("Hops", 1, 2, 1)
            nodes = cols[1].number_input("Maximum accounts", 1, 500, 150)
            edges = cols[2].number_input("Maximum transactions", 1, 5000, 1000)
            run = st.form_submit_button("Run bounded investigation", type="primary")
        st.caption(
            "Source event time; timezone/arrival availability unknown. Same-timestamp peers excluded. Five-second SQL timeout per query. Finding and candidate caps remain enforced."  # noqa: E501
        )
    if run:
        st.session_state.pop("report", None)
        st.session_state.pop("explanation", None)
        try:
            start_time, cutoff_time = (
                datetime.fromisoformat(start),
                datetime.fromisoformat(cutoff),
            )
        except ValueError:
            st.error(
                "Enter dates as YYYY-MM-DDTHH:MM:SS, for example 2022-09-09T00:00:00."
            )
            return
        if not bank or not account or start_time >= cutoff_time:
            st.error("Enter both bank and account, and a start time before the cutoff.")
            return
        run_investigation(
            data,
            start_time,
            cutoff_time,
            (bank, account),
            focal["source_row"] if focal else None,
            hops,
            int(nodes),
            int(edges),
        )
    report = st.session_state.get("report")
    if not report:
        st.info(
            "Select a transaction in the queue or enter a composite account to begin. No investigation has been completed."  # noqa: E501
        )
        return
    st.caption(
        f"RESULT SCOPE • {report['root']} • {report['start']} ≤ event time < {report['cutoff']}"  # noqa: E501
    )
    cols = st.columns(3)
    cols[0].metric("Review groups", len(report["cases"]))
    cols[1].metric("Pattern witnesses", len(report["findings"]))
    cols[2].metric("Distinct historical transfers", len(report["transactions"]))
    st.caption(
        "Completed within requested limits; not a global search. Groups are not independent incidents. Neighbor histories may be incomplete. ML ranking and network evidence are separate."  # noqa: E501
    )
    if not cases and st.button("Review grouped cases", type="primary"):
        st.session_state["next_nav"] = "Investigation Cases"
        st.rerun()
    if cases:
        if not report["cases"]:
            st.info(
                "No cases found within this scope; this is not evidence of low risk."
            )
            return
        case = st.selectbox(
            "Review case",
            report["cases"],
            format_func=lambda c: (
                f"{c['id'][:12]} · {c['finding_count']} witnesses · {c['ml_summary']['scored_transactions']} scored transactions"  # noqa: E501
            ),
        )
        st.write(
            " · ".join(code.replace("_", " ").title() for code in case["reason_codes"])
        )
        score_summary(case["ml_summary"])
        with st.expander("Account-level evidence and score coverage"):
            members = {tuple(a) for a in case["accounts"]}
            account_rows = [
                a for a in report["accounts"] if tuple(a["account"]) in members
            ]
            inspected = st.selectbox(
                "Case account",
                account_rows,
                format_func=lambda a: " / ".join(a["account"]),
            )
            account_summary(inspected)
            st.caption(
                "Each maximum uses this account's own incident transactions. "
                "It is not an account probability; neighbor history may be incomplete."
            )

        ids = set(case["finding_ids"])
        findings = [f for f in report["findings"] if f["id"] in ids]
        transfers = [
            t
            for t in report["transactions"]
            if t["source_row"] in case["transaction_ids"]
        ]
    else:
        accounts = [tuple(a["account"]) for a in report["accounts"]]
        selected = st.selectbox(
            "Inspect account / focus network",
            accounts,
            format_func=lambda a: f"Bank {a[0]} / {a[1]}",
        )
        fig = network_figure(report, selected)
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        event = st.plotly_chart(
            fig,
            width="stretch",
            on_select="rerun",
            key=f"network-selection-{selected}",
            selection_mode="points",
            alt="Directed local account relationships; select a node to inspect",
        )
        if event.selection.points:
            point = event.selection.points[0]
            clicked = tuple(point.get("customdata", []))
            if clicked in accounts:
                selected = clicked
        st.caption(f"Inspecting bank {selected[0]} / {selected[1]}")
        st.caption(
            "Directed relationships in the selected account’s local neighborhood. Repeated transfers share an arrow; self transfers appear in the table. Static arrows do not establish chronological movement."  # noqa: E501
        )
        summary = next(a for a in report["accounts"] if tuple(a["account"]) == selected)
        with st.expander(
            "Account score coverage, reason codes and historical activity",
            expanded=True,
        ):
            account_summary(summary)
        transfers = [
            t
            for t in report["transactions"]
            if selected
            in [
                (t["from_bank_id"], t["from_account"]),
                (t["to_bank_id"], t["to_account"]),
            ]
        ]
        findings = report["findings"]
    st.subheader("Pattern evidence & temporal sequence")
    types = st.multiselect(
        "Pattern types", sorted({f["pattern_type"] for f in findings})
    )
    findings = [f for f in findings if not types or f["pattern_type"] in types]
    if findings:
        finding = st.selectbox(
            "Supporting witness",
            findings,
            format_func=lambda f: (
                f"{f['pattern_type']} · {f['first_at']} · {f['id'][:10]}"
            ),
        )
        st.write(finding["interpretation"])
        with st.expander("Supporting evidence details"):
            st.json(finding["evidence"])
        table(
            sorted(
                finding["transactions"],
                key=lambda t: (t["occurred_at"], t["source_row"]),
            ),
            "sequence-page",
        )
    else:
        st.info("No pattern witnesses for this selection.")
    st.subheader("Individual transfer evidence")
    table(
        sorted(transfers, key=lambda t: (t["occurred_at"], t["source_row"])),
        "transfer-page",
    )
    if transfers:
        source = st.selectbox(
            "Explain evidence transaction", [t["source_row"] for t in transfers]
        )
        explanation(source, report)


def main() -> None:
    st.set_page_config(
        page_title="MuleGraph | Investigation workspace", page_icon="◈", layout="wide"
    )
    if "next_nav" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("next_nav")
    with st.sidebar:
        st.title("◈ MuleGraph")
        st.caption("INVESTIGATION WORKSPACE")
        section = st.radio("Workspace", NAV, key="nav", label_visibility="collapsed")
        focal = st.session_state.get("focal_context")
        if focal:
            st.caption(f"Selected transaction #{focal['source_row']}")
            st.caption(str(focal["occurred_at"]))
        st.caption("FROZEN MODEL")
        st.write("LightGBM · history_none")
        st.caption("Read-only • Local session")
        st.info(
            "Review scores prioritize attention. They are not calibrated probabilities or proof of wrongdoing."  # noqa: E501
        )
    try:
        data = DashboardData()
        if section == "Home":
            home(data)
        elif section == "Model Evaluation":
            overview(data)
        elif section == "Transaction Queue":
            queue(data)
        else:
            investigations(data, section == "Investigation Cases")
    except Exception as exc:
        # Do not expose DSNs, credentials, SQL, or local paths in browser errors.
        from mulegraph.graph import GraphLimitExceeded

        if isinstance(exc, GraphLimitExceeded):
            st.warning(
                "Investigation exceeds resource limits. No partial result returned. Narrow the dates or reduce hops; evidence totals are unknown."  # noqa: E501
            )
        elif isinstance(exc, ValueError):
            st.error(
                "Check your inputs: use a positive source ID, both bank and account, "
                "and a start before cutoff. If inputs are valid, artifact "
                "verification failed; restore the original files rather than refitting."
            )
        elif isinstance(exc, (FileNotFoundError, OSError)):
            st.error(
                "Local data or service unavailable. Check PostgreSQL and the saved "
                "artifact folders, then retry. Existing data has not been changed."
            )
        else:
            st.error(
                "Request could not be completed. Check input formats, local service availability and frozen-artifact integrity. No partial result is presented."  # noqa: E501
            )
        st.caption(
            f"Failure category: {type(exc).__name__}. Credentials and internal exception details are not displayed."  # noqa: E501
        )
