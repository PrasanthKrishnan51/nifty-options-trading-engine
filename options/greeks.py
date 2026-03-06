"""
Option Greeks Calculator — Black-Scholes (European options, no dividends).

Functions: delta, gamma, theta, vega, rho, implied_volatility, option_price
"""
from __future__ import annotations
import math
from typing import Literal

OptionSide = Literal["CE", "PE"]


def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

def _d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return _d1(S, K, T, r, sigma) - sigma * math.sqrt(T)

def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def option_price(S: float, K: float, T: float, r: float, sigma: float,
                 option_type: OptionSide = "CE") -> float:
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if option_type == "CE" else max(0.0, K - S)
    d1 = _d1(S, K, T, r, sigma); d2 = _d2(S, K, T, r, sigma)
    if option_type == "CE":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def delta(S: float, K: float, T: float, r: float, sigma: float,
          option_type: OptionSide = "CE") -> float:
    if T <= 0:
        return 1.0 if (option_type == "CE" and S > K) else 0.0
    d1 = _d1(S, K, T, r, sigma)
    return _norm_cdf(d1) if option_type == "CE" else _norm_cdf(d1) - 1


def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or S <= 0:
        return 0.0
    d1 = _d1(S, K, T, r, sigma)
    return _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def theta(S: float, K: float, T: float, r: float, sigma: float,
          option_type: OptionSide = "CE", days: bool = True) -> float:
    if T <= 0:
        return 0.0
    d1 = _d1(S, K, T, r, sigma); d2 = _d2(S, K, T, r, sigma)
    term1 = -S * _norm_pdf(d1) * sigma / (2 * math.sqrt(T))
    if option_type == "CE":
        th = term1 - r * K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        th = term1 + r * K * math.exp(-r * T) * _norm_cdf(-d2)
    return th / 365 if days else th


def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0:
        return 0.0
    d1 = _d1(S, K, T, r, sigma)
    return S * _norm_pdf(d1) * math.sqrt(T) / 100   # per 1% IV move


def rho(S: float, K: float, T: float, r: float, sigma: float,
        option_type: OptionSide = "CE") -> float:
    if T <= 0:
        return 0.0
    d2 = _d2(S, K, T, r, sigma)
    if option_type == "CE":
        return K * T * math.exp(-r * T) * _norm_cdf(d2) / 100
    return -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100


def implied_volatility(market_price: float, S: float, K: float, T: float, r: float,
                       option_type: OptionSide = "CE", tol: float = 1e-5,
                       max_iter: int = 100) -> float:
    """Newton-Raphson IV solver. Returns 0.0 on failure."""
    if T <= 0 or market_price <= 0:
        return 0.0
    sigma = 0.25
    for _ in range(max_iter):
        price = option_price(S, K, T, r, sigma, option_type)
        vg = vega(S, K, T, r, sigma) * 100   # undo per-1% scaling
        if abs(vg) < 1e-10:
            break
        sigma -= (price - market_price) / vg
        sigma = max(0.001, min(sigma, 5.0))
        if abs(price - market_price) < tol:
            return sigma
    return 0.0


def all_greeks(S: float, K: float, T: float, r: float, sigma: float,
               option_type: OptionSide = "CE") -> dict:
    return dict(
        price  = option_price(S, K, T, r, sigma, option_type),
        delta  = delta(S, K, T, r, sigma, option_type),
        gamma  = gamma(S, K, T, r, sigma),
        theta  = theta(S, K, T, r, sigma, option_type),
        vega   = vega(S, K, T, r, sigma),
        rho    = rho(S, K, T, r, sigma, option_type),
    )
