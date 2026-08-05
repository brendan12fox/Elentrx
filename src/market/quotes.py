"""Fetch live (delayed) stock quotes for alert tickers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def _yf():
    import yfinance as yf

    return yf


@dataclass
class StockQuote:
    ticker: str
    price: float | None
    change_pct: float | None
    change_abs: float | None
    previous_close: float | None
    market_cap: float | None
    currency: str = "USD"
    as_of: str = ""

    @property
    def available(self) -> bool:
        return self.price is not None


def _parse_fast_info(ticker: str, info) -> StockQuote | None:
    try:
        price = getattr(info, "last_price", None) or getattr(info, "regular_market_price", None)
        prev = getattr(info, "previous_close", None) or getattr(info, "regular_market_previous_close", None)
        if price is None and prev is None:
            return None
        price_f = float(price) if price is not None else None
        prev_f = float(prev) if prev is not None else None
        change_abs = None
        change_pct = None
        if price_f is not None and prev_f is not None and prev_f != 0:
            change_abs = price_f - prev_f
            change_pct = (change_abs / prev_f) * 100
        mcap = getattr(info, "market_cap", None)
        return StockQuote(
            ticker=ticker.upper(),
            price=price_f,
            change_pct=change_pct,
            change_abs=change_abs,
            previous_close=prev_f,
            market_cap=float(mcap) if mcap else None,
            currency=str(getattr(info, "currency", "USD") or "USD"),
            as_of=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )
    except (TypeError, ValueError, AttributeError):
        return None


def fetch_quote(ticker: str) -> StockQuote | None:
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    try:
        yf = _yf()
        parsed = _parse_fast_info(sym, yf.Ticker(sym).fast_info)
        if parsed:
            return parsed
    except Exception:
        pass
    try:
        yf = _yf()
        hist = yf.Ticker(sym).history(period="5d", interval="1d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        change_abs = price - prev
        change_pct = (change_abs / prev * 100) if prev else None
        return StockQuote(
            ticker=sym,
            price=price,
            change_pct=change_pct,
            change_abs=change_abs,
            previous_close=prev,
            market_cap=None,
            as_of=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )
    except Exception:
        return None


def fetch_quotes(tickers: list[str]) -> dict[str, StockQuote]:
    unique = sorted({(t or "").strip().upper() for t in tickers if t})
    return {sym: q for sym in unique if (q := fetch_quote(sym))}


def _fmt_price(price: float | None, currency: str = "USD") -> str:
    if price is None:
        return "—"
    sym = "$" if currency.upper() == "USD" else f"{currency} "
    if price >= 1000:
        return f"{sym}{price:,.2f}"
    return f"{sym}{price:.2f}"


def _fmt_change(change_pct: float | None, change_abs: float | None, currency: str = "USD") -> str:
    if change_pct is None:
        return ""
    sym = "$" if currency.upper() == "USD" else ""
    arrow = "▲" if change_pct >= 0 else "▼"
    sign = "+" if change_pct >= 0 else ""
    abs_part = f" ({sign}{sym}{change_abs:.2f})" if change_abs is not None else ""
    return f"{arrow} {sign}{change_pct:.2f}%{abs_part}"


def _fmt_mcap(mcap: float | None) -> str:
    if not mcap:
        return ""
    if mcap >= 1_000_000_000_000:
        return f" · MCap ${mcap / 1_000_000_000_000:.2f}T"
    if mcap >= 1_000_000_000:
        return f" · MCap ${mcap / 1_000_000_000:.1f}B"
    if mcap >= 1_000_000:
        return f" · MCap ${mcap / 1_000_000:.0f}M"
    return f" · MCap ${mcap:,.0f}"


def format_quote_text(quote: StockQuote | None) -> str:
    if not quote or not quote.available:
        return "Market: quote unavailable (delayed)"
    line = f"Market: {_fmt_price(quote.price, quote.currency)} {_fmt_change(quote.change_pct, quote.change_abs, quote.currency).strip()}"
    line += _fmt_mcap(quote.market_cap)
    line += f" · as of {quote.as_of} (delayed)"
    return line.strip()


def format_quote_html(quote: StockQuote | None) -> str:
    if not quote or not quote.available:
        return '<p style="color:#64748b;font-size:0.85rem;">Market quote unavailable</p>'
    direction = "up" if (quote.change_pct or 0) >= 0 else "down"
    color = "#059669" if direction == "up" else "#dc2626"
    change = _fmt_change(quote.change_pct, quote.change_abs, quote.currency)
    mcap = _fmt_mcap(quote.market_cap)
    return (
        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
        f'padding:12px 14px;margin:12px 0;">'
        f'<div style="font-size:1.1rem;font-weight:700;color:#0f172a;">'
        f'{quote.ticker} {_fmt_price(quote.price, quote.currency)}'
        f' <span style="color:{color};font-size:0.95rem;">{change}</span></div>'
        f'<div style="font-size:0.75rem;color:#64748b;margin-top:4px;">'
        f'Delayed quote{mcap} · {quote.as_of}</div></div>'
    )


def format_quote_chip(quote: StockQuote | None) -> str:
    """Compact inline HTML for cards."""
    if not quote or not quote.available:
        return ""
    direction = "up" if (quote.change_pct or 0) >= 0 else "down"
    change = _fmt_change(quote.change_pct, quote.change_abs, quote.currency)
    if direction == "up":
        style = "border-color:#a7f3d0;background:#ecfdf5;color:#047857;"
    else:
        style = "border-color:#fecaca;background:#fef2f2;color:#b91c1c;"
    base_style = (
        "display:inline-block;margin-top:0.35rem;border-radius:8px;"
        "padding:0.2rem 0.55rem;font-size:0.78rem;font-weight:600;border:1px solid;"
    )
    return (
        f'<span class="quote-chip quote-{direction}" style="{base_style}{style}">'
        f'{_fmt_price(quote.price, quote.currency)} {change}</span>'
    )
