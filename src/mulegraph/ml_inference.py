"""Apply a trusted saved bundle without fitting or retrieving labels."""

import numpy as np
import pyarrow as pa
from threadpoolctl import threadpool_limits

from mulegraph.ml_training import predict


def score_batch(artifact: dict, table: pa.Table) -> tuple[np.ndarray, np.ndarray]:
    matrix = artifact["preprocessor"].transform(table)
    if matrix.shape[1] != artifact["model"].n_features_in_:
        raise ValueError("Estimator/preprocessing dimension mismatch")
    with threadpool_limits(limits=2):
        scores = predict(artifact["model"], matrix).astype(np.float64)
    # Threshold was selected in float64. Do not round it into float32 score ties.
    return scores, scores >= artifact["threshold"]
