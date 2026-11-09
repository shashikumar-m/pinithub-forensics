"""
JSON Serialization Utilities for FastAPI & NumPy types.

Ensures that all NumPy scalars (np.float32, np.float64, np.int32, np.int64, np.bool_),
NumPy arrays, NaNs, infinities, and nested structures are cleanly converted
to standard native Python primitives (float, int, bool, str, list, dict)
before serialization by FastAPI jsonable_encoder.
"""
from typing import Any
import numpy as np


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively converts numpy scalars, arrays, and objects into native Python types.
    """
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except Exception:
            import base64
            return base64.b64encode(obj).decode("ascii")
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        val = float(obj)
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    if isinstance(obj, np.ndarray):
        return [sanitize_for_json(x) for x in obj.tolist()]
    if hasattr(obj, "detach") and callable(getattr(obj, "detach")):
        # PyTorch Tensor support
        return sanitize_for_json(obj.detach().cpu().numpy())
    if hasattr(obj, "tolist") and callable(getattr(obj, "tolist")):
        return [sanitize_for_json(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(v) for v in obj]
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        return sanitize_for_json(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return sanitize_for_json(obj.__dict__)
    return obj
