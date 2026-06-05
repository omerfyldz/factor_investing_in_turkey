# Backtrader — Comprehensive Reference Guide

**Algorithmic Trading and Quantitative Strategies — EC581**
**Dr. Ayhan Yuksel, CFA, FDP, FRM, PRM — Bogazici University**

> This document is a consolidated reference for all features, capabilities, and configuration options of the [backtrader](https://www.backtrader.com/) Python framework used throughout the course notebooks (NB_04 through NB_06 and beyond).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Cerebro Engine](#2-cerebro-engine)
3. [Data Feeds](#3-data-feeds)
4. [Strategy Lifecycle](#4-strategy-lifecycle)
5. [Order Types & Order Management](#5-order-types--order-management)
6. [Broker Simulator](#6-broker-simulator)
7. [Commission Schemes, Fees, Margins & Leverage](#7-commission-schemes-fees-margins--leverage)
8. [Slippage Modeling](#8-slippage-modeling)
9. [Notifications & Logging](#9-notifications--logging)
10. [Built-in Indicators (122+)](#10-built-in-indicators-122)
11. [ta-lib Integration](#11-ta-lib-integration)
12. [Sizers — Position Sizing & Money Management](#12-sizers--position-sizing--money-management)
13. [Performance Analyzers](#13-performance-analyzers)
14. [Observers — Plotted Statistics](#14-observers--plotted-statistics)
15. [Plotting](#15-plotting)
16. [Optimization](#16-optimization)
17. [Timers, Calendars & Timezone Support](#17-timers-calendars--timezone-support)
18. [Signal-Based Strategies](#18-signal-based-strategies)
19. [Live Trading Compatibility](#19-live-trading-compatibility)
20. [Miscellaneous Features](#20-miscellaneous-features)
21. [Quick-Start Code Template](#21-quick-start-code-template)

---

## 1. Architecture Overview

Backtrader follows a modular, object-oriented architecture. The main components interact as follows:

```
┌─────────────────────────────────────────────────────┐
│                     Cerebro                         │
│  (central engine — orchestrates everything)         │
│                                                     │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│   │ Data     │  │ Strategy │  │ Broker           │ │
│   │ Feed(s)  │──│ (user    │──│ (order execution,│ │
│   │          │  │  logic)  │  │  cash, positions)│ │
│   └──────────┘  └────┬─────┘  └──────────────────┘ │
│                      │                              │
│         ┌────────────┼────────────┐                 │
│         │            │            │                 │
│   ┌─────┴────┐ ┌─────┴────┐ ┌────┴─────┐          │
│   │Indicators│ │ Sizers   │ │Analyzers │          │
│   │          │ │          │ │& Observers│          │
│   └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────┘
```

**Key design principles:**
- **Event-driven + vectorized hybrid**: trading logic and broker always run event-by-event; indicator calculations are vectorized when data is preloaded.
- **0-based indexing**: `[0]` = current bar, `[-1]` = previous bar, positive indices = future (will raise errors in event-only mode to prevent look-ahead bias).
- **Pure Python**: no external C libraries required (optional: matplotlib, pandas, ta-lib, pyfolio).
- **Operator overloading**: natural mathematical expressions for indicators, e.g. `bt.ind.SMA(period=30) - bt.ind.SMA(period=15)`.

---

## 2. Cerebro Engine

`Cerebro` is the central controller that wires together data, strategies, broker, analyzers, observers, and sizers.

### Core Methods

| Method | Purpose |
|---|---|
| `adddata(data)` | Add a data feed |
| `resampledata(data, timeframe, compression)` | Resample data to a higher timeframe |
| `replaydata(data, timeframe, compression)` | Replay data bar-by-bar |
| `addstrategy(cls, *args, **kwargs)` | Add a strategy class |
| `optstrategy(cls, **kwargs)` | Add a strategy for parameter optimization |
| `addanalyzer(cls, *args, **kwargs)` | Add a performance analyzer |
| `addobserver(cls, *args, **kwargs)` | Add an observer |
| `addsizer(cls, *args, **kwargs)` | Add a default sizer for all strategies |
| `addsizer_byidx(idx, cls, *args, **kwargs)` | Add a sizer for a specific strategy |
| `broker` | Property to access/configure the broker |
| `run(**kwargs)` | Execute the backtest |
| `plot(**kwargs)` | Plot the results |

### Common `run()` Parameters

| Parameter | Default | Description |
|---|---|---|
| `preload` | `True` | Preload all data feeds before running |
| `runonce` | `True` | Use vectorized indicator calculation |
| `optreturn` | `True` | Return lightweight optimization results |
| `exactbars` | `False` | Memory savings mode (integer controls level) |
| `stdstats` | `True` | Add standard observers (Broker, BuySell, Trades) |

### Example

```python
cerebro = bt.Cerebro()
cerebro.adddata(data)
cerebro.addstrategy(MyStrategy, param1=10)
cerebro.broker.setcash(100000)
cerebro.broker.setcommission(commission=0.001)
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addsizer(bt.sizers.PercentSizer, percents=95)
results = cerebro.run()
cerebro.plot()
```

---

## 3. Data Feeds

### Built-in Data Sources

| Class | Source |
|---|---|
| `bt.feeds.GenericCSVData` | Any CSV with configurable columns |
| `bt.feeds.BacktraderCSVData` | Backtrader's own CSV format |
| `bt.feeds.YahooFinanceCSVData` | Yahoo Finance CSV files |
| `bt.feeds.YahooFinanceData` | Yahoo Finance direct download |
| `bt.feeds.PandasData` | Pandas DataFrame |
| `bt.feeds.PandasDirectData` | Pandas DataFrame (direct access, no copy) |
| `bt.feeds.VChartCSVData` | VisualChart CSV |
| `bt.feeds.SierraChartCSVData` | SierraChart CSV |
| `bt.feeds.IBData` | Interactive Brokers (live) |
| `bt.feeds.OandaData` | Oanda v1 (live) |

### Data Lines

Every data feed exposes these standard lines (accessible via `self.data.xxx` or `self.data.lines.xxx`):

| Line | Index | Description |
|---|---|---|
| `close` | 0 | Closing price |
| `low` | 1 | Low price |
| `high` | 2 | High price |
| `open` | 3 | Opening price |
| `volume` | 4 | Volume |
| `openinterest` | 5 | Open interest |
| `datetime` | 6 | Date/time |

### Key Capabilities

- **Multiple simultaneous data feeds** — any number of instruments
- **Multiple timeframes** — mix intraday with daily, weekly, monthly
- **Resampling** — aggregate lower timeframes to higher ones (e.g., 1-min → 1-hour)
- **Replaying** — rebuild bars tick-by-tick for realistic simulation
- **Data filters** — session filters, Renko bricks, etc.
- **Rollover** — automatic futures contract rollover
- **Custom data feeds** — subclass `bt.feeds.DataBase` to create your own

### PandasData Example

```python
data = bt.feeds.PandasData(
    dataname=df,
    datetime=None,   # use the DataFrame index
    open='Open',
    high='High',
    low='Low',
    close='Close',
    volume='Volume',
    openinterest=-1, # not available
    fromdate=datetime(2020, 1, 1),
    todate=datetime(2023, 12, 31)
)
```

### Resampling Example

```python
data0 = bt.feeds.YahooFinanceData(dataname='AAPL', timeframe=bt.TimeFrame.Days)
cerebro.adddata(data0)
cerebro.resampledata(data0, timeframe=bt.TimeFrame.Weeks)
```

---

## 4. Strategy Lifecycle

### Lifecycle Methods (in execution order)

| Phase | Method | Description |
|---|---|---|
| **Conception** | `__init__()` | Declare indicators, set up variables. No trading allowed. |
| **Birth** | `start()` | Called just before backtesting begins. Optional setup. |
| **Childhood** | `prenext()` | Called while indicators are warming up (minimum period not yet met). |
| **Transition** | `nextstart()` | Called exactly once when the minimum period is first met. Default: calls `next()`. |
| **Adulthood** | `next()` | Called for every bar once all indicators are ready. **Main trading logic goes here.** |
| **Death** | `stop()` | Called when backtesting ends. Final calculations, reporting. |

### Trading Methods

| Method | Description |
|---|---|
| `self.buy(...)` | Create a buy (long) order |
| `self.sell(...)` | Create a sell (short) order |
| `self.close(...)` | Close an existing position |
| `self.cancel(order)` | Cancel a pending order |
| `self.buy_bracket(...)` | Create a bracket order group (entry + stop-loss + take-profit) |
| `self.sell_bracket(...)` | Create a bracket order group for short positions |

### Target-Based Order Methods (Portfolio Rebalancing)

| Method | Description |
|---|---|
| `self.order_target_size(data, target)` | Rebalance to a target number of shares |
| `self.order_target_value(data, target)` | Rebalance to a target dollar value |
| `self.order_target_percent(data, target)` | Rebalance to a target percentage of portfolio |

### Key Attributes Available in a Strategy

| Attribute | Description |
|---|---|
| `self.data` / `self.data0` | First data feed |
| `self.dataX` | Xth data feed |
| `self.datas` | List of all data feeds |
| `self.dnames` | Access data feeds by name |
| `self.broker` | Reference to the broker |
| `self.position` | Current position for `data0` |
| `self.getposition(data)` | Current position for a specific data |
| `self.order` | (user-managed) reference to a pending order |
| `self.stats` | Observers |
| `self.analyzers` | Analyzers |
| `self.sizer` | Current sizer |
| `self.p` / `self.params` | Strategy parameters |

### Strategy Parameters

```python
class MyStrategy(bt.Strategy):
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
        ('risk_pct', 0.02),
    )

    def __init__(self):
        self.fast_sma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_sma = bt.ind.SMA(period=self.p.slow_period)
```

---

## 5. Order Types & Order Management

### Supported Order Types

| Type | Constant | Execution Logic |
|---|---|---|
| **Market** | `bt.Order.Market` | Executes at the **opening price** of the next bar |
| **Close** | `bt.Order.Close` | Executes at the **closing price** of the next bar when it actually closes |
| **Limit** | `bt.Order.Limit` | Executes if the limit `price` is seen during the session |
| **Stop** | `bt.Order.Stop` | Triggers a Market order when the `price` (stop) is reached |
| **StopLimit** | `bt.Order.StopLimit` | Triggers a Limit order (at `plimit`) when the `price` (stop) is reached |
| **StopTrail** | `bt.Order.StopTrail` | Trailing stop — updates as price moves favorably |
| **StopTrailLimit** | `bt.Order.StopTrailLimit` | Trailing stop that triggers a Limit order |
| **MarketOnClose** | — | Execute at the session closing price |

### Order Validity

| Value | Meaning |
|---|---|
| `None` | Good Til Cancel (GTC) — order stays until filled or canceled |
| `datetime.date` or `datetime.datetime` | Good Til Date — expires at the given date |
| `bt.Order.DAY` or `0` or `timedelta()` | Day order — expires at end of session |
| Numeric (matplotlib date) | Good Til Date using matplotlib date encoding |

### Order Parameters (buy/sell)

```python
self.buy(
    data=None,          # which data feed (default: self.data0)
    size=None,          # number of units (default: ask the Sizer)
    price=None,         # price for Limit/Stop orders
    plimit=None,        # limit price for StopLimit orders
    exectype=None,      # Order.Market, Order.Limit, etc.
    valid=None,         # validity (GTC, date, DAY)
    tradeid=0,          # trade grouping id
    oco=None,           # another order for OCO group
    trailamount=None,   # absolute trail distance for StopTrail
    trailpercent=None,  # percentage trail distance for StopTrail
    parent=None,        # parent order for bracket groups
    transmit=True,      # transmit immediately or wait for bracket
    **kwargs            # extra broker-specific parameters
)
```

### Advanced Order Groups

#### OCO (One Cancels Others)

When one order in the OCO group executes, all others are automatically canceled.

```python
o1 = self.buy(exectype=bt.Order.Limit, price=50.0)
o2 = self.buy(exectype=bt.Order.Limit, price=48.0, oco=o1)
o3 = self.buy(exectype=bt.Order.Limit, price=46.0, oco=o1)
# If o1 fills, o2 and o3 are canceled automatically
```

#### Bracket Orders

A main entry order with automatic stop-loss and take-profit:

```python
orders = self.buy_bracket(
    price=100.0,         # entry limit price
    stopprice=95.0,      # stop-loss price
    limitprice=110.0,    # take-profit price
    size=100
)
# Returns [main_order, stop_order, limit_order]
```

```python
orders = self.sell_bracket(
    price=100.0,         # entry limit price (short)
    stopprice=105.0,     # stop-loss price (buy to cover)
    limitprice=90.0,     # take-profit price (buy to cover)
)
```

### Order Status Values

| Status | Meaning |
|---|---|
| `order.Submitted` | Order sent to broker |
| `order.Accepted` | Order accepted by broker |
| `order.Completed` | Order fully executed |
| `order.Canceled` | Order canceled (by user or system) |
| `order.Margin` | Order rejected due to insufficient margin/cash |
| `order.Expired` | Order validity expired |
| `order.Partial` | Order partially filled |
| `order.Rejected` | Order rejected by broker |

### Order Execution Price Logic

For **Market** orders:
- Executed at the **open** of the next bar

For **Limit Buy** orders:
- If `open < limit_price` → filled at `open` (gap down, price improved)
- If `low <= limit_price` → filled at `limit_price`

For **Stop Buy** orders:
- If `open > stop_price` → triggered at `open` (gap up)
- If `high >= stop_price` → triggered at `stop_price`

(Logic is inverted for sell orders.)

---

## 6. Broker Simulator

The built-in `BackBroker` simulates realistic trading conditions.

### Broker Configuration

| Parameter | Default | Description |
|---|---|---|
| `cash` | `10000` | Starting cash |
| `checksubmit` | `True` | Validate margin/cash before accepting orders |
| `eosbar` | `False` | Treat bar at session-end time as end-of-session |
| `coc` | `False` | **Cheat-On-Close** — match orders to current bar's close |
| `coo` | `False` | **Cheat-On-Open** — match orders to current bar's open (via timer) |
| `int2pnl` | `True` | Assign credit interest to trade P&L |
| `shortcash` | `True` | Increase cash when shorting stock-like assets |
| `fundstartval` | `100.0` | Starting value for fund-like performance tracking |
| `fundmode` | `False` | Track performance as a fund (NAV-independent) |
| `filler` | `None` | Custom volume-filling callable for partial fills |

### Broker Methods

```python
cerebro.broker.setcash(100000)                    # Set starting cash
cerebro.broker.getcash()                          # Get current cash
cerebro.broker.getvalue()                         # Get portfolio value
cerebro.broker.get_value(datas=None, mkt=False)   # Get value for specific data(s)
cerebro.broker.getposition(data)                  # Get position for a data
cerebro.broker.get_orders_open()                  # Get list of open orders
cerebro.broker.add_cash(5000)                     # Add cash during run
cerebro.broker.add_cash(-2000)                    # Withdraw cash during run
```

### Cheat-On-Close (COC)

Allows matching a Market order to the **closing price of the same bar** in which it was issued. Useful for strategies that need same-bar execution.

```python
cerebro.broker.set_coc(True)
```

### Cheat-On-Open (COO)

Allows issuing orders before the broker evaluates, enabling execution at the **opening price of the current bar**. Used with timers where `cheat=True`.

```python
cerebro.broker.set_coo(True)
```

---

## 7. Commission Schemes, Fees, Margins & Leverage

### Quick Setup via Broker Shortcut

```python
# Stocks: percentage-based commission
cerebro.broker.setcommission(commission=0.001)  # 0.1% per trade

# Futures: fixed commission + margin + multiplier
cerebro.broker.setcommission(
    commission=2.0,     # $2 per contract
    margin=2000.0,      # $2000 margin per contract
    mult=10.0           # contract multiplier
)

# Per-instrument (by name)
cerebro.broker.setcommission(
    commission=2.0, margin=2000.0, mult=10.0,
    name='ES'           # only applies to data named 'ES'
)
```

### Full `setcommission()` Parameters

| Parameter | Default | Description |
|---|---|---|
| `commission` | `0.0` | Commission amount (fixed or percentage) |
| `margin` | `None` | Margin per contract. If `None` → stock-like (% commission). If set → futures-like (fixed commission). |
| `mult` | `1.0` | Contract multiplier for P&L (futures) |
| `commtype` | `None` | `CommInfoBase.COMM_PERC` or `CommInfoBase.COMM_FIXED` |
| `percabs` | `True` | If `True`: commission 0.001 = 0.1%. If `False`: commission 0.1 = 0.1%. |
| `stocklike` | `False` | `True` for stocks, `False` for futures |
| `interest` | `0.0` | Yearly interest rate for short positions (e.g., 0.05 = 5%) |
| `interest_long` | `False` | Charge interest on long positions too (e.g., ETFs) |
| `leverage` | `1.0` | Leverage ratio for the asset |
| `automargin` | `False` | Auto-calculate margin from price × multiplier |
| `name` | `None` | Apply only to instruments with this name |

### Custom CommissionInfo Class

For full control, subclass `bt.CommissionInfo`:

```python
class MyCommission(bt.CommissionInfo):
    params = (
        ('commission', 0.001),    # 0.1%
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexec):
        # Custom logic: e.g., tiered pricing
        value = abs(size) * price
        if value > 100000:
            return value * 0.0005  # 0.05% for large orders
        return value * self.p.commission

cerebro.broker.addcommissioninfo(MyCommission())
```

### Interest on Short Positions

```python
cerebro.broker.setcommission(
    commission=0.001,
    interest=0.05,          # 5% annual interest on short positions
    interest_long=False     # don't charge on longs
)
```

Formula: `days × price × abs(size) × (interest / 365)`

### Leverage

```python
cerebro.broker.setcommission(
    commission=0.001,
    leverage=2.0            # 2x leverage
)
```

---

## 8. Slippage Modeling

Slippage simulates the difference between expected and actual execution prices.

### Configuration

```python
# Percentage-based slippage
cerebro.broker.set_slippage_perc(
    perc=0.001,           # 0.1% slippage
    slip_open=True,       # apply to orders executed at open
    slip_limit=True,      # apply to limit orders
    slip_match=True,      # cap slippage at high/low
    slip_out=False         # don't allow slippage outside high/low range
)

# Fixed-point slippage
cerebro.broker.set_slippage_fixed(
    fixed=0.05,           # $0.05 slippage per unit
    slip_open=True,
    slip_limit=True,
    slip_match=True,
    slip_out=False
)
```

### Slippage Parameters

| Parameter | Default | Description |
|---|---|---|
| `slip_perc` | `0.0` | Slippage as a percentage (0.01 = 1%) |
| `slip_fixed` | `0.0` | Slippage as fixed points |
| `slip_open` | `False` | Apply slippage to open-price executions (e.g., Market orders) |
| `slip_match` | `True` | Cap slippage at bar's high/low prices |
| `slip_limit` | `True` | Match Limit orders even when `slip_match=False` |
| `slip_out` | `False` | Allow slippage to push execution price outside high/low range |

**Note:** If `slip_perc` is non-zero, it takes precedence over `slip_fixed`.

---

## 9. Notifications & Logging

### Strategy Notification Callbacks

| Callback | When Called | Typical Use |
|---|---|---|
| `notify_order(order)` | On any order status change | Track order execution, log fills, handle rejections |
| `notify_trade(trade)` | On trade open/update/close | Track trade P&L, log completed trades |
| `notify_cashvalue(cash, value)` | Before each `next()` cycle | Monitor account equity |
| `notify_fund(cash, value, fundvalue, shares)` | Before each `next()` cycle | Fund-mode monitoring |
| `notify_store(msg, *args, **kwargs)` | On store-provider events | Live trading notifications |
| `notify_timer(timer, when, *args, **kwargs)` | When a timer fires | Scheduled actions |

### `notify_order` — Comprehensive Example

```python
def notify_order(self, order):
    if order.status in [order.Submitted, order.Accepted]:
        return  # order pending, nothing to do

    if order.status in [order.Completed]:
        if order.isbuy():
            self.log(
                f'BUY EXECUTED | '
                f'Price: {order.executed.price:.2f} | '
                f'Cost: {order.executed.value:.2f} | '
                f'Comm: {order.executed.comm:.2f} | '
                f'Size: {order.executed.size}'
            )
        elif order.issell():
            self.log(
                f'SELL EXECUTED | '
                f'Price: {order.executed.price:.2f} | '
                f'Cost: {order.executed.value:.2f} | '
                f'Comm: {order.executed.comm:.2f} | '
                f'Size: {order.executed.size}'
            )

    elif order.status in [order.Canceled]:
        self.log('ORDER CANCELED')
    elif order.status in [order.Margin]:
        self.log('ORDER MARGIN — INSUFFICIENT FUNDS')
    elif order.status in [order.Rejected]:
        self.log('ORDER REJECTED')
    elif order.status in [order.Expired]:
        self.log('ORDER EXPIRED')

    self.order = None  # reset order sentinel
```

### `notify_trade` — Example

```python
def notify_trade(self, trade):
    if not trade.isclosed:
        return
    self.log(f'TRADE CLOSED | '
             f'Gross P&L: {trade.pnl:.2f} | '
             f'Net P&L: {trade.pnlcomm:.2f}')
```

### Order Object — Useful Attributes

| Attribute | Description |
|---|---|
| `order.status` | Current status (see status table above) |
| `order.isbuy()` | `True` if buy order |
| `order.issell()` | `True` if sell order |
| `order.executed.price` | Fill price |
| `order.executed.value` | Monetary value of the fill |
| `order.executed.comm` | Commission paid |
| `order.executed.size` | Number of units filled |
| `order.executed.pnl` | Profit/loss (for closing orders) |
| `order.created.price` | Price when order was created |
| `order.created.size` | Size when order was created |
| `order.created.dt` | Datetime when order was created |
| `order.ref` | Unique order reference number |

### Custom Logging Method

```python
def log(self, txt, dt=None):
    dt = dt or self.datas[0].datetime.date(0)
    print(f'{dt.isoformat()}, {txt}')
```

---

## 10. Built-in Indicators (122+)

### Moving Averages

| Indicator | Aliases | Key Parameters |
|---|---|---|
| Simple Moving Average | `SMA`, `MovingAverageSimple` | `period` |
| Exponential Moving Average | `EMA`, `MovingAverageExponential` | `period` |
| Weighted Moving Average | `WMA`, `MovingAverageWeighted` | `period` |
| Smoothed Moving Average | `SMMA`, `WilderMA` | `period` |
| Double Exponential MA | `DEMA` | `period` |
| Triple Exponential MA | `TEMA` | `period` |
| Hull Moving Average | `HMA`, `HullMA` | `period` |
| Kaufman Adaptive MA | `KAMA` | `period`, `fast`, `slow` |
| Zero-Lag Indicator | `ZeroLagIndicator` | `period`, `gainlimit` |
| Dickson Moving Average | `DMA` | `period`, `gainlimit`, `hperiod` |
| Laguerre Filter | `LAGF` | `gamma` |

**All moving averages also have Envelope and Oscillator variants** (e.g., `SMAEnvelope`, `SMAOscillator`).

### Trend Indicators

| Indicator | Aliases | Key Parameters |
|---|---|---|
| MACD | `MACD` | `period_me1=12`, `period_me2=26`, `period_signal=9` |
| MACD Histogram | `MACDHisto`, `MACDHistogram` | same as MACD |
| Average Directional Index | `ADX` | `period=14` |
| ADX Rating | `ADXR` | `period=14` |
| Directional Movement Index | `DMI` | `period=14` |
| Directional Indicator | `DI` (shows +DI, -DI) | `period=14` |
| Plus Directional Indicator | `PlusDI` | `period=14` |
| Minus Directional Indicator | `MinusDI` | `period=14` |
| Directional Movement | `DM` (full: ADX, ADXR, +DI, -DI) | `period=14` |
| Parabolic SAR | `PSAR` | `af=0.02`, `afmax=0.2` |
| Ichimoku Cloud | `Ichimoku` | `tenkan=9`, `kijun=26`, `senkou=52` |
| Trix | `TRIX` | `period=15` |
| Know Sure Thing | `KST` | `rp1..rp4`, `rma1..rma4`, `rsignal` |
| Detrended Price Oscillator | `DPO` | `period=20` |
| Aroon Up/Down | `AroonUpDown` | `period=14` |
| Aroon Oscillator | `AroonOsc` | `period=14` |
| Hurst Exponent | `Hurst` | `period=40` |

### Momentum & Oscillators

| Indicator | Aliases | Key Parameters |
|---|---|---|
| Relative Strength Index | `RSI`, `RSI_SMMA`, `RSI_Wilder` | `period=14`, `upperband=70`, `lowerband=30` |
| RSI (EMA variant) | `RSI_EMA` | `period=14` |
| RSI (SMA/Cutler) | `RSI_SMA`, `RSI_Cutler` | `period=14` |
| Relative Momentum Index | `RMI` | `period=20`, `lookback=5` |
| Stochastic (Slow) | `Stochastic`, `StochasticSlow` | `period=14`, `period_dfast=3`, `period_dslow=3` |
| Stochastic (Fast) | `StochasticFast` | `period=14`, `period_dfast=3` |
| Stochastic (Full) | `StochasticFull` | all three lines |
| Commodity Channel Index | `CCI` | `period=20`, `factor=0.015` |
| Momentum | `Momentum` | `period=12` |
| Momentum Oscillator | `MomentumOsc` | `period=12` |
| Rate of Change | `ROC` | `period=12` |
| Rate of Change (×100) | `ROC100` | `period=12` |
| Percentage Price Osc. | `PPO` | `period1=12`, `period2=26`, `period_signal=9` |
| Price Oscillator | `PriceOsc`, `APO` | `period1=12`, `period2=26` |
| Pretty Good Oscillator | `PGO` | `period=14` |
| Williams %R | `WilliamsR` | `period=14` |
| Ultimate Oscillator | `UltimateOscillator` | `p1=7`, `p2=14`, `p3=28` |
| Awesome Oscillator | `AO` | `fast=5`, `slow=34` |
| Accel/Decel Oscillator | `AccDeOsc` | `period=5` |
| Laguerre RSI | `LRSI` | `period=6`, `gamma=0.5` |
| DV2 | `DV2` | `period=252` |

### Volatility Indicators

| Indicator | Aliases | Key Parameters |
|---|---|---|
| Average True Range | `ATR` | `period=14` |
| True Range | `TrueRange`, `TR` | — |
| True High | `TrueHigh` | — |
| True Low | `TrueLow` | — |
| Bollinger Bands | `BBands` | `period=20`, `devfactor=2.0` |
| Bollinger Bands %B | `BollingerBandsPct` | `period=20`, `devfactor=2.0` |
| Standard Deviation | `StdDev` | `period=20` |
| Mean Deviation | `MeanDev` | `period=20` |

### Support / Resistance

| Indicator | Description |
|---|---|
| `PivotPoint` | Classic pivot points (P, S1, S2, R1, R2) |
| `FibonacciPivotPoint` | Fibonacci-based pivot levels |
| `DemarkPivotPoint` | Demark-style pivot levels |

### Signal / Crossover Indicators

| Indicator | Description |
|---|---|
| `CrossOver` | Returns +1 (cross up) or -1 (cross down) |
| `CrossUp` | Returns 1 when first data crosses above second |
| `CrossDown` | Returns 1 when first data crosses below second |

### Chart Pattern Indicators

| Indicator | Description |
|---|---|
| `HeikinAshi` | Heikin-Ashi candlestick values as lines |
| `Fractal` | Bill Williams fractal pattern detection |

### Statistical Indicators

| Indicator | Description |
|---|---|
| `OLS_BetaN` | OLS regression beta |
| `OLS_Slope_InterceptN` | OLS slope and intercept |
| `OLS_TransformationN` | Spread, z-score (for pairs trading) |
| `CointN` | Cointegration test (score and p-value) |
| `PercentRank` | Percent rank of current value |
| `PercentChange` | Percent change over period |

### Utility Indicators

| Indicator | Aliases | Description |
|---|---|---|
| `Highest` | `MaxN` | Highest value over N periods |
| `Lowest` | `MinN` | Lowest value over N periods |
| `SumN` | — | Sum over N periods |
| `Average` | `ArithmeticMean`, `Mean` | Arithmetic mean over N periods |
| `Accum` | `CumSum` | Cumulative sum |
| `NonZeroDifference` | `NZD` | Last non-zero difference |
| `Envelope` | — | Creates upper/lower bands around any data |
| `ApplyN` | — | Apply custom function over N periods |
| `FindFirstIndexHighest` | — | Index of highest in period |
| `FindLastIndexLowest` | — | Index of lowest in period |

### Using Indicators

```python
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.sma_fast = bt.ind.SMA(self.data.close, period=10)
        self.sma_slow = bt.ind.SMA(self.data.close, period=30)
        self.rsi = bt.ind.RSI(self.data.close, period=14)
        self.bbands = bt.ind.BollingerBands(self.data.close, period=20)
        self.atr = bt.ind.ATR(self.data, period=14)
        self.crossover = bt.ind.CrossOver(self.sma_fast, self.sma_slow)

    def next(self):
        if self.crossover > 0 and self.rsi < 70:
            self.buy()
        elif self.crossover < 0:
            self.close()
```

---

## 11. ta-lib Integration

Backtrader provides seamless integration with the TA-Lib library, giving access to 150+ additional indicators.

```python
import backtrader.talib as btta

class MyStrategy(bt.Strategy):
    def __init__(self):
        self.rsi = btta.RSI(self.data.close, timeperiod=14)
        self.bbands = btta.BBANDS(self.data.close, timeperiod=20)
        self.macd = btta.MACD(self.data.close)
        self.atr = btta.ATR(self.data, timeperiod=14)
```

**Note:** Requires `TA-Lib` C library and `ta-lib` Python wrapper to be installed.

---

## 12. Sizers — Position Sizing & Money Management

Sizers control **how many units** to buy or sell when `size=None` is passed to `buy()`/`sell()`.

### Built-in Sizers

| Sizer | Description |
|---|---|
| `bt.sizers.FixedSize` | Fixed number of units (default: `stake=1`) |
| `bt.sizers.FixedReverser` | Doubles stake when reversing a position |
| `bt.sizers.PercentSizer` | Invest a percentage of portfolio value |
| `bt.sizers.AllInSizer` | Use all available cash |
| `bt.sizers.AllInSizerInt` | Use all available cash (rounded to integer shares) |

### Using Sizers

```python
# Global sizer for all strategies
cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

# Per-strategy sizer
idx = cerebro.addstrategy(MyStrategy)
cerebro.addsizer_byidx(idx, bt.sizers.FixedSize, stake=100)
```

### Custom Sizer Development

Override `_getsizing(comminfo, cash, data, isbuy)`:

```python
class RiskBasedSizer(bt.Sizer):
    params = (
        ('risk_pct', 0.02),   # risk 2% of portfolio per trade
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        # Risk 2% of portfolio, using ATR for stop distance
        portfolio_value = self.broker.getvalue()
        risk_amount = portfolio_value * self.p.risk_pct
        atr = data.atr[0] if hasattr(data, 'atr') else data.close[0] * 0.02
        if atr == 0:
            return 0
        size = int(risk_amount / atr)
        return size
```

### Sizer for Long-Only Strategy

```python
class LongOnly(bt.Sizer):
    params = (('stake', 1),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            return self.p.stake
        position = self.broker.getposition(data)
        if not position.size:
            return 0
        return self.p.stake
```

### Information Available in `_getsizing`

| Parameter | Description |
|---|---|
| `comminfo` | CommissionInfo for the data — can calculate costs, position value |
| `cash` | Current available cash |
| `data` | Target data feed |
| `isbuy` | `True` for buy, `False` for sell |
| `self.strategy` | Full access to the strategy |
| `self.broker` | Full access to the broker |

---

## 13. Performance Analyzers

Analyzers compute statistics about strategy performance. They are added to Cerebro and accessed after the run.

### Built-in Analyzers

| Analyzer | What It Computes |
|---|---|
| `bt.analyzers.SharpeRatio` | Sharpe ratio with configurable risk-free rate and timeframe |
| `bt.analyzers.SharpeRatio_A` | Annualized Sharpe ratio |
| `bt.analyzers.Returns` | Total, average, compound, and annualized returns |
| `bt.analyzers.AnnualReturn` | Year-by-year returns |
| `bt.analyzers.DrawDown` | Drawdown %, drawdown money, drawdown length, and max values |
| `bt.analyzers.TimeDrawDown` | Drawdown per configurable timeframe |
| `bt.analyzers.TradeAnalyzer` | Comprehensive trade statistics (won/lost, streaks, PnL, lengths) |
| `bt.analyzers.SQN` | System Quality Number (Van Tharp) |
| `bt.analyzers.VWR` | Variability-Weighted Return |
| `bt.analyzers.Calmar` | Calmar Ratio (return / max drawdown) |
| `bt.analyzers.TimeReturn` | Returns per configurable time period |
| `bt.analyzers.LogReturnsRolling` | Rolling log returns |
| `bt.analyzers.PeriodStats` | Average, std dev, best, worst per period |
| `bt.analyzers.Transactions` | Per-data transaction log |
| `bt.analyzers.PositionsValue` | Position values per data over time |
| `bt.analyzers.GrossLeverage` | How much the strategy is invested |
| `bt.analyzers.PyFolio` | Export data for pyfolio tear sheets |

### Using Analyzers

```python
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                    timeframe=bt.TimeFrame.Days, riskfreerate=0.02)
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')

results = cerebro.run()
strat = results[0]

print('Sharpe Ratio:', strat.analyzers.sharpe.get_analysis())
print('Max Drawdown:', strat.analyzers.drawdown.get_analysis().max.drawdown)
print('Total Trades:', strat.analyzers.trades.get_analysis().total.total)
print('SQN:', strat.analyzers.sqn.get_analysis().sqn)
```

### SQN Interpretation (Van Tharp)

| SQN Range | Rating |
|---|---|
| 1.6 – 1.9 | Below average |
| 2.0 – 2.4 | Average |
| 2.5 – 2.9 | Good |
| 3.0 – 5.0 | Excellent |
| 5.1 – 6.9 | Superb |
| 7.0+ | Holy Grail |

### TradeAnalyzer Output Structure

```
total.total          # total number of trades
total.open           # currently open trades
total.closed         # closed trades
streak.won.current   # current winning streak
streak.won.longest   # longest winning streak
streak.lost.current  # current losing streak
streak.lost.longest  # longest losing streak
pnl.gross.total      # total gross P&L
pnl.gross.average    # average gross P&L per trade
pnl.net.total        # total net P&L (after commissions)
pnl.net.average      # average net P&L per trade
won.total            # number of winning trades
won.pnl.total        # total P&L of winners
won.pnl.average      # average P&L of winners
won.pnl.max          # largest winner
lost.total           # number of losing trades
lost.pnl.total       # total P&L of losers
lost.pnl.average     # average P&L of losers
lost.pnl.max         # largest loser
long.total           # number of long trades
short.total          # number of short trades
len.total            # total bars in market
len.average          # average bars per trade
len.max              # longest trade (bars)
len.min              # shortest trade (bars)
```

### PyFolio Integration

```python
cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
results = cerebro.run()
strat = results[0]

pyfolio_analyzer = strat.analyzers.pyfolio
returns, positions, transactions, gross_lev = pyfolio_analyzer.get_pf_items()

import pyfolio as pf
pf.create_full_tear_sheet(returns, positions=positions,
                          transactions=transactions,
                          gross_lev=gross_lev)
```

---

## 14. Observers — Plotted Statistics

Observers are like analyzers but produce **line data that is plotted** on the chart.

### Built-in Observers

| Observer | What It Plots |
|---|---|
| `bt.observers.Broker` | Cash and portfolio value (both lines) |
| `bt.observers.Cash` | Cash only |
| `bt.observers.Value` | Portfolio value only |
| `bt.observers.BuySell` | Buy/sell markers on the price chart |
| `bt.observers.Trades` | P&L of closed trades |
| `bt.observers.DrawDown` | Current drawdown level |
| `bt.observers.TimeReturn` | Period returns |
| `bt.observers.LogReturns` | Log returns |
| `bt.observers.LogReturns2` | Log returns for two instruments |
| `bt.observers.Benchmark` | Strategy returns vs. a reference asset |
| `bt.observers.FundValue` | Fund-like value tracking |
| `bt.observers.FundShares` | Fund-like shares tracking |

**Note:** `Broker`, `BuySell`, and `Trades` are added by default when `stdstats=True` (the default).

### Adding/Customizing Observers

```python
cerebro.addobserver(bt.observers.DrawDown)
cerebro.addobserver(bt.observers.Benchmark, data=data_benchmark)
```

---

## 15. Plotting

### Basic Usage

```python
cerebro.plot()
# or with options:
cerebro.plot(
    style='candle',       # 'bar', 'line', 'candle'
    numfigs=1,            # number of figures
    volume=True,          # show volume
    barup='green',        # color for up bars
    bardown='red',        # color for down bars
)
```

### Plotting Features

- Automated subplot layout for indicators, observers, and volume
- Customizable styles: bar, line, candlestick
- Date range filtering
- Same-axis plotting for multiple indicators
- Multiple figures for cleaner layout
- Annotations for buy/sell signals

### Indicator Plot Control

```python
# Don't plot a specific indicator
self.sma = bt.ind.SMA(period=10, plot=False)

# Plot in a subplot
self.rsi = bt.ind.RSI(period=14, subplot=True)

# Plot on the same axis as another indicator
self.sma2 = bt.ind.SMA(period=20, plotmaster=self.data)
```

### Requirements

- `matplotlib` must be installed
- In Jupyter notebooks, use `%matplotlib inline` or `cerebro.plot(iplot=False)`

---

## 16. Optimization

### Basic Optimization

```python
cerebro.optstrategy(
    MyStrategy,
    fast_period=range(5, 30, 5),      # [5, 10, 15, 20, 25]
    slow_period=range(20, 60, 10),     # [20, 30, 40, 50]
)

results = cerebro.run(maxcpus=4)       # use 4 CPU cores

# Analyze results
for run in results:
    for strategy in run:
        sharpe = strategy.analyzers.sharpe.get_analysis()
        params = strategy.params
        print(f'fast={params.fast_period}, slow={params.slow_period}, '
              f'sharpe={sharpe.get("sharperatio", "N/A")}')
```

### Optimization Features

- **Multi-core execution** via `maxcpus` parameter
- **Memory savings** modes for large parameter spaces
- **`optreturn`** parameter to return lightweight results (less memory)
- Returns a list of lists — one sub-list per parameter combination

### Getting Optimization Results

```python
results = cerebro.run()

# Collect results into a list
opt_results = []
for run in results:
    for strat in run:
        analysis = strat.analyzers.returns.get_analysis()
        opt_results.append({
            'fast': strat.params.fast_period,
            'slow': strat.params.slow_period,
            'return': analysis.get('rnorm100', 0),
        })

import pandas as pd
df_results = pd.DataFrame(opt_results)
print(df_results.sort_values('return', ascending=False).head(10))
```

---

## 17. Timers, Calendars & Timezone Support

### Timers

Schedule repeated actions during the trading day:

```python
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.add_timer(
            when=bt.timer.SESSION_START,
            offset=datetime.timedelta(minutes=30),   # 30 min after open
            repeat=datetime.timedelta(minutes=60),    # repeat hourly
            weekdays=[1, 2, 3, 4, 5],                 # Mon-Fri
        )

    def notify_timer(self, timer, when, *args, **kwargs):
        self.log(f'Timer fired at {when}')
        # Perform scheduled action (rebalance, check stops, etc.)
```

### Timer Parameters

| Parameter | Description |
|---|---|
| `when` | `datetime.time`, `bt.timer.SESSION_START`, or `bt.timer.SESSION_END` |
| `offset` | `timedelta` offset from `when` |
| `repeat` | `timedelta` for repeating within session |
| `weekdays` | List of ISO weekdays (1=Mon, 7=Sun) |
| `weekcarry` | If `True`, execute on next available day if skipped |
| `monthdays` | List of days-of-month |
| `monthcarry` | If `True`, execute on next available day if skipped |
| `allow` | Callback returning `True`/`False` for date filtering |
| `tzdata` | Timezone (`pytz` instance, data feed, or `None`) |
| `cheat` | If `True`, timer fires before broker evaluation (cheat-on-open) |

### Trading Calendars

```python
import backtrader as bt

class MyTradingCalendar(bt.TradingCalendar):
    params = dict(
        open=datetime.time(9, 30),
        close=datetime.time(16, 0),
        holidays=[
            datetime.date(2024, 1, 1),   # New Year's Day
            datetime.date(2024, 12, 25),  # Christmas
        ],
        earlydays=[
            (datetime.date(2024, 12, 24), datetime.time(9, 30), datetime.time(13, 0)),
        ],
    )
```

### Timezone Support

```python
import pytz

data = bt.feeds.IBData(
    dataname='AAPL',
    tz=pytz.timezone('US/Eastern')
)
```

---

## 18. Signal-Based Strategies

For simple strategies, backtrader offers a signal-based shortcut that avoids writing a full strategy class:

```python
class MySignal(bt.Indicator):
    lines = ('signal',)
    params = (('period', 30),)

    def __init__(self):
        self.lines.signal = bt.ind.CrossOver(
            bt.ind.SMA(period=10),
            bt.ind.SMA(period=self.p.period)
        )

cerebro.add_signal(bt.SIGNAL_LONG, MySignal, period=20)
cerebro.run()
```

### Signal Types

| Signal | Description |
|---|---|
| `bt.SIGNAL_LONG` | Positive value → buy; negative → close long |
| `bt.SIGNAL_SHORT` | Negative value → sell short; positive → close short |
| `bt.SIGNAL_LONGSHORT` | Positive → buy; negative → sell short |
| `bt.SIGNAL_LONGEXIT` | Exit signal for long positions |
| `bt.SIGNAL_SHORTEXIT` | Exit signal for short positions |

---

## 19. Live Trading Compatibility

Backtrader strategies can transition from backtesting to live trading with minimal code changes.

### Supported Brokers

| Broker | Module | Notes |
|---|---|---|
| Interactive Brokers | `bt.stores.IBStore` | Full support (orders, data, positions) |
| Oanda v1 | `bt.stores.OandaStore` | Forex trading |
| VisualChart | `bt.stores.VCStore` | — |
| Alpaca | `alpaca-backtrader-api` | 3rd party |
| Oanda v20 | `btoandav20` | 3rd party |
| CCXT (crypto) | `bt-ccxt-store` | 3rd party, 100+ crypto exchanges |

### Live Trading Example (IB)

```python
store = bt.stores.IBStore(host='127.0.0.1', port=7497, clientId=1)
cerebro.broker = store.getbroker()
data = store.getdata(dataname='AAPL-STK-SMART-USD')
cerebro.adddata(data)
cerebro.addstrategy(MyStrategy)
cerebro.run()
```

---

## 20. Miscellaneous Features

### Volume Filling (Partial Fills)

Simulate realistic partial order fills based on volume:

```python
cerebro.broker.set_filler(bt.broker.fillers.FixedSize(size=100))
# or
cerebro.broker.set_filler(bt.broker.fillers.FixedBarPerc(perc=50))
# or
cerebro.broker.set_filler(bt.broker.fillers.BarPointPerc(minmov=0.01, perc=50))
```

### Fund Mode

Track performance independently of cash additions/withdrawals:

```python
cerebro.broker.set_fundmode(True, fundstartval=100.0)

# During the run:
cerebro.broker.add_cash(50000)  # NAV won't change, shares adjust
```

### Memory Savings

For large datasets, reduce memory usage:

```python
cerebro.run(exactbars=True)    # minimal memory
cerebro.run(exactbars=1)       # keep minimum bars for indicators
```

### Writer / Logging Output

```python
cerebro.addwriter(bt.WriterFile, csv=True, out='results.csv')
```

### Operator Overloading

Natural mathematical syntax for indicators:

```python
spread = bt.ind.SMA(period=30) - bt.ind.SMA(period=15)
double_sma = bt.ind.SMA(period=20) * 2
above_sma = self.data.close > bt.ind.SMA(period=50)

# Logical operators (can't override 'and', 'or', 'if' in Python)
both_above = bt.And(self.data.close > sma1, self.data.close > sma2)
either_above = bt.Or(self.data.close > sma1, self.data.close > sma2)
conditional = bt.If(condition, value_if_true, value_if_false)
```

### Data Naming & Multi-Data Access

```python
data_aapl = bt.feeds.YahooFinanceData(dataname='AAPL', name='aapl')
data_msft = bt.feeds.YahooFinanceData(dataname='MSFT', name='msft')
cerebro.adddata(data_aapl)
cerebro.adddata(data_msft)

# In strategy:
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.sma_aapl = bt.ind.SMA(self.dnames.aapl, period=20)
        self.sma_msft = bt.ind.SMA(self.dnames['msft'], period=20)
```

---

## 21. Quick-Start Code Template

A complete, minimal template that demonstrates the most commonly used features:

```python
import backtrader as bt
import datetime

class SMACrossStrategy(bt.Strategy):
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.fast_sma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_sma = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_sma, self.slow_sma)
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY @ {order.executed.price:.2f}, '
                         f'Cost: {order.executed.value:.2f}, '
                         f'Comm: {order.executed.comm:.2f}')
            else:
                self.log(f'SELL @ {order.executed.price:.2f}, '
                         f'Comm: {order.executed.comm:.2f}')
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f'TRADE CLOSED — Gross: {trade.pnl:.2f}, '
                     f'Net: {trade.pnlcomm:.2f}')

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.close()

if __name__ == '__main__':
    cerebro = bt.Cerebro()

    # Data
    data = bt.feeds.YahooFinanceData(
        dataname='AAPL',
        fromdate=datetime.datetime(2020, 1, 1),
        todate=datetime.datetime(2023, 12, 31)
    )
    cerebro.adddata(data)

    # Strategy
    cerebro.addstrategy(SMACrossStrategy, fast_period=10, slow_period=30)

    # Broker settings
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.broker.set_slippage_perc(perc=0.001)

    # Sizer
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    # Analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='dd')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

    # Run
    print(f'Starting Portfolio Value: {cerebro.broker.getvalue():.2f}')
    results = cerebro.run()
    strat = results[0]
    print(f'Final Portfolio Value: {cerebro.broker.getvalue():.2f}')

    # Print results
    print(f'Sharpe Ratio: {strat.analyzers.sharpe.get_analysis()}')
    print(f'Max Drawdown: {strat.analyzers.dd.get_analysis().max.drawdown:.2f}%')
    print(f'Total Trades: {strat.analyzers.trades.get_analysis().total.total}')
    returns = strat.analyzers.returns.get_analysis()
    print(f'Total Return: {returns.rtot*100:.2f}%')
    print(f'Annualized Return: {returns.rnorm100:.2f}%')

    # Plot
    cerebro.plot(style='candle')
```

---

## References

- **Official Documentation**: [https://www.backtrader.com/docu/](https://www.backtrader.com/docu/)
- **Features Overview**: [https://www.backtrader.com/home/features/](https://www.backtrader.com/home/features/)
- **Indicator Reference**: [https://www.backtrader.com/docu/indautoref/](https://www.backtrader.com/docu/indautoref/)
- **Analyzer Reference**: [https://www.backtrader.com/docu/analyzers-reference/](https://www.backtrader.com/docu/analyzers-reference/)
- **Broker Reference**: [https://www.backtrader.com/docu/broker/](https://www.backtrader.com/docu/broker/)
- **Strategy Reference**: [https://www.backtrader.com/docu/strategy/](https://www.backtrader.com/docu/strategy/)
- **Sizers Reference**: [https://www.backtrader.com/docu/sizers/sizers/](https://www.backtrader.com/docu/sizers/sizers/)
- **Commission Schemes**: [https://www.backtrader.com/docu/commission-schemes/commission-schemes/](https://www.backtrader.com/docu/commission-schemes/commission-schemes/)
- **Order Execution**: [https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/](https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/)
- **Observers Reference**: [https://www.backtrader.com/docu/observers-reference/](https://www.backtrader.com/docu/observers-reference/)
- **GitHub Repository**: [https://github.com/mementum/backtrader](https://github.com/mementum/backtrader)

---

*Document generated for EC581 — Algorithmic Trading and Quantitative Strategies, Bogazici University.*