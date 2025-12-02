# BİST Trading Bot - Copilot Instructions

## Language / Dil

**Tüm konuşmalar ve açıklamalar Türkçe yapılmalıdır.** Kod içi yorumlar ve değişken isimleri de Türkçe olabilir.

## Project Overview

This is a **BİST (Borsa İstanbul) stock scanner bot** that performs technical and fundamental analysis to generate buy signals and send Telegram notifications. All code and comments are in **Turkish**.

## Architecture & Data Flow

```
main.py (BISTTradingBot) orchestrates the pipeline:
  → data_fetcher.py (yfinance API) → OHLCV, fundamentals, daily stats
  → filters.py (pre-filters) → liquidity, price band, volatility checks
  → indicators.py (TechnicalIndicators) → trend, momentum, volume, price action
  → scoring.py (score_*) → 4-block scoring → signal level (ULTRA_BUY/STRONG_BUY/WATCHLIST)
  → cooldown_manager.py → prevents signal spam
  → telegram_notifier.py → formatted Telegram messages
```

## Key Configuration (`config.py`)

All bot parameters are centralized here. Key settings:
- **Signal thresholds**: `ULTRA_BUY_THRESHOLD=16`, `STRONG_BUY_THRESHOLD=13` (out of 20)
- **Scoring blocks**: Trend (5), Momentum (5), Volume (5), Fundamental/PA (5)
- **Telegram**: Set `DRY_RUN_MODE=True` for testing (logs only, no messages)
- **Symbol list**: `BIST_SYMBOLS` array with ticker codes (yfinance adds `.IS` suffix)

## Module Patterns

### Singleton Pattern
All service classes use factory functions for singleton access:
```python
# Example from data_fetcher.py
_data_fetcher_instance = None
def get_data_fetcher() -> DataFetcher:
    global _data_fetcher_instance
    if _data_fetcher_instance is None:
        _data_fetcher_instance = DataFetcher()
    return _data_fetcher_instance
```
Used in: `data_fetcher.py`, `cooldown_manager.py`, `telegram_notifier.py`

### Scoring Block Pattern
Each scoring function returns `tuple[int, list[str]]` (score, triggered criteria):
```python
def score_trend(indicators: Dict) -> tuple:
    score = 0
    triggered = []
    # ... scoring logic
    return min(score, config.MAX_TREND_SCORE), triggered
```

### Filter Chain Pattern
Filters return `tuple[bool, str]` (passed, reason):
```python
def apply_all_filters(symbol_data: Dict) -> tuple:
    passes, reason = passes_pre_filters(symbol_data)
    if not passes:
        return False, f"Ön filtre: {reason}"
    # ... more filters
    return True, "Tüm filtreleri geçti"
```

## Running the Bot

```bash
cd core-src
pip install pandas numpy yfinance requests python-dateutil
python main.py
```

- Bot runs async with `asyncio.run(main())`
- Scans every `SCAN_INTERVAL_SECONDS` (default: 300s)
- Only runs during market hours (10:00-18:00 Turkey time, weekdays)

## Adding New Indicators

1. Add calculation method to `TechnicalIndicators` class in `indicators.py`
2. Use in appropriate `calculate_*_indicators()` function
3. Add scoring criteria in corresponding `score_*()` function in `scoring.py`
4. If new parameter needed, add to `config.py`

## Adding New Filters

Add filter logic in `filters.py`:
1. Create specific filter function returning `tuple[bool, str]`
2. Call it from `apply_all_filters()`
3. Add threshold constants to `config.py`

## Common Data Structures

**Symbol Data Dict** (passed through pipeline):
```python
{
    'ohlcv': pd.DataFrame,           # OHLCV data from yfinance
    'daily_stats': dict,             # current_price, volume, daily_change_percent
    'fundamentals': dict,            # pe_ratio, pb_ratio, etc.
    'spread': float,                 # bid-ask spread estimate
    'volume_indicators': dict,       # after indicator calculation
    'pa_indicators': dict            # price action features
}
```

**Signal Dict** (from `calculate_total_score`):
```python
{
    'symbol': str,
    'total_score': int,
    'signal_level': str,             # 'ULTRA_BUY', 'STRONG_BUY', 'WATCHLIST', 'NO_SIGNAL'
    'triggered_criteria': list[str], # Human-readable trigger descriptions
    'trend_score': int, 'momentum_score': int, 'volume_score': int, 'fundamental_pa_score': int
}
```

## Logging

Uses Python `logging` module. Set `LOG_LEVEL` in config ('DEBUG', 'INFO', 'WARNING', 'ERROR'). Logs go to both file (`bist_bot.log`) and stdout.

---

## Sprint 1: Provider Katmanı (feature/data-providers-v1)

### Yeni Mimari

```
providers/
├── __init__.py          # Package exports
├── base.py              # BaseDataProvider, Timeframe, ProviderHealthStatus
├── tradingview_ws.py    # TradingView WebSocket (ana realtime kaynak)
├── finnhub.py           # Finnhub REST (intraday/daily fallback)
├── yahoo.py             # yfinance adapter (temel analiz + günlük)
└── manager.py           # ProviderManager (priority + failover)
```

### Provider Öncelik Sıralaması

```python
# config.py
DATA_PRIORITY_INTRADAY = ["tradingview", "finnhub"]  # 1m, 5m, 15m, 1h
DATA_PRIORITY_DAILY = ["finnhub", "yahoo"]            # 1D
```

### Yeni Config Anahtarları

| Anahtar | Varsayılan | Açıklama |
|---------|------------|----------|
| `TRADINGVIEW_ENABLED` | `True` | TradingView WS aktif mi |
| `TRADINGVIEW_WS_URL` | `wss://data.tradingview.com/...` | WebSocket URL |
| `FINNHUB_ENABLED` | `True` | Finnhub aktif mi |
| `FINNHUB_API_KEY` | `""` | Finnhub API anahtarı |
| `YAHOO_ENABLED` | `True` | yfinance aktif mi |

### Provider Ekleme Örneği

```python
# providers/base.py'den türet
class MyProvider(BaseDataProvider):
    name = "myprovider"
    
    async def get_ohlcv(self, symbol: str, timeframe: Timeframe, limit: int) -> pd.DataFrame:
        # Standart DataFrame döndür: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        ...
```

### Failover Davranışı

1. `ProviderManager.get_ohlcv()` öncelik sırasına göre provider dener
2. Sağlıksız provider'lar (`DOWN`) atlanır
3. Hata alınırsa sıradakine geçilir (failover)
4. Tüm provider'lar başarısız olursa boş DataFrame döner

### Sağlık Durumları

- `HEALTHY`: Tam çalışır
- `DEGRADED`: Kısmi sorun (kullanılabilir ama dikkatli)
- `DOWN`: Tamamen erişilemez
- `UNKNOWN`: Henüz kontrol edilmedi

### data_fetcher.py Uyumluluğu

Public API değişmedi. İç implementasyon provider katmanına delege eder:
- `get_ohlcv()` → `ProviderManager.get_ohlcv()`
- `get_fundamentals()` → `YahooProvider.get_fundamentals()`
- `get_daily_stats()` → `ProviderManager.get_daily_stats()`

Fallback: Provider'lar başarısız olursa eski yfinance yöntemi kullanılır.
