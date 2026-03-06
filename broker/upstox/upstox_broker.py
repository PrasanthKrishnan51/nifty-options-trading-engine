"""
Upstox API v2 Broker Adapter.

Full implementation covering:
  - OAuth2 access-token flow (auto-refresh)
  - REST endpoints: quotes, OHLCV history, option chain, orders, positions, funds
  - WebSocket streaming (upstox_client Market Data Feeder)
  - Order lifecycle: place, modify, cancel, status polling
  - Position & portfolio management
  - Margin & brokerage calculation

Install:
    pip install upstox-python-sdk websocket-client requests

Environment variables:
    UPSTOX_API_KEY        — from Upstox developer portal
    UPSTOX_API_SECRET     — from Upstox developer portal
    UPSTOX_REDIRECT_URI   — registered redirect (e.g. https://127.0.0.1/)
    UPSTOX_ACCESS_TOKEN   — set after completing OAuth2 login
    UPSTOX_RTOKEN         — optional: refresh token for auto-renewal

Reference: https://upstox.com/developer/api-documentation/
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import pandas as pd
import requests

from broker.base_broker import BaseBroker
from config.settings import config
from core.models import (
    Order, OrderSide, OrderStatus, OrderType,
    Position, PositionStatus, Tick,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.upstox.com/v2"
_AUTH_URL  = "https://api.upstox.com/v2/login/authorization/token"


class UpstoxBroker(BaseBroker):
    """
    Production-ready Upstox API v2 adapter.

    Implements every method of BaseBroker so the rest of the system
    remains 100% broker-agnostic.

    Instrument key format: NSE_FO|<token>  or  NSE_INDEX|Nifty 50
    """

    INTERVAL_MAP: Dict[str, str] = {
        "minute":   "1minute",
        "3minute":  "3minute",
        "5minute":  "5minute",
        "10minute": "10minute",
        "15minute": "15minute",
        "30minute": "30minute",
        "60minute": "60minute",
        "day":      "day",
        "week":     "week",
        "month":    "month",
    }

    _PRODUCT_MAP    = {"MIS": "I", "NRML": "D", "CNC": "D"}
    _ORDER_TYPE_MAP = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT:  "LIMIT",
        OrderType.SL:     "SL",
        OrderType.SL_M:   "SL-M",
    }
    _STATUS_MAP = {
        "complete":                       OrderStatus.COMPLETE,
        "open":                           OrderStatus.OPEN,
        "open pending":                   OrderStatus.OPEN,
        "not modified":                   OrderStatus.OPEN,
        "trigger pending":                OrderStatus.OPEN,
        "put order req received":         OrderStatus.PENDING,
        "cancelled":                      OrderStatus.CANCELLED,
        "rejected":                       OrderStatus.REJECTED,
        "validation pending":             OrderStatus.PENDING,
        "modify pending":                 OrderStatus.OPEN,
        "after market order req received": OrderStatus.PENDING,
    }

    _INDEX_KEY_MAP = {
        "NIFTY":     "NSE_INDEX|Nifty 50",
        "NIFTY 50":  "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "NIFTY BANK":"NSE_INDEX|Nifty Bank",
        "FINNIFTY":  "NSE_INDEX|Nifty Fin Service",
        "MIDCPNIFTY":"NSE_INDEX|NIFTY MID SELECT",
        "SENSEX":    "BSE_INDEX|SENSEX",
    }

    def __init__(self) -> None:
        super().__init__("upstox")
        self._session = requests.Session()
        self._session.headers.update({
            "Accept":       "application/json",
            "Content-Type": "application/json",
        })
        self._access_token: Optional[str] = None
        self._ws: Any = None
        self._ws_thread: Optional[threading.Thread] = None
        self._instruments: pd.DataFrame = pd.DataFrame()
        self._token_map:   Dict[str, str] = {}   # tradingsymbol.upper() -> instrument_key
        self._lock = threading.Lock()

    # ─── Connection ──────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Authenticate with Upstox.

        Priority:
          1. UPSTOX_ACCESS_TOKEN env var (direct)
          2. UPSTOX_RTOKEN env var (refresh flow)
          3. Print OAuth2 URL for manual browser login
        """
        cfg = config.upstox

        if cfg.access_token:
            self._access_token = cfg.access_token
            self._set_auth_header()
            if self._validate_token():
                self._connected = True
                self._load_instruments()
                logger.info("Upstox: connected via access token.")
                return True
            logger.warning("Upstox: cached token invalid, trying refresh...")

        if cfg.rtoken:
            if self._refresh_access_token(cfg.rtoken):
                self._connected = True
                self._load_instruments()
                return True

        auth_url = self._build_auth_url(cfg.api_key, cfg.redirect_uri)
        logger.warning(
            "\n%s\n"
            "  Upstox access token missing.\n"
            "  1. Visit: %s\n"
            "  2. Copy the 'code' from the redirect URL.\n"
            "  3. Call exchange_code_for_token(code) OR set UPSTOX_ACCESS_TOKEN.\n"
            "%s",
            "=" * 72, auth_url, "=" * 72,
        )
        return False

    def disconnect(self) -> None:
        self._stop_ws()
        self._connected = False
        logger.info("Upstox: disconnected.")

    # ─── Auth helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_auth_url(api_key: str, redirect_uri: str) -> str:
        params = {
            "client_id":     api_key,
            "redirect_uri":  redirect_uri,
            "response_type": "code",
        }
        return f"https://api.upstox.com/v2/login/authorization/dialog?{urlencode(params)}"

    def exchange_code_for_token(self, auth_code: str) -> Optional[str]:
        """Exchange one-time auth code for access_token after browser login."""
        cfg = config.upstox
        try:
            resp = requests.post(_AUTH_URL, data={
                "code":          auth_code,
                "client_id":     cfg.api_key,
                "client_secret": cfg.api_secret,
                "redirect_uri":  cfg.redirect_uri,
                "grant_type":    "authorization_code",
            }, timeout=15)
            resp.raise_for_status()
            token = resp.json().get("access_token")
            if token:
                self._access_token = token
                self._set_auth_header()
                logger.info("Upstox: access token obtained.")
            return token
        except Exception as exc:
            logger.exception("Upstox token exchange failed: %s", exc)
            return None

    def _refresh_access_token(self, refresh_token: str) -> bool:
        cfg = config.upstox
        try:
            resp = requests.post(_AUTH_URL, data={
                "refresh_token": refresh_token,
                "client_id":     cfg.api_key,
                "client_secret": cfg.api_secret,
                "grant_type":    "refresh_token",
            }, timeout=15)
            resp.raise_for_status()
            token = resp.json().get("access_token")
            if token:
                self._access_token = token
                self._set_auth_header()
                logger.info("Upstox: token refreshed.")
                return True
        except Exception as exc:
            logger.warning("Upstox token refresh failed: %s", exc)
        return False

    def _set_auth_header(self) -> None:
        self._session.headers["Authorization"] = f"Bearer {self._access_token}"

    def _validate_token(self) -> bool:
        try:
            resp = self._get("/user/profile")
            return bool(resp and resp.get("status") == "success")
        except Exception:
            return False

    # ─── REST helpers ────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        try:
            r = self._session.get(f"{_BASE_URL}{path}", params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as exc:
            logger.error("Upstox GET %s → %s: %s", path, exc.response.status_code, exc.response.text[:200])
        except Exception as exc:
            logger.error("Upstox GET %s failed: %s", path, exc)
        return None

    def _post(self, path: str, payload: Dict) -> Optional[Dict]:
        try:
            r = self._session.post(f"{_BASE_URL}{path}", json=payload, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as exc:
            logger.error("Upstox POST %s → %s: %s", path, exc.response.status_code, exc.response.text[:200])
        except Exception as exc:
            logger.error("Upstox POST %s failed: %s", path, exc)
        return None

    def _put(self, path: str, payload: Dict) -> Optional[Dict]:
        try:
            r = self._session.put(f"{_BASE_URL}{path}", json=payload, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.error("Upstox PUT %s failed: %s", path, exc)
        return None

    def _delete(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        try:
            r = self._session.delete(f"{_BASE_URL}{path}", params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.error("Upstox DELETE %s failed: %s", path, exc)
        return None

    # ─── Instrument master ───────────────────────────────────────────────────

    def _load_instruments(self) -> None:
        """Download NSE + NFO instrument master CSV from Upstox CDN."""
        urls = [
            "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz",
            "https://assets.upstox.com/market-quote/instruments/exchange/NFO.csv.gz",
        ]
        dfs: List[pd.DataFrame] = []
        for url in urls:
            try:
                df = pd.read_csv(url, compression="gzip")
                dfs.append(df)
                logger.debug("Upstox: loaded %d rows from %s", len(df), url)
            except Exception as exc:
                logger.warning("Upstox: failed to load instruments from %s: %s", url, exc)

        if dfs:
            self._instruments = pd.concat(dfs, ignore_index=True)
            if {"tradingsymbol", "instrument_key"}.issubset(self._instruments.columns):
                self._token_map = dict(
                    zip(
                        self._instruments["tradingsymbol"].str.upper(),
                        self._instruments["instrument_key"],
                    )
                )
            logger.info("Upstox: loaded %d instruments.", len(self._instruments))
        else:
            logger.warning("Upstox: instrument master unavailable (network issue?).")

    def get_instrument_key(self, symbol: str, exchange: str = "NSE_FO") -> Optional[str]:
        """Resolve trading symbol to Upstox instrument_key."""
        sym_upper = symbol.upper()
        # Check index map first
        if sym_upper in self._INDEX_KEY_MAP:
            return self._INDEX_KEY_MAP[sym_upper]
        # Check loaded instrument map
        key = self._token_map.get(sym_upper)
        if key:
            return key
        # Fallback: construct key from exchange prefix + symbol
        exchange_prefix = {
            "NSE": "NSE_EQ", "NFO": "NSE_FO",
            "BSE": "BSE_EQ", "BFO": "BSE_FO",
            "MCX": "MCX_FO",
        }
        prefix = exchange_prefix.get(exchange.upper(), exchange)
        logger.debug("Upstox: constructed fallback key %s|%s", prefix, symbol)
        return f"{prefix}|{symbol}"

    # ─── Market Data ─────────────────────────────────────────────────────────

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Optional[Tick]:
        """Real-time full market quote (LTP, bid, ask, OI, volume)."""
        instrument_key = self.get_instrument_key(symbol, exchange)
        if not instrument_key:
            return None
        try:
            resp = self._get("/market-quote/quotes",
                             params={"instrument_key": instrument_key})
            if not resp or resp.get("status") != "success":
                return None
            data: Dict = resp.get("data", {}).get(instrument_key, {})
            depth   = data.get("depth", {})
            buy_0   = depth.get("buy",  [{}])[0]
            sell_0  = depth.get("sell", [{}])[0]
            return Tick(
                symbol=symbol,
                ltp=float(data.get("last_price", 0)),
                bid=float(buy_0.get("price",  0)),
                ask=float(sell_0.get("price", 0)),
                volume=int(data.get("volume", 0)),
                oi=int(data.get("oi", 0)),
                timestamp=datetime.now(),
            )
        except Exception as exc:
            logger.error("Upstox get_quote failed (%s): %s", symbol, exc)
            return None

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Optional[float]:
        """Lightweight LTP-only fetch."""
        instrument_key = self.get_instrument_key(symbol, exchange)
        if not instrument_key:
            return None
        try:
            resp = self._get("/market-quote/ltp",
                             params={"instrument_key": instrument_key})
            if resp and resp.get("status") == "success":
                return float(resp["data"].get(instrument_key, {}).get("last_price", 0))
        except Exception as exc:
            logger.error("Upstox get_ltp failed: %s", exc)
        return None

    def get_historical_data(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        from_date: datetime,
        to_date: datetime,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles.

        Upstox candle schema: [timestamp, open, high, low, close, volume, oi]
        Auto-selects intraday vs historical endpoint based on date range.
        """
        instrument_key = self.get_instrument_key(symbol, exchange)
        if not instrument_key:
            logger.error("Upstox: no instrument_key for %s:%s", exchange, symbol)
            return pd.DataFrame()

        try:
            upstox_interval = self.INTERVAL_MAP.get(interval, "1minute")
            # Encode '|' so it is safe in URL paths
            encoded_key = instrument_key.replace("|", "%7C")

            is_intraday = (
                interval not in ("day", "week", "month")
                and from_date.date() == datetime.now().date()
            )

            if is_intraday:
                path = f"/historical-candle/intraday/{encoded_key}/{upstox_interval}"
                resp = self._get(path)
            else:
                from_str = from_date.strftime("%Y-%m-%d")
                to_str   = to_date.strftime("%Y-%m-%d")
                path = f"/historical-candle/{encoded_key}/{upstox_interval}/{to_str}/{from_str}"
                resp = self._get(path)

            if not resp or resp.get("status") != "success":
                logger.warning("Upstox: empty candle data for %s", symbol)
                return pd.DataFrame()

            candles = resp.get("data", {}).get("candles", [])
            if not candles:
                return pd.DataFrame()

            df = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume", "oi"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
            for col in ("open", "high", "low", "close"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
            return df[["open", "high", "low", "close", "volume"]]

        except Exception as exc:
            logger.exception("Upstox get_historical_data failed: %s", exc)
            return pd.DataFrame()

    def get_option_chain(
        self, underlying: str, expiry: datetime
    ) -> List[Dict[str, Any]]:
        """
        Fetch full option chain via Upstox /option/chain endpoint.

        Returns list of dicts with strike, option_type, ltp, greeks, OI, volume.
        """
        try:
            instrument_key = self._INDEX_KEY_MAP.get(underlying.upper())
            if not instrument_key:
                logger.warning("Upstox option chain: unknown underlying '%s'", underlying)
                return []

            expiry_str = expiry.strftime("%Y-%m-%d")
            resp = self._get("/option/chain", params={
                "instrument_key": instrument_key,
                "expiry_date":    expiry_str,
            })
            if not resp or resp.get("status") != "success":
                return []

            result: List[Dict[str, Any]] = []
            for entry in resp.get("data", []):
                for opt_type, key in (("CE", "call_options"), ("PE", "put_options")):
                    opt = entry.get(key)
                    if not opt:
                        continue
                    md  = opt.get("market_data", {})
                    grk = opt.get("option_greeks", {})
                    result.append({
                        "instrument_key": opt.get("instrument_key", ""),
                        "tradingsymbol":  opt.get("tradingsymbol", ""),
                        "strike":         float(entry.get("strike_price", 0)),
                        "option_type":    opt_type,
                        "expiry":         expiry_str,
                        "ltp":            float(md.get("ltp",       0)),
                        "bid":            float(md.get("bid_price", 0)),
                        "ask":            float(md.get("ask_price", 0)),
                        "iv":             float(grk.get("iv",    0)),
                        "delta":          float(grk.get("delta", 0)),
                        "theta":          float(grk.get("theta", 0)),
                        "vega":           float(grk.get("vega",  0)),
                        "gamma":          float(grk.get("gamma", 0)),
                        "oi":             int(md.get("oi",     0)),
                        "volume":         int(md.get("volume", 0)),
                    })
            logger.info("Upstox option chain: %d contracts for %s %s",
                        len(result), underlying, expiry_str)
            return result

        except Exception as exc:
            logger.exception("Upstox get_option_chain failed: %s", exc)
            return []

    def get_market_status(self) -> Dict[str, Any]:
        """Check NSE market open/closed status."""
        resp = self._get("/market/status/NSE")
        if resp and resp.get("status") == "success":
            return resp.get("data", {})
        return {}

    # ─── WebSocket Streaming ─────────────────────────────────────────────────

    def subscribe(
        self, symbols: List[str], callback: Callable[[Tick], None]
    ) -> None:
        """
        Subscribe to live ticks using Upstox WebSocket.

        Tries upstox-python-sdk first; falls back to raw websocket-client.
        """
        self._tick_callbacks.append(callback)
        instrument_keys = [
            k for s in symbols
            if (k := self.get_instrument_key(s))
        ]
        if not instrument_keys:
            logger.warning("Upstox subscribe: no valid instrument keys found.")
            return

        try:
            import upstox_client  # type: ignore
            cfg_sdk = upstox_client.Configuration(access_token=self._access_token)
            streamer = upstox_client.MarketDataStreamer(cfg_sdk, instrument_keys, "full")

            def _on_message(_ws: Any, message: str) -> None:
                try:
                    feeds = json.loads(message).get("feeds", {})
                    for ikey, feed in feeds.items():
                        ff   = feed.get("ff", {})
                        mff  = ff.get("marketFF", ff.get("indexFF", {}))
                        ltpc = mff.get("ltpc", {})
                        tick = Tick(
                            symbol=ikey,
                            ltp=float(ltpc.get("ltp", 0)),
                            volume=int(mff.get("vttq", {}).get("vtt", 0)),
                            oi=int(mff.get("oi", {}).get("oi", 0)),
                            timestamp=datetime.now(),
                        )
                        for cb in self._tick_callbacks:
                            cb(tick)
                except Exception:
                    pass

            streamer.on_message = _on_message
            self._ws_thread = threading.Thread(target=streamer.connect, daemon=True)
            self._ws_thread.start()
            logger.info("Upstox: SDK streamer started (%d keys).", len(instrument_keys))

        except ImportError:
            self._ws_raw_subscribe(instrument_keys)

    def _ws_raw_subscribe(self, instrument_keys: List[str]) -> None:
        """Fallback: raw websocket-client library."""
        try:
            import websocket  # type: ignore
        except ImportError:
            logger.error("Install websocket-client: pip install websocket-client")
            return

        ws_url = (
            "wss://api.upstox.com/v2/feed/market-data-feed"
            f"?access_token={self._access_token}"
        )

        def _on_message(ws: Any, msg: Any) -> None:
            try:
                data = json.loads(msg) if isinstance(msg, str) else {}
                for ikey, feed in data.get("feeds", {}).items():
                    ltp_val = (
                        feed.get("ff", {})
                            .get("marketFF", feed.get("ff", {}).get("indexFF", {}))
                            .get("ltpc", {}).get("ltp", 0)
                    )
                    tick = Tick(symbol=ikey, ltp=float(ltp_val), timestamp=datetime.now())
                    for cb in self._tick_callbacks:
                        cb(tick)
            except Exception:
                pass

        def _on_open(ws: Any) -> None:
            ws.send(json.dumps({
                "guid":   "sub-001",
                "method": "sub",
                "data":   {"mode": "full", "instrumentKeys": instrument_keys},
            }))
            logger.info("Upstox WS raw: subscribed %d keys.", len(instrument_keys))

        def _on_error(ws: Any, err: Any) -> None:
            logger.error("Upstox WS error: %s", err)

        def _on_close(ws: Any, code: Any, msg: Any) -> None:
            logger.warning("Upstox WS closed: %s %s", code, msg)

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_message=_on_message,
            on_open=_on_open,
            on_error=_on_error,
            on_close=_on_close,
            header={"Accept": "application/json"},
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 30, "ping_timeout": 10},
            daemon=True,
        )
        self._ws_thread.start()

    def _stop_ws(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._ws = None

    def unsubscribe(self, symbols: List[str]) -> None:
        if not self._ws:
            return
        keys = [k for s in symbols if (k := self.get_instrument_key(s))]
        try:
            self._ws.send(json.dumps({
                "guid": "unsub-001", "method": "unsub",
                "data": {"mode": "full", "instrumentKeys": keys},
            }))
        except Exception as exc:
            logger.error("Upstox unsubscribe failed: %s", exc)

    # ─── Orders ──────────────────────────────────────────────────────────────

    def place_order(self, order: Order) -> Order:
        """Place a new order. Maps our Order model to Upstox v2 payload."""
        try:
            instrument_key = self.get_instrument_key(order.symbol, order.exchange)
            if not instrument_key:
                raise ValueError(f"No instrument_key for {order.symbol}")

            payload: Dict[str, Any] = {
                "quantity":           order.quantity,
                "product":            self._PRODUCT_MAP.get(order.product, "I"),
                "validity":           order.validity,
                "price":              order.price,
                "tag":                (order.tag or "")[:20],
                "instrument_token":   instrument_key,
                "order_type":         self._ORDER_TYPE_MAP.get(order.order_type, "MARKET"),
                "transaction_type":   order.side.value,
                "disclosed_quantity": 0,
                "trigger_price":      order.trigger_price,
                "is_amo":             False,
            }

            resp = self._post("/order/place", payload)
            if resp and resp.get("status") == "success":
                order.broker_order_id = str(resp.get("data", {}).get("order_id", ""))
                order.status = OrderStatus.OPEN
                logger.info("Upstox order placed | %s | id=%s",
                            order.symbol, order.broker_order_id)
            else:
                order.status = OrderStatus.REJECTED
                order.error_message = (resp or {}).get("message", "No response")
                logger.error("Upstox order rejected: %s", order.error_message)

        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.error_message = str(exc)
            logger.exception("Upstox place_order failed: %s", exc)
        return order

    def modify_order(self, order: Order) -> Order:
        """Modify price / quantity / type of an open order."""
        try:
            resp = self._put("/order/modify", {
                "order_id":           order.broker_order_id,
                "quantity":           order.quantity,
                "validity":           order.validity,
                "price":              order.price,
                "order_type":         self._ORDER_TYPE_MAP.get(order.order_type, "LIMIT"),
                "trigger_price":      order.trigger_price,
                "disclosed_quantity": 0,
            })
            if resp and resp.get("status") == "success":
                logger.info("Upstox order modified: %s", order.broker_order_id)
        except Exception as exc:
            logger.exception("Upstox modify_order failed: %s", exc)
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by broker order id."""
        try:
            resp = self._delete("/order/cancel", params={"order_id": order_id})
            if resp and resp.get("status") == "success":
                logger.info("Upstox order cancelled: %s", order_id)
                return True
        except Exception as exc:
            logger.exception("Upstox cancel_order failed: %s", exc)
        return False

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Poll the status of a specific order."""
        try:
            resp = self._get("/order/details", params={"order_id": order_id})
            if resp and resp.get("status") == "success":
                raw = str(resp["data"].get("status", "")).lower()
                return self._STATUS_MAP.get(raw, OrderStatus.PENDING)
        except Exception as exc:
            logger.error("Upstox get_order_status failed: %s", exc)
        return OrderStatus.PENDING

    def get_orders(self) -> List[Order]:
        """Retrieve all orders for today's session."""
        try:
            resp = self._get("/order/retrieve-all")
            if resp and resp.get("status") == "success":
                return [self._raw_to_order(o) for o in (resp.get("data") or [])]
        except Exception as exc:
            logger.error("Upstox get_orders failed: %s", exc)
        return []

    def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """State-change history for a specific order."""
        try:
            resp = self._get("/order/history", params={"order_id": order_id})
            if resp and resp.get("status") == "success":
                return resp.get("data", [])
        except Exception as exc:
            logger.error("Upstox get_order_history failed: %s", exc)
        return []

    def get_trades(self) -> List[Dict[str, Any]]:
        """All executed trades for today."""
        try:
            resp = self._get("/order/trades/get-trades-for-day")
            if resp and resp.get("status") == "success":
                return resp.get("data", [])
        except Exception as exc:
            logger.error("Upstox get_trades failed: %s", exc)
        return []

    # ─── Positions & Portfolio ────────────────────────────────────────────────

    def get_positions(self) -> List[Position]:
        """Retrieve all open intraday (short-term) positions."""
        try:
            resp = self._get("/portfolio/short-term-positions")
            if not resp or resp.get("status") != "success":
                return []
            positions: List[Position] = []
            for p in (resp.get("data") or []):
                net_qty = int(p.get("quantity", 0))
                if net_qty == 0:
                    continue
                positions.append(Position(
                    symbol=p.get("tradingsymbol", ""),
                    exchange=p.get("exchange", "NFO"),
                    quantity=abs(net_qty),
                    entry_price=float(p.get("average_price", 0.0)),
                    status=PositionStatus.OPEN,
                ))
            return positions
        except Exception as exc:
            logger.error("Upstox get_positions failed: %s", exc)
            return []

    def get_portfolio(self) -> Dict[str, Any]:
        """Combined portfolio: long-term holdings + short-term positions."""
        try:
            holdings_resp = self._get("/portfolio/long-term-holdings")
            holdings = (holdings_resp or {}).get("data", []) \
                if (holdings_resp or {}).get("status") == "success" else []
            return {
                "holdings":  holdings,
                "positions": [
                    {"symbol": p.symbol, "qty": p.quantity, "avg_price": p.entry_price}
                    for p in self.get_positions()
                ],
            }
        except Exception as exc:
            logger.error("Upstox get_portfolio failed: %s", exc)
            return {}

    def get_funds(self) -> Dict[str, float]:
        """Available margin and used margin."""
        try:
            resp = self._get("/user/get-funds-and-margin")
            if resp and resp.get("status") == "success":
                eq = resp.get("data", {}).get("equity", {})
                available = float(eq.get("available_margin", 0))
                used      = float(eq.get("used_margin",      0))
                total     = float(eq.get("net_margin",       available + used))
                return {"available": available, "used": used, "total": total}
        except Exception as exc:
            logger.error("Upstox get_funds failed: %s", exc)
        return {"available": 0.0, "used": 0.0, "total": 0.0}

    # ─── Margin & Brokerage ───────────────────────────────────────────────────

    def get_required_margin(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        transaction_type: str = "BUY",
        product: str = "I",
        price: float = 0.0,
    ) -> Optional[float]:
        """Calculate required margin before order placement."""
        instrument_key = self.get_instrument_key(symbol, exchange)
        if not instrument_key:
            return None
        try:
            resp = self._post("/charges/margin", {"instruments": [{
                "instrument_key":   instrument_key,
                "quantity":         quantity,
                "transaction_type": transaction_type,
                "product":          product,
                "price":            price,
            }]})
            if resp and resp.get("status") == "success":
                return float(resp["data"].get("required_margin", 0))
        except Exception as exc:
            logger.error("Upstox get_required_margin failed: %s", exc)
        return None

    def get_brokerage(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: float,
        transaction_type: str = "BUY",
        product: str = "I",
    ) -> Optional[Dict[str, float]]:
        """Brokerage + statutory charges breakdown."""
        instrument_key = self.get_instrument_key(symbol, exchange)
        if not instrument_key:
            return None
        try:
            resp = self._get("/charges/brokerage", params={
                "instrument_token": instrument_key,
                "quantity":         quantity,
                "product":          product,
                "transaction_type": transaction_type,
                "price":            price,
            })
            if resp and resp.get("status") == "success":
                return resp.get("data", {})
        except Exception as exc:
            logger.error("Upstox get_brokerage failed: %s", exc)
        return None

    # ─── User profile ─────────────────────────────────────────────────────────

    def get_profile(self) -> Dict[str, Any]:
        """Return authenticated user's profile."""
        try:
            resp = self._get("/user/profile")
            if resp and resp.get("status") == "success":
                return resp.get("data", {})
        except Exception as exc:
            logger.error("Upstox get_profile failed: %s", exc)
        return {}

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _raw_to_order(self, raw: Dict) -> Order:
        """Map Upstox raw order JSON to internal Order model."""
        raw_status = str(raw.get("status", "")).lower()
        return Order(
            symbol=raw.get("tradingsymbol", ""),
            exchange=raw.get("exchange", ""),
            side=OrderSide.BUY if raw.get("transaction_type") == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=int(raw.get("quantity", 0)),
            price=float(raw.get("price", 0)),
            trigger_price=float(raw.get("trigger_price", 0)),
            broker_order_id=str(raw.get("order_id", "")),
            status=self._STATUS_MAP.get(raw_status, OrderStatus.PENDING),
            filled_qty=int(raw.get("filled_quantity", 0)),
            avg_price=float(raw.get("average_price", 0)),
            tag=raw.get("tag", ""),
            error_message=raw.get("status_message"),
        )

    def get_instrument_token(self, symbol: str, exchange: str) -> Optional[int]:
        """Compatibility shim — returns numeric part of instrument_key."""
        key = self.get_instrument_key(symbol, exchange)
        if key and "|" in key:
            try:
                return int(key.split("|")[1])
            except ValueError:
                pass
        return None
