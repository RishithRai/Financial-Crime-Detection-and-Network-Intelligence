# Engineering documentation

Start with the [project overview and results](../README.md), then choose a topic.
The application uses frozen `lightgbm-stable-v1/history_none`; graph-enhanced
prediction remains a separate validation-only experiment.

| Topic | Design and evidence |
| --- | --- |
| System | [Architecture](architecture.md), [installation and reproduction](reproducibility.md) |
| Data engineering | [Attribution/acquisition](data_acquisition.md), [schema and ingestion](schema_and_ingestion.md), [validation](data_validation_report.md), [EDA](eda_report.md) |
| Temporal features | [Historical features](historical_features.md), [verification](feature_verification.md) |
| Detection engine | [Rules](rules_baseline.md), [supervised learning](supervised_learning.md), [stabilization](ml_stabilization.md), [holdout results](ml_holdout_report_v1.md) |
| Graph prediction research | [Pair-feature contract](graph_prediction.md), [comparison](graph_prediction_report.md), [leakage verification](graph_prediction_verification.md) |
| Network investigation | [Graph foundation](transaction_graph.md), [patterns](network_investigation.md), [case intelligence](case_intelligence.md) |
| Analyst workflow | [Application](analyst_application.md), [summaries](analyst_intelligence.md), [evidence quality](evidence_quality.md), [walkthrough](demo_walkthrough.md) |
| Explanations | [TreeSHAP contracts](shap_explanations.md), [verification](shap_verification.md) |
| Testing and release | [Reproducibility](reproducibility.md), [execution record](portfolio_release.md) |

The `*_verification.md` and aggregate `*_report.md` files retain measured results,
limitations and dated execution evidence. Versioned JSON plans and freeze records
are reproducibility inputs, not disposable planning notes; some are loaded by the
application and tests. Stage identifiers in these records connect results to the original experiments.
Historical revision IDs are provenance references, not available checkout targets
in this source snapshot. These records are not current test runs. See
[reproduction limits](reproducibility.md#historical-environment-boundary).

No raw dataset files or saved models are bundled. Three [application screenshots](screenshots/README.md)
show the synthetic-data workflow. Screenshots, synthetic tests, architecture diagrams,
and aggregate plots can be reviewed without installing the local dataset.
