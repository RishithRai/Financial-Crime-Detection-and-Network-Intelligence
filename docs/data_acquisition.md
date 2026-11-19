# HI-Small acquisition and provenance

IBM's [AML-Data repository](https://github.com/IBM/AML-Data) links to the
[official Kaggle dataset](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml).
data-acquisition stage used Kaggle **version 8**, last updated July 8, 2025. IBM describes
the data as synthetic. The data license is **CDLA-Sharing-1.0**, distinct from
the repository's Apache-2.0 code license. Check the source's license terms
before redistributing data; raw files are excluded from this repository.

Only these data files are in scope:

| File | Source-listed bytes |
| --- | --- |
| HI-Small_Trans.csv | 475664283 |
| HI-Small_accounts.csv | 34053187 |
| HI-Small_Patterns.txt | 323844 |

The three files were downloaded individually over unauthenticated HTTPS.
No credentials were needed. No other dataset variant or full-dataset archive
was downloaded. The patterns request used the current version (8 at retrieval);
the transactions and accounts requests explicitly specified version 8. The
exact request URLs, local hashes, sizes, and retrieval time appear in the
[validation report](data_validation_report.md).

## Existing workspace

Do not overwrite the existing raw files. The directory layout is:

```text
data/raw/hi-small/
  HI-Small_Trans.csv
  HI-Small_accounts.csv
  HI-Small_Patterns.txt
data/provenance/hi-small/
  manifest.json
  kaggle-metadata.json
  kaggle-files.json
data/validation/hi-small.json
```

All of `data/` is ignored by Git. Raw files were downloaded into temporary
`.download` paths, checked against Kaggle's byte counts, then renamed without
decoding or rewriting their contents. The validator hashes bytes before and
after its audit and compares them with the acquisition manifest. Download
metadata is an observation at retrieval time; a local hash is an integrity
baseline, not a publisher signature.

## Fresh acquisition

Use individual-file downloads; never use the dataset-wide download button or
omit the `-f` option from a Kaggle CLI command. For example, the official Kaggle
CLI supports:

```sh
kaggle datasets download \
  ealtman2019/ibm-transactions-for-anti-money-laundering-aml \
  -f HI-Small_Trans.csv -p data/raw/hi-small --unzip
```

Repeat only for the accounts and patterns filenames above. This CLI example
uses the current dataset version; verify version and hashes before comparing
results with this report. For the exact version-8 HTTP route, use:

```text
https://www.kaggle.com/api/v1/datasets/download/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/HI-Small_Trans.csv?datasetVersionNumber=8
```

Substitute only the requested accounts or patterns filename. Keep downloads
in temporary paths until HTTP success, file type, and expected size have been
verified. If served as a ZIP, extract only the named member, preserving its
bytes; do not treat archive bytes or a login HTML page as CSV. Do not force
overwrites of existing raw files. Keep acquisition metadata separate from raw
files and record this manifest structure:

```json
{
  "dataset_url": "official dataset page URL",
  "upstream_url": "https://github.com/IBM/AML-Data",
  "dataset_version": 8,
  "dataset_last_updated": "timestamp from source metadata",
  "retrieved_at_utc": "actual acquisition timestamp",
  "license": "license from source metadata",
  "method": "actual download and extraction method",
  "files": {
    "HI-Small_Trans.csv": {
      "source_url": "actual request URL",
      "size_bytes": 475664283,
      "sha256": "actual SHA-256 of unmodified CSV bytes"
    }
  }
}
```

Include entries for all three files. Use actual measurements, not copied
placeholder hashes. Omitting `--provenance` still permits validation, but the
report explicitly warns that acquisition provenance is unverified.

## If Kaggle requires authentication later

Sign in to Kaggle, complete any account/terms prompts on the dataset page,
and use Kaggle's supported local authentication flow. Follow the
[official Kaggle CLI authentication instructions](https://github.com/Kaggle/kaggle-cli#authentication).
Keep tokens in Kaggle's normal local credential store or environment variables.
Never hardcode tokens, add credentials to Git, or paste them into project docs
or chat. Alternatively, download just these three files through the signed-in
Kaggle UI and place their unchanged bytes in the ignored raw directory.

CLI file-download reference:
[Kaggle dataset commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md).
