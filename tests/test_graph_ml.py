"""Full synthetic two-fit run, preservation, reload and one-attempt guards."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_ml import fixture_table

from mulegraph import graph_ml
from mulegraph.features import sha256_file
from mulegraph.graph_features import build
from mulegraph.graph_prediction_report import render
from mulegraph.graph_prediction_verify import verify
from mulegraph.ml import Preprocessor, tie_keys
from mulegraph.ml_stabilization import fit_one
from mulegraph.ml_training import load_artifact


def test_synthetic_pipeline_and_preservation(tmp_path, monkeypatch):
    original_plan = Path("docs/graph_prediction_plan_v1.json").read_bytes()
    lock = Path("uv.lock").read_bytes()
    monkeypatch.chdir(tmp_path)
    Path("docs").mkdir()
    Path("docs/graph_prediction_plan_v1.json").write_bytes(original_plan)
    Path("uv.lock").write_bytes(lock)
    table = fixture_table(300)
    table = table.set_column(
        table.column_names.index("split"),
        "split",
        pa.array(["train"] * 200 + ["validation"] * 100),
    )
    times = [datetime(2022, 9, 1) + timedelta(seconds=i) for i in range(200)] + [
        datetime(2022, 9, 7) + timedelta(seconds=i) for i in range(100)
    ]
    for n, values in {
        "source_row": range(1, 301),
        "occurred_at": times,
        "from_bank_id": ["1"] * 300,
        "from_account": ["A"] * 300,
        "to_bank_id": ["2"] * 300,
        "to_account": ["B"] * 300,
    }.items():
        table = table.append_column(n, pa.array(values))
    features = tmp_path / "history"
    features.mkdir()
    pq.write_table(table, features / "features.parquet")
    manifest = {
        "definition": {"version": "historical-v1"},
        "file_sha256": sha256_file(features / "features.parquet"),
        "dataset": {
            "dataset_id": 1,
            "dataset_key": "fixture",
            "fingerprint": "fixture",
        },
    }
    (features / "manifest.json").write_text(json.dumps(manifest))
    graph = tmp_path / "graph"
    build(features, graph)
    base = Preprocessor.fit([table.slice(0, 200)], "history")
    labels = {"train": np.array([0, 1] * 100), "validation": np.array([0, 1] * 50)}
    ids = np.arange(201, 301)
    dest = Path("data/ml/lightgbm-stable-v1/history_none")
    dest.parent.mkdir(parents=True)
    fit_one(
        {"name": "history_none", "weight": "none", "variant": "history"},
        base,
        {
            "train": base.transform(table.slice(0, 200)),
            "validation": base.transform(table.slice(200)),
        },
        labels,
        ids,
        tie_keys(ids, "fixture"),
        dest,
    )
    access = []

    def export(dsn, manifest, split, path, schema):
        assert split in ("train", "validation")
        access.append(split)
        pq.write_table(
            pa.table(
                {
                    "source_row": np.arange(1, 201) if split == "train" else ids,
                    "label": labels[split],
                }
            ),
            path,
        )
        return {
            "split": split,
            "rows": len(labels[split]),
            "sha256": sha256_file(path),
            "completed_at": "2026-10-15T00:00:00+00:00",
        }

    monkeypatch.setattr(graph_ml, "export_labels", export)
    plan = tmp_path / "plan.json"
    graph_ml.freeze(features, graph, plan)
    output = tmp_path / "experiment"
    result = graph_ml.run(features, graph, plan, output, "synthetic")
    assert access == ["train", "validation"]
    audit = verify(features, graph, output, tmp_path / "audit.json")
    assert audit["reproduced_validation_scores"] == 200
    assert audit["training_preprocessing_exact"]
    report = render(output, graph)
    assert "history_control" in report and "history_plus_graph" in report
    assert "No new test/stress predictions" in report
    assert result["experiments"][0]["frozen_control_exact"]
    assert len(result["experiments"]) == 2
    loaded = load_artifact(output / "history_plus_graph")
    assert len(loaded["preprocessor"].names) == len(base.names) + 6
    with pytest.raises(ValueError, match="Completed"):
        graph_ml.run(features, graph, plan, output, "synthetic")
    assert not list(tmp_path.glob(".graph-ml-*"))
    assert not list(tmp_path.rglob("*.labels.parquet"))

    def fail_export(*args, **kwargs):
        raise RuntimeError("synthetic export failure")

    monkeypatch.setattr(graph_ml, "export_labels", fail_export)
    failed = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="synthetic export"):
        graph_ml.run(features, graph, plan, failed, "synthetic")
    assert failed.with_suffix(".attempt.json").exists()
    assert not failed.exists()
    assert not list(tmp_path.glob(".graph-ml-*"))
    with pytest.raises(FileExistsError):
        graph_ml.run(features, graph, plan, failed, "synthetic")
    frozen = json.loads(plan.read_text())
    (graph / "features.parquet").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="changed"):
        graph_ml.validate(frozen)
    assert access == ["train", "validation"]
