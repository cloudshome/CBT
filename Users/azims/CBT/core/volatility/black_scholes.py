"""
core/volatility/black_scholes.py
================================
Analytical Black-76 pricer, Greeks engine, and Newton-Raphson IV solver.
"""

from __future__ import annotations

import math
from typing import Any, Literal

SQRT_2PI = math.sqrt(2.0 * math.pi)


def norm_pdf(x: float) -> float:
    """Standard normal probability density function N'(x)."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function N(x) using erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_d1_d2(
    s: float,
    k: float,
    t: float,
    sigma: float,
    r: float = 0.0,
) -> tuple[float, float]:
    """
    Computes Black-76 / Black-Scholes d1 and d2 parameters.
    s: underlying / forward price
    k: strike price
    t: time to expiry in years (> 0)
    sigma: annualized volatility (> 0)
    r: risk-free rate (defaults to 0.0 for crypto futures/spot parity)
    """
    if t <= 0.0 or sigma <= 0.0 or s <= 0.0 or k <= 0.0:
        return 0.0, 0.0
    sigma_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    return d1, d2


def black_price(
    option_type: Literal["CALL", "PUT"],
    s: float,
    k: float,
    t: float,
    sigma: float,
    r: float = 0.0,
) -> float:
    """
    Computes Black-76 option premium.
    """
    if t <= 0.0:
        return max(0.0, s - k) if option_type == "CALL" else max(0.0, k - s)
    if sigma <= 0.0:
        return max(0.0, s - k) if option_type == "CALL" else max(0.0, k - s)

    d1, d2 = compute_d1_d2(s, k, t, sigma, r)
    df = math.exp(-r * t)

    if option_type == "CALL":
        return df * (s * norm_cdf(d1) - k * norm_cdf(d2))
    else:
        return df * (k * norm_cdf(-d2) - s * norm_cdf(-d1))


def compute_greeks(
    option_type: Literal["CALL", "PUT"],
    s: float,
    k: float,
    t: float,
    sigma: float,
    r: float = 0.0,
) -> dict[str, float]:
    """
    Returns delta, gamma, and vega.
    """
    if t <= 1e-6 or sigma <= 1e-6 or s <= 1e-6 or k <= 1e-6:
        intrinsic = 1.0 if s >= k else 0.0
        delta = intrinsic if option_type == "CALL" else intrinsic - 1.0
        return {"delta": delta, "gamma": 0.0, "vega": 0.0}

    d1, _ = compute_d1_d2(s, k, t, sigma, r)
    pdf_d1 = norm_pdf(d1)
    sqrt_t = math.sqrt(t)
    df = math.exp(-r * t)

    if option_type == "CALL":
        delta = df * norm_cdf(d1)
    else:
        delta = df * (norm_cdf(d1) - 1.0)

    gamma = (df * pdf_d1) / (s * sigma * sqrt_t) if (s * sigma * sqrt_t) > 0 else 0.0
    vega = s * df * pdf_d1 * sqrt_t  # Dollar vega per 100% vol change

    return {
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
    }


def find_implied_volatility(
    option_type: Literal["CALL", "PUT"],
    target_price: float,
    s: float,
    k: float,
    t: float,
    r: float = 0.0,
    max_iter: int = 50,
    tol: float = 1e-5,
) -> float:
    """
    Finds implied volatility via Newton-Raphson with bisection fallback.
    """
    # Lower bound check (intrinsic value)
    intrinsic = max(0.0, s - k) if option_type == "CALL" else max(0.0, k - s)
    if target_price <= intrinsic:
        return 0.01

    # Initial guess: Brenner-Subrahmanyam approximation for ATM
    sigma = math.sqrt(2.0 * math.pi / max(1e-4, t)) * (target_price / s)
    sigma = max(0.05, min(3.0, sigma))

    low = 0.001
    high = 8.0

    for _ in range(max_iter):
        price = black_price(option_type, s, k, t, sigma, r)
        diff = price - target_price
        if abs(diff) < tol:
            return round(sigma, 6)

        greeks = compute_greeks(option_type, s, k, t, sigma, r)
        vega = greeks["vega"]

        if vega > 1e-4:
            sigma_new = sigma - diff / vega
            if low <= sigma_new <= high:
                sigma = sigma_new
                continue

        # Bisection fallback
        if diff > 0:
            high = sigma
        else:
            low = sigma
    return round(sigma, 6)


from dataclasses import dataclass


@dataclass
class OptionGreeks:
    delta: float
    gamma: float
    vega: float
    theta: float = 0.0


def black76_price(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    option_type: Any = "CALL",
) -> float:
    opt = option_type.value if hasattr(option_type, "value") else str(option_type)
    return black_price(opt, s, k, t, sigma, r)


def black76_greeks(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    option_type: Any = "CALL",
) -> OptionGreeks:
    opt = option_type.value if hasattr(option_type, "value") else str(option_type)
    res = compute_greeks(opt, s, k, t, sigma, r)
    return OptionGreeks(
        delta=res["delta"],
        gamma=res["gamma"],
        vega=res["vega"],
        theta=0.0,
    )


def implied_volatility(
    target_price: float,
    s: float,
    k: float,
    t: float,
    r: float = 0.0,
    option_type: Any = "CALL",
) -> float:
    opt = option_type.value if hasattr(option_type, "value") else str(option_type)
    return find_implied_volatility(opt, target_price, s, k, t, r)
