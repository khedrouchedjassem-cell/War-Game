"""
GPU utilities: detect GPU availability and provide a unified array module (xp)
Supports CuPy when available, otherwise falls back to NumPy.
"""
from typing import Tuple

try:
    import cupy as cp
    _CUPY_AVAILABLE = True
except Exception:
    cp = None
    _CUPY_AVAILABLE = False

import numpy as np


def detect_gpu() -> Tuple[bool, str]:
    """Detect whether a CUDA GPU is available and return (available, provider_str).

    Returns:
        (True, 'cupy') if CuPy is available and a device can be used, otherwise (False, 'numpy').
    """
    if not _CUPY_AVAILABLE:
        return False, 'numpy'

    try:
        # Try a quick allocation to confirm device availability
        _ = cp.zeros(1)
        return True, 'cupy'
    except Exception:
        return False, 'numpy'


def get_xp(prefer_gpu: bool = True):
    """Return an array module compatible with NumPy API: cupy if available and preferred, else numpy.

    Usage:
        xp = get_xp()
        arr = xp.array([...])
    """
    if prefer_gpu and _CUPY_AVAILABLE:
        try:
            # Quick smoke test
            _ = cp.zeros(1)
            return cp
        except Exception:
            return np
    return np


def to_cpu(x):
    """Transfer array x to host (NumPy). Works for NumPy and CuPy arrays."""
    if _CUPY_AVAILABLE and hasattr(x, 'get'):
        try:
            return x.get()
        except Exception:
            return np.array(x)
    return np.array(x)


def from_cpu(x, use_gpu: bool = True):
    """Convert a NumPy array to GPU array if requested and available."""
    if use_gpu and _CUPY_AVAILABLE:
        try:
            return cp.asarray(x)
        except Exception:
            return np.array(x)
    return np.array(x)
