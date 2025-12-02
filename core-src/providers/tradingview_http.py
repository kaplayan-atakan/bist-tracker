"""
BİST Trading Bot - TradingView HTTP Provider
HTTP Screener API üzerinden anlık fiyat ve OHLC snapshot verisi

ÖNEMLİ NOTLAR:
- Bu provider OHLC snapshot verisi sağlar (intraday polling için).
- Gerçek zamanlı streaming için TradingViewWebSocketProvider kullanın.
- Anonim modda veriler 15 dakika gecikmelidir (delayed_streaming_900).
- ~200-250ms latency ile düşük rate limit riski.

Başarıyla test edildi: experiments/tradingview_http_poll_test.py
Screener URL: https://scanner.tradingview.com/turkey/scan
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import pandas as pd

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from .base import BaseDataProvider, Timeframe, ProviderHealthStatus, ProviderConfig

logger = logging.getLogger(__name__)

# ============================================================================
# SABİTLER - Çalışan test scriptinden alındı
# ============================================================================

# HTTP endpoint
DEFAULT_SCREENER_URL = "https://scanner.tradingview.com/turkey/scan"

# Timeout ayarları
REQUEST_TIMEOUT = 10  # saniye
HEALTH_CHECK_INTERVAL = 30  # saniye

# Rate limiting - TradingView cömert ama dikkatli olalım
MIN_REQUEST_INTERVAL = 0.5  # saniye - aynı sembol için minimum bekleme
BATCH_SIZE = 50  # Tek istekte maksimum sembol sayısı

# Screener alanları - TradingView screener API'den
SCREENER_COLUMNS = [
    "name",
    "close",
    "open",
    "high",
    "low",
    "volume",
    "change",
    "change_abs",
    "Recommend.All",
    "update_mode",
    "description",
    "exchange",
    "sector",
    "market_cap_basic",
    "price_earnings_ttm",
    "price_book_ratio",
]


# ============================================================================
# OHLCV SNAPSHOT DATACLASS
# ============================================================================

@dataclass
class OHLCVSnapshot:
    """Tek bir sembolün anlık OHLCV verisi."""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    change: float
    change_percent: float
    timestamp: datetime
    update_mode: str
    description: str = ""
    exchange: str = "BIST"
    
    # Opsiyonel fundamental veriler
    sector: str = ""
    market_cap: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0


# ============================================================================
# ANA PROVIDER SINIFI
# ============================================================================

class TradingViewHTTPProvider(BaseDataProvider):
    """
    TradingView HTTP Screener API üzerinden OHLC snapshot verisi sağlayan provider.
    
    KULLANIM ALANLARI:
    - Intraday anlık fiyat taramaları
    - Birden fazla sembol için toplu veri çekme
    - Gerçek zamanlı WebSocket'e fallback
    
    VERİ MODU:
    - Anonim kullanımda veriler 15 dakika gecikmelidir (delayed_streaming_900).
    - Gerçek zamanlı veri için TradingView authentication gerekir.
    
    ÖZELLİKLER:
    - Düşük latency (~200-250ms)
    - Batch sorgu desteği (50 sembol/istek)
    - Temel analiz verileri (sector, market_cap, PE, PB)
    - Rate limit koruması
    """
    
    name = "tradingview_http"
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        TradingView HTTP provider'ı başlat.
        
        Args:
            config: Provider yapılandırması
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp paketi yüklü değil. Yüklemek için: pip install aiohttp")
        
        super().__init__(config)
        
        # HTTP ayarları
        self._screener_url = self.config.base_url or DEFAULT_SCREENER_URL
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiting
        self._last_request_times: Dict[str, float] = {}
        
        # Sağlık takibi
        self._consecutive_failures = 0
        self._last_success_time: Optional[float] = None
        
        logger.info(f"{self.name} provider başlatıldı (URL: {self._screener_url})")
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """HTTP session'ın hazır olduğundan emin ol."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def disconnect(self):
        """HTTP session'ı kapat."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        logger.info("TradingView HTTP session kapatıldı")
    
    def _build_screener_payload(
        self,
        symbols: List[str],
        columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        TradingView screener API için payload oluşturur.
        
        Args:
            symbols: Sembol listesi (GARAN, THYAO, vs.)
            columns: İstenen alanlar (None ise varsayılan kullanılır)
            
        Returns:
            Dict: API request payload
        """
        # Sembolleri TradingView formatına çevir
        tv_symbols = [
            self.convert_symbol_to_provider_format(s, "tradingview")
            for s in symbols
        ]
        
        payload = {
            "markets": ["turkey"],
            "symbols": {"tickers": tv_symbols},
            "columns": columns or SCREENER_COLUMNS,
            "range": [0, len(symbols)],
        }
        
        return payload
    
    def _parse_screener_response(self, data: Dict, symbols: List[str]) -> List[OHLCVSnapshot]:
        """
        TradingView screener API yanıtını parse eder.
        
        Args:
            data: API yanıtı
            symbols: İstenen semboller (sıra için referans)
            
        Returns:
            List[OHLCVSnapshot]: Parse edilmiş veriler
        """
        snapshots = []
        
        try:
            rows = data.get("data", [])
            
            for row in rows:
                try:
                    symbol_full = row.get("s", "")  # BIST:GARAN formatı
                    values = row.get("d", [])
                    
                    if not symbol_full or not values:
                        continue
                    
                    # Sembol adını çıkar
                    symbol = symbol_full.replace("BIST:", "")
                    
                    # Değerleri column sırasına göre eşleştir
                    col_map = {}
                    for i, col_name in enumerate(SCREENER_COLUMNS):
                        if i < len(values):
                            col_map[col_name] = values[i]
                    
                    # OHLCVSnapshot oluştur
                    snapshot = OHLCVSnapshot(
                        symbol=symbol,
                        open=float(col_map.get("open", 0) or 0),
                        high=float(col_map.get("high", 0) or 0),
                        low=float(col_map.get("low", 0) or 0),
                        close=float(col_map.get("close", 0) or 0),
                        volume=int(col_map.get("volume", 0) or 0),
                        change=float(col_map.get("change", 0) or 0),
                        change_percent=float(col_map.get("change_abs", 0) or 0),
                        timestamp=datetime.now(),
                        update_mode=str(col_map.get("update_mode", "unknown")),
                        description=str(col_map.get("description", "")),
                        exchange=str(col_map.get("exchange", "BIST")),
                        sector=str(col_map.get("sector", "")),
                        market_cap=float(col_map.get("market_cap_basic", 0) or 0),
                        pe_ratio=float(col_map.get("price_earnings_ttm", 0) or 0),
                        pb_ratio=float(col_map.get("price_book_ratio", 0) or 0),
                    )
                    snapshots.append(snapshot)
                    
                except Exception as e:
                    logger.debug(f"Row parse hatası: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Screener response parse hatası: {e}")
        
        return snapshots
    
    async def get_snapshots(
        self,
        symbols: List[str],
        columns: Optional[List[str]] = None
    ) -> List[OHLCVSnapshot]:
        """
        Birden fazla sembol için anlık OHLCV snapshot'ları getirir.
        
        NOT: Anonim kullanımda veriler 15 dakika gecikmelidir.
        
        Args:
            symbols: Sembol listesi (maks 50)
            columns: İstenen alanlar (None ise varsayılan)
            
        Returns:
            List[OHLCVSnapshot]: Anlık veriler
        """
        if not symbols:
            return []
        
        # Batch boyutunu kontrol et
        if len(symbols) > BATCH_SIZE:
            logger.warning(f"Sembol sayısı {BATCH_SIZE}'den fazla, batch'lere bölünüyor")
            all_snapshots = []
            for i in range(0, len(symbols), BATCH_SIZE):
                batch = symbols[i:i + BATCH_SIZE]
                batch_snapshots = await self.get_snapshots(batch, columns)
                all_snapshots.extend(batch_snapshots)
                await asyncio.sleep(MIN_REQUEST_INTERVAL)
            return all_snapshots
        
        try:
            session = await self._ensure_session()
            payload = self._build_screener_payload(symbols, columns)
            
            start_time = time.time()
            
            async with session.post(self._screener_url, json=payload) as response:
                latency = (time.time() - start_time) * 1000
                
                if response.status != 200:
                    self._consecutive_failures += 1
                    logger.error(f"TradingView HTTP hatası: {response.status}")
                    self._health_status = ProviderHealthStatus.DEGRADED
                    return []
                
                data = await response.json()
                
            snapshots = self._parse_screener_response(data, symbols)
            
            # Başarılı istek
            self._consecutive_failures = 0
            self._last_success_time = time.time()
            self._health_status = ProviderHealthStatus.HEALTHY
            
            logger.debug(f"TradingView HTTP: {len(snapshots)} snapshot alındı ({latency:.0f}ms)")
            
            return snapshots
            
        except asyncio.TimeoutError:
            self._consecutive_failures += 1
            logger.error("TradingView HTTP timeout")
            self._health_status = ProviderHealthStatus.DEGRADED
            return []
            
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"TradingView HTTP hatası: {e}")
            self._health_status = ProviderHealthStatus.DOWN
            self._last_error = str(e)
            return []
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Tek sembol için OHLCV snapshot verisi getirir.
        
        DİKKAT: Bu provider SADECE anlık (current) veri sağlar.
        Geçmiş (historical) veriler için YahooProvider kullanın.
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi (sadece mevcut bar döner)
            limit: Bar sayısı (dikkate alınmaz - sadece 1 bar döner)
            
        Returns:
            DataFrame: Tek satırlık OHLCV verisi
        """
        snapshots = await self.get_snapshots([symbol])
        
        if not snapshots:
            logger.warning(f"TradingView HTTP: {symbol} için veri alınamadı")
            return pd.DataFrame()
        
        snapshot = snapshots[0]
        
        df = pd.DataFrame([{
            'timestamp': snapshot.timestamp,
            'open': snapshot.open,
            'high': snapshot.high,
            'low': snapshot.low,
            'close': snapshot.close,
            'volume': snapshot.volume,
        }])
        
        return self.normalize_dataframe(df)
    
    async def get_daily_stats(self, symbol: str) -> Dict[str, Any]:
        """
        Sembol için günlük istatistikleri getirir.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Günlük istatistikler (current_price, volume, daily_change_percent, vs.)
        """
        snapshots = await self.get_snapshots([symbol])
        
        if not snapshots:
            return {}
        
        snapshot = snapshots[0]
        
        return {
            'current_price': snapshot.close,
            'open': snapshot.open,
            'high': snapshot.high,
            'low': snapshot.low,
            'volume': snapshot.volume,
            'daily_change': snapshot.change,
            'daily_change_percent': snapshot.change_percent,
            'sector': snapshot.sector,
            'market_cap': snapshot.market_cap,
            'pe_ratio': snapshot.pe_ratio,
            'pb_ratio': snapshot.pb_ratio,
            'update_mode': snapshot.update_mode,
            'timestamp': snapshot.timestamp.isoformat(),
        }
    
    async def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Sembol için temel analiz verilerini getirir.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Temel analiz verileri
        """
        snapshots = await self.get_snapshots([symbol])
        
        if not snapshots:
            return {}
        
        snapshot = snapshots[0]
        
        return {
            'sector': snapshot.sector,
            'market_cap': snapshot.market_cap,
            'pe_ratio': snapshot.pe_ratio,
            'pb_ratio': snapshot.pb_ratio,
            'description': snapshot.description,
        }
    
    async def get_health(self) -> ProviderHealthStatus:
        """
        Sağlık durumunu döndürür.
        
        HEALTHY: Son istek başarılı
        DEGRADED: Birkaç ardışık hata
        DOWN: Çok fazla ardışık hata veya session kapalı
        """
        if self._consecutive_failures >= 5:
            return ProviderHealthStatus.DOWN
        elif self._consecutive_failures >= 2:
            return ProviderHealthStatus.DEGRADED
        return self._health_status


# ============================================================================
# SINGLETON FACTORY
# ============================================================================

_tradingview_http_provider_instance: Optional[TradingViewHTTPProvider] = None


def get_tradingview_http_provider(config: Optional[ProviderConfig] = None) -> TradingViewHTTPProvider:
    """TradingView HTTP provider singleton instance döndürür."""
    global _tradingview_http_provider_instance
    if _tradingview_http_provider_instance is None:
        _tradingview_http_provider_instance = TradingViewHTTPProvider(config)
    return _tradingview_http_provider_instance
