"""
Pure-Python mathematical compatibility layer for NumPy.
Provides a drop-in fallback for core vector operations and statistical functions
when NumPy is not available in the runtime environment.
"""
# ruff: noqa: B905, UP035

from __future__ import annotations

import math
import sys
import types
from typing import Any, Sequence


class NdArray:
    """Pure-Python vector array emulating element-wise operations."""

    def __init__(self, data: Any, dtype: Any = None) -> None:
        if isinstance(data, NdArray):
            self._data = list(data._data)
        elif isinstance(data, (list, tuple)):
            self._data = [x._data[0] if isinstance(x, NdArray) and len(x) == 1 else x for x in data]
        else:
            self._data = [data]
        self.dtype = dtype or float

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, slice):
            return NdArray(self._data[item], dtype=self.dtype)
        elif isinstance(item, NdArray):
            return NdArray([v for v, m in zip(self._data, item._data) if m], dtype=self.dtype)
        elif isinstance(item, (list, tuple)):
            return NdArray([v for v, m in zip(self._data, item) if m], dtype=self.dtype)
        return self._data[item]

    def __setitem__(self, key: int, value: Any) -> None:
        self._data[key] = value

    def __abs__(self) -> NdArray:
        return NdArray([abs(x) for x in self._data], dtype=self.dtype)

    def __add__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a + b for a, b in zip(self._data, other)], dtype=self.dtype)
        return NdArray([a + other for a in self._data], dtype=self.dtype)

    def __radd__(self, other: Any) -> NdArray:
        return self.__add__(other)

    def __sub__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a - b for a, b in zip(self._data, other)], dtype=self.dtype)
        return NdArray([a - other for a in self._data], dtype=self.dtype)

    def __rsub__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([b - a for a, b in zip(self._data, other)], dtype=self.dtype)
        return NdArray([other - a for a in self._data], dtype=self.dtype)

    def __mul__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a * b for a, b in zip(self._data, other)], dtype=self.dtype)
        return NdArray([a * other for a in self._data], dtype=self.dtype)

    def __rmul__(self, other: Any) -> NdArray:
        return self.__mul__(other)

    def __truediv__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray(
                [a / b if b != 0 else 0.0 for a, b in zip(self._data, other)],
                dtype=self.dtype,
            )
        return NdArray(
            [a / other if other != 0 else 0.0 for a in self._data],
            dtype=self.dtype,
        )

    def __rtruediv__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray(
                [b / a if a != 0 else 0.0 for a, b in zip(self._data, other)],
                dtype=self.dtype,
            )
        return NdArray(
            [other / a if a != 0 else 0.0 for a in self._data],
            dtype=self.dtype,
        )

    def __gt__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a > b for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([a > other for a in self._data], dtype=bool)

    def __ge__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a >= b for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([a >= other for a in self._data], dtype=bool)

    def __lt__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a < b for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([a < other for a in self._data], dtype=bool)

    def __le__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a <= b for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([a <= other for a in self._data], dtype=bool)

    def __eq__(self, other: Any) -> NdArray:  # type: ignore[override]
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a == b for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([a == other for a in self._data], dtype=bool)

    def __ne__(self, other: Any) -> NdArray:  # type: ignore[override]
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([a != b for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([a != other for a in self._data], dtype=bool)

    def __and__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([bool(a and b) for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([bool(a and other) for a in self._data], dtype=bool)

    def __or__(self, other: Any) -> NdArray:
        if isinstance(other, (NdArray, list, tuple)):
            return NdArray([bool(a or b) for a, b in zip(self._data, other)], dtype=bool)
        return NdArray([bool(a or other) for a in self._data], dtype=bool)

    def tolist(self) -> list[Any]:
        return list(self._data)

    def copy(self) -> NdArray:
        return NdArray(list(self._data), dtype=self.dtype)

    def __repr__(self) -> str:
        return f"array({self._data})"


class MaximumHelper:
    """Emulates np.maximum and np.maximum.accumulate."""

    def __call__(self, a: Any, b: Any) -> Any:
        a_is_seq = hasattr(a, "__iter__") and not isinstance(a, (str, bytes))
        b_is_seq = hasattr(b, "__iter__") and not isinstance(b, (str, bytes))

        if a_is_seq and b_is_seq:
            return NdArray([max(x, y) for x, y in zip(a, b)])
        elif a_is_seq:
            return NdArray([max(x, b) for x in a])
        elif b_is_seq:
            return NdArray([max(a, y) for y in b])
        return max(a, b)

    def accumulate(self, arr: Sequence[Any]) -> NdArray:
        res = []
        cur = -float("inf")
        for x in arr:
            if x > cur:
                cur = x
            res.append(cur)
        return NdArray(res)


def array(data: Any, dtype: Any = None) -> NdArray:
    return NdArray(data, dtype=dtype)


def mean(data: Any) -> float:
    seq = list(data) if hasattr(data, "__iter__") else [data]
    if not seq:
        return 0.0
    return float(sum(seq) / len(seq))


def sum_(data: Any) -> float:
    seq = list(data) if hasattr(data, "__iter__") else [data]
    return float(sum(seq))


def var(data: Any, ddof: int = 0) -> float:
    seq = [float(x) for x in data] if hasattr(data, "__iter__") else [float(data)]
    n = len(seq)
    if n <= ddof:
        return 0.0
    m = sum(seq) / n
    return sum((x - m) ** 2 for x in seq) / (n - ddof)


def std(data: Any, ddof: int = 0) -> float:
    return math.sqrt(var(data, ddof=ddof))


def median(data: Any) -> float:
    seq = sorted([float(x) for x in data]) if hasattr(data, "__iter__") else [float(data)]
    n = len(seq)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return seq[mid]
    return (seq[mid - 1] + seq[mid]) / 2.0


def cumsum(data: Any) -> NdArray:
    seq = list(data) if hasattr(data, "__iter__") else [data]
    res = []
    total = 0.0
    for x in seq:
        total += float(x)
        res.append(total)
    return NdArray(res)


def max_(data: Any) -> float:
    seq = list(data) if hasattr(data, "__iter__") else [data]
    if not seq:
        return 0.0
    return float(max(seq))


def log(x: Any) -> Any:
    if hasattr(x, "__iter__") and not isinstance(x, (str, bytes)):
        return NdArray([math.log(v) for v in x])
    return math.log(x)


def sqrt(x: Any) -> Any:
    if hasattr(x, "__iter__") and not isinstance(x, (str, bytes)):
        return NdArray([math.sqrt(v) for v in x])
    return math.sqrt(x)


def where(cond: Any, x: Any, y: Any) -> NdArray:
    cond_list = list(cond) if hasattr(cond, "__iter__") else [cond]
    x_list = (
        list(x)
        if hasattr(x, "__iter__") and not isinstance(x, (str, bytes))
        else [x] * len(cond_list)
    )
    y_list = (
        list(y)
        if hasattr(y, "__iter__") and not isinstance(y, (str, bytes))
        else [y] * len(cond_list)
    )
    return NdArray([xv if c else yv for c, xv, yv in zip(cond_list, x_list, y_list)])


maximum = MaximumHelper()
float64 = float


def create_numpy_compat_module() -> types.ModuleType:
    """Create a module object mimicking numpy."""
    mod = types.ModuleType("numpy")
    mod.ndarray = NdArray  # type: ignore[attr-defined]
    mod.array = array  # type: ignore[attr-defined]
    mod.float64 = float64  # type: ignore[attr-defined]
    mod.mean = mean  # type: ignore[attr-defined]
    mod.std = std  # type: ignore[attr-defined]
    mod.var = var  # type: ignore[attr-defined]
    mod.sum = sum_  # type: ignore[attr-defined]
    mod.cumsum = cumsum  # type: ignore[attr-defined]
    mod.median = median  # type: ignore[attr-defined]
    mod.max = max_  # type: ignore[attr-defined]
    mod.maximum = maximum  # type: ignore[attr-defined]
    mod.log = log  # type: ignore[attr-defined]
    mod.sqrt = sqrt  # type: ignore[attr-defined]
    mod.where = where  # type: ignore[attr-defined]
    mod.__version__ = "2.2.0-purepython-compat"
    return mod


def register_numpy_compat() -> types.ModuleType:
    """Register numpy compatibility module in sys.modules if numpy is absent."""
    if "numpy" not in sys.modules:
        mod = create_numpy_compat_module()
        sys.modules["numpy"] = mod
        return mod
    return sys.modules["numpy"]


# Auto-register if numpy is not already present
if "numpy" not in sys.modules:
    try:
        import numpy  # noqa: F401
    except ImportError:
        register_numpy_compat()
