# Five-minute portfolio demonstration

Use the local full-data workspace, built frontend and running API described in
[reproduction](reproducibility.md). Rehearse before presenting; network/model
hashing and SQL can add delays. This is a retrospective synthetic-data example,
not a live alert or verified criminal case. No ground-truth labels are displayed.

| Time | Action | Explain and expected observation |
| --- | --- | --- |
| 0:00–0:40 | Open localhost:8000, review queue, search primary-test reference **2612189**, choose **Review transfer** | Saved review priorities are uncalibrated scores. Amounts preserve exact underlying decimals and identities are composite bank/account pairs. The source reference supplies context automatically. |
| 0:40–1:15 | Read model contribution cards; expand technical details briefly | Contributions increase/decrease a raw model margin relative to its background. Native TreeSHAP additivity and saved-score agreement are checked. This is not causality or an explanation of criminal intent. |
| 1:15–2:00 | **Explore connected accounts** | Default preceding-24-hour one-hop history: **7 historical accounts, 22 transfers, 6 grouped arrows, no witnesses**. Plus one separate focal arrow and one focal-only account. No findings within this scope does not mean safe. Click a node/arrow and inspect its transfers. |
| 2:00–2:45 | Expand **Advanced scope**, **Use wider history** | September 1 to focal cutoff, one hop: **15 historical accounts, 197 transfers, 16 grouped arrows**; focal stays separate. **706 overlapping witnesses, 5 review groups, 172 distinct supporting transfers**. Historical score coverage **50/197**. Fit/zoom, then select a group. |
| 2:45–3:40 | **Review the 5 groups**, choose a group and pattern, navigate witnesses | Only that group's original findings appear. All 706 witnesses remain accessible; the graph highlights exact selected references within grouped arrows. Counts are organizational summaries, not independent incidents. Use **Show sequence on network** and **Return to full network**. |
| 3:40–4:20 | Inspect **How much does this observation tell us?**, handoff amounts and sequence | The records establish connected accounts in strict time order. Exact incoming received/outgoing paid amounts, signed difference, elapsed seconds and intervening local activity provide context, not proof of same funds. Missing training scores mean unknown, not low risk. Neighbor history is incomplete. |
| 4:20–5:00 | Open [graph-feature comparison](graph_prediction_report.md) and [README results](../README.md#measured-results) | Separate pair-history features improved reused-validation AP **0.56054 → 0.62812**, recall **79.54% → 83.01%** at the same 1% budget. Only two fixed fits; original demo model unchanged. No new graph-model test/stress result or claim of unseen-data improvement. |

## Recovery and honest presentation

Optional boundary demonstration: the wider **two-hop** request exceeds the existing
1,000-finding cap for this example. Expect a resource-limit message, no partial
report and cleared stale graph. Explicitly choose preceding 24 hours to recover;
there is no automatic scope change. A cap is a computational boundary, not evidence
of suspiciousness. Do not increase limits simply to obtain a successful demo.

If the API is unavailable, start the localhost launch command. If queue/explanations
report missing artifacts or integrity failures, verify the correct environment and
original files; do not disable checks. If PostgreSQL is stopped, start the existing
Compose service without deleting its volume. Use the aggregate reports/architecture
as a presentation fallback; never substitute a screenshot and call it live execution.

Three [reviewed application screenshots](screenshots/README.md) are bundled with
synthetic-data attribution. They illustrate the recorded workflow without requiring
a local installation. The architecture diagram and aggregate metrics provide further
presentation material. Review new recordings for data exposure before sharing them.
