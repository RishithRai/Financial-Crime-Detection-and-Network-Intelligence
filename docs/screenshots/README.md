# Application screenshots

These are unchanged captures of the working MuleGraph application, recorded on
October 15, 2026 and selected for the portfolio on November 19, 2026. They show
historical saved scores from `lightgbm-stable-v1/history_none`, not the separate
graph-feature experiment. They are not mockups or evidence of a live hosted service.

| Image | What it demonstrates |
| --- | --- |
| [Transfer review](review.png) | Saved review score, original currency, and native TreeSHAP contribution cards |
| [Network and evidence](network-wide-evidence.png) | Bounded connected-account graph, selected chronological chain, exact amounts, and uncertainty |
| [Investigation groups](cases.png) | Five review groups with evidence-preserving selection and supporting transfers |

## Data attribution

Source: [IBM AML-Data](https://github.com/IBM/AML-Data), synthetic AML HI-Small,
[official Kaggle distribution](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml),
version 8. IBM describes the data as entirely synthetic, not anonymized real people.
The displayed bank/account references and transactions belong to this synthetic dataset.

The visible source-data excerpts are provided under the unmodified
[Community Data License Agreement — Sharing, Version 1.0](https://cdla.dev/sharing-1-0/)
(SPDX: CDLA-Sharing-1.0). Attribution belongs to IBM and the source data providers.
The application selects and reformats source records, displays shortened account
references, and adds model scores and analysis. These displayed views are not the
original CSV files. No raw dataset or saved model bundle is included.

The PNG captures themselves have not been retouched, redacted, or composited.
They contain no visible credentials, personal browser tabs, or local filesystem paths.
Their data license notice does not select a license for MuleGraph's application code.

Scores are uncalibrated review priorities; graph patterns and model explanations
are not proof of laundering. See the [walkthrough](../demo_walkthrough.md) and
[limitations](../../README.md#scope-and-limitations).
