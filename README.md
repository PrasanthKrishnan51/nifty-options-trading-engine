# 🏦 Options Algo Trader
### Institutional-Grade Python Algorithmic Trading System for Indian Options Markets

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![Brokers](https://img.shields.io/badge/Brokers-Zerodha%20|%20AngelOne%20|%20Fyers%20|%20Upstox-orange)]()
[![Architecture](https://img.shields.io/badge/Architecture-Hedge--Fund%20Grade-gold)]()

---

## 📁 Project Structure

```
options_trader/
│
├── main.py                          # Entry point (live | backtest | api | demo)
├── requirements.txt
├── .env.example                     # → copy to .env
│
├── config/
│   └── settings.py                  # AppConfig — all env-driven, zero hardcoding
│
├── core/
│   └── models.py                    # Domain models: OHLCV, Signal, Order, Position, Trade
│
├── broker/                          # ── BROKER ABSTRACTION LAYER ──
│   ├── base_broker.py               # Abstract BaseBroker (12 abstract methods)
│   ├── factory.py                   # get_broker() factory
│   ├── zerodha/
│   │   └── kite_broker.py           # Zerodha KiteConnect (REST + WS)
│   ├── angelone/
│   │   └── angel_broker.py          # Angel One SmartAPI + TOTP
│   ├── fyers/
│   │   └── fyers_broker.py          # Fyers API v3
│   └── upstox/                      # ── NEW ──
│       └── upstox_broker.py         # Upstox API v2 (OAuth2, WS, option chain)
│
├── indicators/
│   └── technical.py                 # EMA, SMA, VWAP, RSI, MACD, ATR, BB, Supertrend
│
├── strategies/
│   ├── base_strategy.py             # Abstract BaseStrategy
│   ├── breakout_strategy.py         # Opening Range Breakout
│   └── additional_strategies.py    # MA Crossover, VWAP, Momentum
│
├── risk_management/
│   └── risk_manager.py              # SL/Target/TSL, sizing, daily loss gate
│
├── execution/
│   └── execution_engine.py          # Orders, retry, strike selection, paper trading
│
├── backtesting/
│   └── backtest_engine.py           # Event-driven backtester + full metrics
│
├── live_trading/
│   └── live_trader.py               # Production live trading loop
│
├── data/
│   ├── data_feed.py                 # Generic historical + live data coordinator
│   └── providers/
│       └── upstox_data.py           # Upstox: option chain, PCR, max pain, IV rank
│
├── database/
│   └── models.py                    # SQLAlchemy ORM + session factory
│
├── api/
│   └── routes.py                    # FastAPI REST (10 endpoints + Swagger)
│
├── logging_module/
│   └── logger.py                    # Colour console + JSON file + trade logger
│
├── notifications/
│   └── notifier.py                  # Telegram + Email real-time alerts
│
├── utils/
│   └── helpers.py                   # IST timezone, market hours, strike rounding
│
├── scripts/
│   ├── upstox_login.py              # Interactive Upstox OAuth2 login
│   ├── generate_token.py            # Universal token generator (all brokers)
│   └── run_backtest.py              # CLI backtest runner
│
└── tests/
    ├── unit/
    │   ├── test_core.py             # Indicators, strategies, risk, backtest
    │   └── test_upstox.py           # 30+ Upstox-specific unit tests
    └── integration/
        └── test_upstox_integration.py  # Live API integration tests
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/your-org/options-trader.git
cd options-trader
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Upstox Login (once per trading day)

```bash
python scripts/upstox_login.py
# OR for any broker:
python scripts/generate_token.py --broker upstox
```

### 4. Run Demo (no broker needed)

```bash
python main.py demo
```

### 5. Run Backtest

```bash
python scripts/run_backtest.py --strategy all --days 90 --capital 500000
# or
python main.py backtest
```

### 6. Live / Paper Trading

```bash
# Ensure PAPER_TRADING=true in .env first!
BROKER=upstox python main.py live
```

### 7. REST API + Dashboard

```bash
python main.py api
# Swagger UI: http://localhost:8000/docs
```

---

## 🔌 Upstox Integration (New)

### What's included

| Feature | Implementation |
|---|---|
| OAuth2 auth flow | `connect()` + `exchange_code_for_token()` |
| Token refresh | Auto-refresh via `UPSTOX_RTOKEN` |
| Live quotes | `get_quote()`, `get_ltp()` |
| Historical OHLCV | `get_historical_data()` — intraday + multi-day |
| Option chain | `get_option_chain()` with full Greeks |
| WebSocket streaming | SDK-based + raw WS fallback |
| Place/modify/cancel orders | Full order lifecycle |
| Position management | `get_positions()`, `get_portfolio()` |
| Funds & margin | `get_funds()`, `get_required_margin()` |
| Brokerage calculation | `get_brokerage()` |
| Market status | `get_market_status()` |
| PCR calculation | `UpstoxDataProvider.get_pcr()` |
| Max Pain | `UpstoxDataProvider.get_max_pain()` |
| IV Rank | `UpstoxDataProvider.get_iv_rank()` |
| ATM strike | `UpstoxDataProvider.get_atm_strike()` |
| Expiry calendar | `UpstoxDataProvider.get_nifty_expiries()` |

### Upstox Setup

```bash
# 1. Register at https://developer.upstox.com/
# 2. Create an app, get API key + secret
# 3. Add to .env:
UPSTOX_API_KEY=your_api_key
UPSTOX_API_SECRET=your_api_secret
UPSTOX_REDIRECT_URI=https://127.0.0.1/

# 4. Run login script once per trading day:
python scripts/upstox_login.py
# Paste the token into .env as UPSTOX_ACCESS_TOKEN

# 5. Set Upstox as active broker:
BROKER=upstox
```

### Using Upstox in Code

```python
from broker.upstox.upstox_broker import UpstoxBroker
from data.providers.upstox_data import UpstoxDataProvider
from datetime import datetime, timedelta

# Connect
broker = UpstoxBroker()
broker.connect()

# Get Nifty quote
tick = broker.get_quote("NIFTY", "NSE")
print(f"NIFTY LTP: {tick.ltp}")

# Option chain
expiry = datetime.now() + timedelta(days=7)
chain = broker.get_option_chain("NIFTY", expiry)
atm_ce = next(c for c in chain if c["option_type"] == "CE"
              and abs(c["strike"] - tick.ltp) < 100)
print(f"ATM CE: {atm_ce['tradingsymbol']} | LTP: {atm_ce['ltp']}")

# Advanced data utilities
dp = UpstoxDataProvider(broker)
pcr = dp.get_pcr("NIFTY", expiry)
max_pain = dp.get_max_pain("NIFTY", expiry)
print(f"PCR: {pcr} | Max Pain: {max_pain}")

# Place an order (paper trading — no real order)
from core.models import Order, OrderSide, OrderType
order = Order(
    symbol=atm_ce["tradingsymbol"],
    exchange="NFO",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=50,
    product="MIS",
)
result = broker.place_order(order)
print(f"Order: {result.status} | ID: {result.broker_order_id}")
```

---

## 🏗 Architecture

```
┌────────────────────────────────────────────────────────┐
│                   LIVE TRADING LOOP                     │
│                                                         │
│  ┌──────────┐   ┌──────────────────┐   ┌────────────┐  │
│  │DataFeed  │──▶│ Strategy Engine  │──▶│ Execution  │  │
│  │          │   │ BreakoutStrategy │   │  Engine    │  │
│  │ Broker   │   │ MACrossover      │   │ Strike sel │  │
│  │ (any of  │   │ VWAPStrategy     │   │ Order retry│  │
│  │ 4 below) │   │ MomentumStrategy │   │ Slippage   │  │
│  └────┬─────┘   └────────┬─────────┘   └─────┬──────┘  │
│       │                  │ Signal             │ Order   │
│  ┌────▼──────────────────▼──────────────────▼───────┐  │
│  │                  RiskManager                      │  │
│  │   Position sizing · SL/Target · Trailing SL       │  │
│  │   Daily loss gate · Max positions                 │  │
│  └─────────────────────────────┬─────────────────────┘  │
│                                │                         │
│  ┌─────────────────────────────▼─────────────────────┐  │
│  │  BaseBroker (abstract)                             │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────┐  │  │
│  │  │ Zerodha  │ │AngelOne  │ │ Fyers  │ │Upstox  │  │  │
│  │  │KiteConnect│ │SmartAPI  │ │ API v3 │ │API v2  │  │  │
│  │  └──────────┘ └──────────┘ └────────┘ └────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────┐    │
│  │  Database  │  │  FastAPI     │  │ Notifications │    │
│  │SQLite/PG   │  │  REST + WS   │  │Telegram/Email │    │
│  └────────────┘  └──────────────┘  └───────────────┘    │
└────────────────────────────────────────────────────────┘
```

---

## 📊 Strategies

| Strategy | Entry Logic | Confirmation |
|---|---|---|
| **ORB Breakout** | Break above/below 15-min opening range | RSI < 75 / > 25, ATR-based SL |
| **MA Crossover** | EMA(9) crosses EMA(21) | RSI > 55 bullish / < 45 bearish |
| **VWAP** | Price crosses above/below VWAP | RSI + deviation threshold |
| **Momentum** | MACD histogram turns positive/negative | EMA trend + RSI filter |

---

## ⚠️ Risk Management

| Control | Default | Config Key |
|---|---|---|
| Max daily loss | 2% of capital | `max_daily_loss_pct` |
| Max per-trade size | 5% of capital | `max_position_size_pct` |
| Max open positions | 5 | `max_open_positions` |
| Default stop loss | 30% of premium | `default_stop_loss_pct` |
| Default target | 50% of premium | `default_target_pct` |
| Trailing SL activation | 20% profit | `trailing_stop_activation_pct` |
| Trailing SL trail | 10% below peak | `trailing_stop_pct` |
| Max slippage | 0.5% | `max_slippage_pct` |

---

## 📈 Backtesting

```bash
# CLI runner (simplest)
python scripts/run_backtest.py --strategy breakout --days 90 --capital 500000

# All strategies
python scripts/run_backtest.py --strategy all

# Custom parameters
python scripts/run_backtest.py \
  --strategy momentum \
  --days 120 \
  --capital 1000000 \
  --sl-pct 25 \
  --target-pct 50
```

**Sample output:**
```
═══════════════════════════════════════════════════════
  BACKTEST REPORT — BreakoutStrategy
═══════════════════════════════════════════════════════
  Total Trades         : 94
  Win Rate             : 54.3%
  Total P&L            : ₹1,38,750.00
  Profit Factor        : 1.87
  Sharpe Ratio         : 1.52
  Sortino Ratio        : 2.14
  Max Drawdown         : -₹31,200.00  (-6.2%)
═══════════════════════════════════════════════════════
```

---

## 🖥️ REST API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System + broker connection status |
| GET | `/positions` | All open positions with live P&L |
| GET | `/daily-stats` | Today's P&L, trades, loss-limit status |
| GET | `/strategies` | Registered strategies + config |
| POST | `/strategies/{name}/toggle` | Enable/disable a strategy |
| POST | `/exit/{position_id}` | Manually close a position |
| POST | `/exit-all` | Emergency square-off |
| GET | `/trades` | Trade history from DB |
| GET | `/strategy-results` | Backtest/live performance summaries |

📖 **Swagger UI:** `http://localhost:8000/docs`

---

## 🔔 Notifications

Set in `.env` and get real-time trade alerts:

```
# Telegram — create bot via @BotFather
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100xxxxxxxxx

# Email (Gmail example — use App Password)
EMAIL_FROM=you@gmail.com
EMAIL_TO=alerts@yourdomain.com
SMTP_PASSWORD=your_gmail_app_password
```

---

## 🧪 Tests

```bash
# All unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing

# Upstox-specific tests only
pytest tests/unit/test_upstox.py -v

# Integration tests (requires real credentials)
SKIP_INTEGRATION=false pytest tests/integration/ -v
```

---

## 🛠️ Adding a New Strategy

```python
# strategies/my_strategy.py
from strategies.base_strategy import BaseStrategy
from core.models import Signal, SignalType, StrategyType, OptionType

class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("MyStrategy", StrategyType.MOMENTUM)

    def pre_process(self, df):
        df = df.copy()
        # Add your indicator columns here
        return df

    def generate_signal(self, df, symbol) -> Signal:
        if not self.validate_data(df):
            return self.no_signal(symbol)
        # Your logic here
        return Signal(
            signal_type=SignalType.BUY_CE,
            strategy_name=self.name,
            symbol=symbol,
            option_type=OptionType.CE,
            strike=None, expiry=None,
            confidence=0.75,
            entry_price=df.iloc[-1]["close"],
        )
```

Register in `main.py`:
```python
from strategies.my_strategy import MyStrategy
strategies = [MyStrategy(), BreakoutStrategy()]
```

---

## ⚙️ Production Checklist

- [ ] Set `PAPER_TRADING=false` only after thorough testing
- [ ] Use PostgreSQL (`DATABASE_URL=postgresql://...`) in production
- [ ] Set a strong `API_SECRET_KEY`
- [ ] Configure Telegram alerts for real-time monitoring
- [ ] Use a process manager (systemd / supervisor / Docker)
- [ ] Set up daily log rotation (`logs/` directory)
- [ ] Test every strategy in paper mode for at least 2 weeks
- [ ] Verify broker credentials before market open each day
- [ ] Re-run `python scripts/upstox_login.py` daily (tokens expire EOD)

---

## ⚠️ Disclaimer

**This software is for educational and research purposes only.**
Never trade with money you cannot afford to lose.
Past performance does not guarantee future results.
The authors accept no liability for financial losses.
