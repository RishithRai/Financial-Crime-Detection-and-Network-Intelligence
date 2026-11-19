"""Train-only graph encoding, importable for persisted model bundles."""

from dataclasses import dataclass

import numpy as np
import pyarrow as pa

from mulegraph.graph_features import COLUMNS
from mulegraph.ml import Preprocessor


def graph_values(table: pa.Table) -> np.ndarray:
    raw = np.column_stack([table[n].cast(pa.float64()).to_numpy() for n in COLUMNS])
    if np.isinf(raw).any() or (raw < 0).any() or np.isnan(raw[:, :2]).any():
        raise ValueError("Invalid graph numeric input")
    return raw


@dataclass
class GraphPreprocessor:
    base: Preprocessor
    mean: np.ndarray
    scale: np.ndarray
    training_rows: int
    variant: str = "history"

    @property
    def names(self) -> list[str]:
        return self.base.names + list(COLUMNS) + [n + "__missing" for n in COLUMNS[2:]]

    @classmethod
    def fit(cls, base: Preprocessor, tables) -> "GraphPreprocessor":
        total = np.zeros(4)
        squares = np.zeros(4)
        count = 0
        for table in tables:
            if set(table["split"].to_pylist()) != {"train"}:
                raise ValueError("Graph preprocessing requires training rows only")
            x = np.log1p(np.nan_to_num(graph_values(table), nan=0))
            total += x.sum(axis=0)
            squares += (x * x).sum(axis=0)
            count += len(x)
        if count != base.training_rows or not count:
            raise ValueError("Graph preprocessing training coverage mismatch")
        mean = total / count
        scale = np.sqrt(np.maximum(squares / count - mean**2, 0))
        scale[scale == 0] = 1
        return cls(base, mean, scale, count)

    def transform(self, table: pa.Table) -> np.ndarray:
        raw = graph_values(table)
        x = (np.log1p(np.nan_to_num(raw, nan=0)) - self.mean) / self.scale
        result = np.column_stack(
            [self.base.transform(table), x, np.isnan(raw[:, 2:])]
        ).astype(np.float32)
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite graph model inputs")
        return result
