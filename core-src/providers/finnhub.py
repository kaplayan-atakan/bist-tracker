"""
BİST Trading Bot - Finnhub REST Provider
Yedek ve geçmiş veri kaynağı - Intraday + Daily OHLCV
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from .base import BaseDataProvider, Timeframe, ProviderHealthStatus, ProviderConfig

logger = logging.getLogger(__name__)

# Finnhub API sabitleri
DEFAULT_BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RATE_LIMIT_CALLS = 60  # Finnhub free tier: 60 calls/minute
RATE_LIMIT_PERIOD = 60  # saniye


class RateLimiter:
    """API rate limit yönetimi"""
    
    def __init__(self, max_calls: int, period: int):
        """
        Rate limiter başlat.
        
        Args:
            max_calls: Periyot başına maksimum çağrı sayısı
            period: Periyot süresi (saniye)
        """
        self.max_calls = max_calls
        self.period = period
        self.calls: List[float] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Rate limit izni al, gerekirse bekle"""
        async with self._lock:
            now = time.time()
            
            # Eski çağrıları temizle
            self.calls = [t for t in self.calls if now - t < self.period]
            
            if len(self.calls) >= self.max_calls:
                # Rate limit'e ulaşıldı, bekle
                wait_time = self.period - (now - self.calls[0]) + 0.1
                if wait_time > 0:
                    logger.warning(f"Rate limit, {wait_time:.1f}s bekleniyor...")
                    await asyncio.sleep(wait_time)
                    # Tekrar temizle
                    now = time.time()
                    self.calls = [t for t in self.calls if now - t < self.period]
            
            self.calls.append(now)


class FinnhubProvider(BaseDataProvider):
    """
    Finnhub REST API üzerinden OHLCV veri sağlayan provider.
    
    Özellikler:
    - Intraday veriler (1m, 5m, 15m)
    - Günlük veriler
    - Backfill/geçmiş veri desteği
    - Rate limit yönetimi
    - Otomatik retry mekanizması
    """
    
    name = "finnhub"
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        Finnhub provider'ı başlat.
        
        Args:
            config: Provider yapılandırması
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp paketi yüklü değil. Yüklemek için: pip install aiohttp")
        
        super().__init__(config)
        
        # API ayarları
        self._base_url = self.config.base_url or DEFAULT_BASE_URL
        self._api_key = self.config.api_key or ""
        self._timeout = self.config.timeout_seconds or DEFAULT_TIMEOUT
        
        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiter
        self._rate_limiter = RateLimiter(RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD)
        
        # İstatistikler
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'rate_limit_hits': 0,
        }
    
    async def _ensure_session(self):
        """HTTP session'ın açık olduğundan emin ol"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._is_connected = True
    
    async def _close_session(self):
        """HTTP session'ı kapat"""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._is_connected = False
    
    async def connect(self) -> bool:
        """Finnhub API bağlantısını başlat"""
        try:
            await self._ensure_session()
            
            # API anahtarı kontrolü
            if not self._api_key:
                logger.warning("Finnhub API anahtarı ayarlanmamış")
            
            # Basit bağlantı testi
            health = await self.check_health()
            return health != ProviderHealthStatus.DOWN
            
        except Exception as e:
            logger.error(f"Finnhub bağlantı hatası: {e}")
            self._health_status = ProviderHealthStatus.DOWN
            return False
    
    async def disconnect(self):
        """Finnhub bağlantısını kapat"""
        await self._close_session()
        logger.info("Finnhub bağlantısı kapatıldı")
    
    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Optional[Dict]:
        """
        Finnhub API'ye istek gönder.
        
        Args:
            endpoint: API endpoint'i
            params: Sorgu parametreleri
            retry_count: Mevcut retry sayısı
            
        Returns:
            Dict: API yanıtı veya None
        """
        await self._ensure_session()
        await self._rate_limiter.acquire()
        
        url = f"{self._base_url}/{endpoint}"
        params = params or {}
        params['token'] = self._api_key
        
        self._stats['total_requests'] += 1
        
        try:
            async with self._session.get(url, params=params) as response:
                if response.status == 200:
                    self._stats['successful_requests'] += 1
                    self._health_status = ProviderHealthStatus.HEALTHY
                    return await response.json()
                
                elif response.status == 429:
                    # Rate limit
                    self._stats['rate_limit_hits'] += 1
                    logger.warning("Finnhub rate limit aşıldı")
                    
                    if retry_count < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** retry_count)
                        await asyncio.sleep(delay)
                        return await self._request(endpoint, params, retry_count + 1)
                    
                    self._health_status = ProviderHealthStatus.DEGRADED
                    return None
                
                elif response.status == 401:
                    logger.error("Finnhub API anahtarı geçersiz")
                    self._health_status = ProviderHealthStatus.DOWN
                    self._last_error = "Geçersiz API anahtarı"
                    return None
                
                elif response.status == 403:
                    # 403 Forbidden - API key geçerli ama bu sembol/endpoint için yetkisiz
                    # Finnhub free tier BİST sembollerini DESTEKLEMİYOR
                    self._stats['failed_requests'] += 1
                    symbol = params.get('symbol', 'bilinmiyor')
                    logger.warning(
                        f"Finnhub 403 Forbidden: '{symbol}' sembolü için erişim yok. "
                        f"Finnhub free tier BİST sembollerini desteklemiyor. "
                        f"Premium abonelik gerekebilir."
                    )
                    self._health_status = ProviderHealthStatus.DEGRADED
                    self._last_error = f"403 Forbidden - Sembol desteklenmiyor: {symbol}"
                    # 403 için retry yapmıyoruz - sembol desteği sorunu
                    return None
                
                else:
                    self._stats['failed_requests'] += 1
                    logger.warning(f"Finnhub API hatası: {response.status}")
                    
                    if retry_count < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** retry_count)
                        await asyncio.sleep(delay)
                        return await self._request(endpoint, params, retry_count + 1)
                    
                    return None
                    
        except asyncio.TimeoutError:
            self._stats['failed_requests'] += 1
            logger.warning(f"Finnhub API timeout ({endpoint})")
            self._health_status = ProviderHealthStatus.DEGRADED
            
            if retry_count < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** retry_count)
                await asyncio.sleep(delay)
                return await self._request(endpoint, params, retry_count + 1)
            
            return None
            
        except Exception as e:
            self._stats['failed_requests'] += 1
            logger.error(f"Finnhub API hatası: {e}")
            self._last_error = str(e)
            
            if retry_count < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** retry_count)
                await asyncio.sleep(delay)
                return await self._request(endpoint, params, retry_count + 1)
            
            return None
    
    def _convert_resolution(self, timeframe: Timeframe) -> str:
        """Timeframe'i Finnhub resolution formatına çevir"""
        mapping = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "1h": "60",
            "1D": "D",
        }
        return mapping.get(timeframe, "D")
    
    def _calculate_time_range(self, timeframe: Timeframe, limit: int) -> tuple:
        """
        Timeframe ve limit'e göre zaman aralığı hesapla.
        
        Args:
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            tuple: (from_timestamp, to_timestamp)
        """
        now = datetime.now()
        to_ts = int(now.timestamp())
        
        # Her timeframe için bar süresi (saniye)
        bar_durations = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "1D": 86400,
        }
        
        bar_duration = bar_durations.get(timeframe, 86400)
        
        # Buffer ekle (%20 fazla)
        total_seconds = bar_duration * limit * 1.2
        from_ts = int((now - timedelta(seconds=total_seconds)).timestamp())
        
        return from_ts, to_ts
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Finnhub'dan OHLCV verisi çeker.
        
        Args:
            symbol: Hisse sembolü (ör: THYAO)
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        try:
            # Sembol formatını çevir
            finnhub_symbol = self.convert_symbol_to_provider_format(symbol, "finnhub")
            resolution = self._convert_resolution(timeframe)
            from_ts, to_ts = self._calculate_time_range(timeframe, limit)
            
            # API isteği
            data = await self._request(
                "stock/candle",
                params={
                    "symbol": finnhub_symbol,
                    "resolution": resolution,
                    "from": from_ts,
                    "to": to_ts,
                }
            )
            
            if not data or data.get("s") == "no_data":
                logger.warning(f"Finnhub'dan veri alınamadı: {symbol}")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # DataFrame'e çevir
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(data.get('t', []), unit='s'),
                'open': data.get('o', []),
                'high': data.get('h', []),
                'low': data.get('l', []),
                'close': data.get('c', []),
                'volume': data.get('v', []),
            })
            
            # Normalize et ve limit uygula
            df = self.normalize_dataframe(df)
            df = df.tail(limit).reset_index(drop=True)
            
            logger.debug(f"Finnhub veri çekildi: {symbol} - {len(df)} bar")
            return df
            
        except Exception as e:
            logger.error(f"Finnhub OHLCV hatası ({symbol}): {e}")
            self._last_error = str(e)
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    async def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        Anlık fiyat bilgisi çeker.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Anlık fiyat bilgileri
        """
        finnhub_symbol = self.convert_symbol_to_provider_format(symbol, "finnhub")
        
        data = await self._request(
            "quote",
            params={"symbol": finnhub_symbol}
        )
        
        if data:
            return {
                'symbol': symbol,
                'current_price': data.get('c'),
                'change': data.get('d'),
                'change_percent': data.get('dp'),
                'high': data.get('h'),
                'low': data.get('l'),
                'open': data.get('o'),
                'previous_close': data.get('pc'),
                'timestamp': datetime.fromtimestamp(data.get('t', 0)),
            }
        
        return None
    
    async def check_health(self) -> ProviderHealthStatus:
        """Aktif sağlık kontrolü yap"""
        try:
            # Basit bir API çağrısı ile test et
            data = await self._request(
                "quote",
                params={"symbol": "BIST:THYAO"}
            )
            
            if data and 'c' in data:
                self._health_status = ProviderHealthStatus.HEALTHY
            else:
                self._health_status = ProviderHealthStatus.DEGRADED
                
        except Exception as e:
            self._health_status = ProviderHealthStatus.DOWN
            self._last_error = str(e)
        
        return self._health_status
    
    def get_stats(self) -> Dict:
        """İstatistikleri döndür"""
        return self._stats.copy()


# Singleton instance
_finnhub_provider_instance: Optional[FinnhubProvider] = None


def get_finnhub_provider(config: Optional[ProviderConfig] = None) -> FinnhubProvider:
    """Finnhub provider singleton instance döndürür"""
    global _finnhub_provider_instance
    if _finnhub_provider_instance is None:
        _finnhub_provider_instance = FinnhubProvider(config)
    return _finnhub_provider_instance
