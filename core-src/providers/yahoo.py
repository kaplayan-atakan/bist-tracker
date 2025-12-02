"""
BİST Trading Bot - Yahoo (yfinance) Provider
Mevcut yfinance fonksiyonları için adapter - temel analiz ve günlük veri
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from .base import BaseDataProvider, Timeframe, ProviderHealthStatus, ProviderConfig

logger = logging.getLogger(__name__)

# Thread pool for sync yfinance calls
_executor = ThreadPoolExecutor(max_workers=4)


class YahooProvider(BaseDataProvider):
    """
    yfinance kütüphanesi üzerinden veri sağlayan provider.
    
    Özellikler:
    - Günlük OHLCV verileri
    - Temel analiz verileri (F/K, PD/DD, piyasa değeri vb.)
    - Mevcut data_fetcher fonksiyonlarıyla uyumluluk
    - Sync yfinance çağrılarını async'e çevirme
    """
    
    name = "yahoo"
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        Yahoo provider'ı başlat.
        
        Args:
            config: Provider yapılandırması
        """
        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance paketi yüklü değil. Yüklemek için: pip install yfinance")
        
        super().__init__(config)
        
        # Cache
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._cache_duration = 60  # saniye
        
        # Bağlantı durumu
        self._is_connected = True
        self._health_status = ProviderHealthStatus.HEALTHY
    
    def _get_yfinance_symbol(self, symbol: str) -> str:
        """BİST sembolünü yfinance formatına çevirir"""
        symbol = symbol.upper().strip()
        if not symbol.endswith('.IS'):
            return f"{symbol}.IS"
        return symbol
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Cache geçerli mi kontrol et"""
        if cache_key not in self._cache_timestamp:
            return False
        
        import time
        elapsed = time.time() - self._cache_timestamp[cache_key]
        return elapsed < self._cache_duration
    
    def _set_cache(self, cache_key: str, data: Any):
        """Cache'e veri kaydet"""
        import time
        self._cache[cache_key] = data
        self._cache_timestamp[cache_key] = time.time()
    
    def _get_cache(self, cache_key: str) -> Optional[Any]:
        """Cache'den veri al"""
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None
    
    def _sync_get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
    ) -> pd.DataFrame:
        """
        Senkron OHLCV veri çekme (thread'de çalışır).
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        try:
            yf_symbol = self._get_yfinance_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            
            # Timeframe'e göre period ve interval ayarla
            if timeframe == "1D":
                period = f"{limit}d"
                interval = "1d"
            elif timeframe == "1h":
                period = f"{min(limit // 24 + 1, 730)}d"  # Max 730 gün
                interval = "1h"
            elif timeframe == "15m":
                period = "60d"  # yfinance limit
                interval = "15m"
            elif timeframe == "5m":
                period = "60d"
                interval = "5m"
            elif timeframe == "1m":
                period = "7d"  # yfinance 1m limit
                interval = "1m"
            else:
                period = f"{limit}d"
                interval = "1d"
            
            # Veriyi çek
            df = ticker.history(period=period, interval=interval)
            
            if df is None or df.empty:
                logger.warning(f"yfinance veri döndürmedi: {symbol}")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # DataFrame'i normalize et
            df = df.reset_index()
            df.columns = [col.lower() for col in df.columns]
            
            # Date/Datetime sütununu timestamp'e çevir
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'timestamp'})
            elif 'datetime' in df.columns:
                df = df.rename(columns={'datetime': 'timestamp'})
            
            # Gereksiz sütunları kaldır
            keep_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df = df[[col for col in keep_columns if col in df.columns]]
            
            # Limit uygula
            df = df.tail(limit).reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"yfinance OHLCV hatası ({symbol}): {e}")
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        yfinance'den OHLCV verisi çeker (async wrapper).
        
        Args:
            symbol: Hisse sembolü (ör: THYAO)
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        # Cache kontrolü
        cache_key = f"ohlcv_{symbol}_{timeframe}_{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache'den döndürülüyor: {symbol}")
            return cached
        
        try:
            # Sync fonksiyonu executor'da çalıştır
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(
                _executor,
                self._sync_get_ohlcv,
                symbol,
                timeframe,
                limit
            )
            
            # Normalize et
            df = self.normalize_dataframe(df)
            
            # Cache'e kaydet
            if not df.empty:
                self._set_cache(cache_key, df)
                self._health_status = ProviderHealthStatus.HEALTHY
            
            logger.debug(f"yfinance veri çekildi: {symbol} - {len(df)} bar")
            return df
            
        except Exception as e:
            logger.error(f"yfinance get_ohlcv hatası ({symbol}): {e}")
            self._last_error = str(e)
            self._health_status = ProviderHealthStatus.DEGRADED
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    def _sync_get_fundamentals(self, symbol: str) -> Optional[Dict]:
        """
        Senkron temel analiz verisi çekme.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Temel analiz verileri
        """
        try:
            yf_symbol = self._get_yfinance_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
            
            fundamentals = {
                'symbol': symbol,
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'pb_ratio': info.get('priceToBook'),
                'ps_ratio': info.get('priceToSalesTrailing12Months'),
                'market_cap': info.get('marketCap'),
                'enterprise_value': info.get('enterpriseValue'),
                'profit_margin': info.get('profitMargins'),
                'debt_to_equity': info.get('debtToEquity'),
                'revenue_growth': info.get('revenueGrowth'),
                'earnings_growth': info.get('earningsGrowth'),
                'dividend_yield': info.get('dividendYield'),
                'beta': info.get('beta'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'long_name': info.get('longName'),
                'website': info.get('website'),
            }
            
            return fundamentals
            
        except Exception as e:
            logger.warning(f"yfinance temel veri hatası ({symbol}): {e}")
            return None
    
    async def get_fundamentals(self, symbol: str) -> Optional[Dict]:
        """
        yfinance'den temel analiz verisi çeker (async).
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Temel analiz verileri
        """
        # Cache kontrolü
        cache_key = f"fundamentals_{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            loop = asyncio.get_running_loop()
            fundamentals = await loop.run_in_executor(
                _executor,
                self._sync_get_fundamentals,
                symbol
            )
            
            if fundamentals:
                self._set_cache(cache_key, fundamentals)
            
            return fundamentals
            
        except Exception as e:
            logger.error(f"yfinance get_fundamentals hatası ({symbol}): {e}")
            return None
    
    def _sync_get_daily_stats(self, symbol: str) -> Optional[Dict]:
        """
        Günlük istatistikleri senkron çeker.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Günlük istatistikler
        """
        try:
            yf_symbol = self._get_yfinance_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            
            # Son 5 günlük veri çek
            df = ticker.history(period="5d", interval="1d")
            
            if df is None or len(df) < 2:
                return None
            
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            
            # Günlük değişim hesapla
            daily_change = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
            daily_volume_tl = today['Volume'] * today['Close']
            
            stats = {
                'symbol': symbol,
                'current_price': today['Close'],
                'open': today['Open'],
                'high': today['High'],
                'low': today['Low'],
                'close': today['Close'],
                'volume': today['Volume'],
                'daily_volume_tl': daily_volume_tl,
                'daily_change_percent': daily_change,
                'timestamp': today.name,
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"yfinance daily stats hatası ({symbol}): {e}")
            return None
    
    async def get_daily_stats(self, symbol: str) -> Optional[Dict]:
        """
        Günlük istatistikleri çeker (async).
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Günlük istatistikler
        """
        try:
            loop = asyncio.get_running_loop()
            stats = await loop.run_in_executor(
                _executor,
                self._sync_get_daily_stats,
                symbol
            )
            return stats
            
        except Exception as e:
            logger.error(f"yfinance get_daily_stats hatası ({symbol}): {e}")
            return None
    
    def _sync_get_bid_ask_spread(self, symbol: str) -> Optional[float]:
        """
        Spread tahmini hesaplar (senkron).
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: Spread yüzdesi
        """
        try:
            yf_symbol = self._get_yfinance_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            
            df = ticker.history(period="1d", interval="1d")
            if df is None or df.empty:
                return None
            
            last_bar = df.iloc[-1]
            spread_estimate = ((last_bar['High'] - last_bar['Low']) / last_bar['Close']) * 100
            
            return spread_estimate
            
        except Exception as e:
            logger.debug(f"Spread hesaplama hatası ({symbol}): {e}")
            return None
    
    async def get_bid_ask_spread(self, symbol: str) -> Optional[float]:
        """
        Alış-satış makası tahmini çeker (async).
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: Spread yüzdesi
        """
        try:
            loop = asyncio.get_running_loop()
            spread = await loop.run_in_executor(
                _executor,
                self._sync_get_bid_ask_spread,
                symbol
            )
            return spread
            
        except Exception as e:
            logger.debug(f"Spread çekme hatası ({symbol}): {e}")
            return None
    
    async def check_health(self) -> ProviderHealthStatus:
        """Aktif sağlık kontrolü yap"""
        try:
            df = await self.get_ohlcv("THYAO", "1D", limit=1)
            
            if df is not None and not df.empty:
                self._health_status = ProviderHealthStatus.HEALTHY
            else:
                self._health_status = ProviderHealthStatus.DEGRADED
                
        except Exception as e:
            self._health_status = ProviderHealthStatus.DOWN
            self._last_error = str(e)
        
        return self._health_status
    
    def clear_cache(self):
        """Cache'i temizle"""
        self._cache.clear()
        self._cache_timestamp.clear()
        logger.debug("Yahoo provider cache temizlendi")


# Singleton instance
_yahoo_provider_instance: Optional[YahooProvider] = None


def get_yahoo_provider(config: Optional[ProviderConfig] = None) -> YahooProvider:
    """Yahoo provider singleton instance döndürür"""
    global _yahoo_provider_instance
    if _yahoo_provider_instance is None:
        _yahoo_provider_instance = YahooProvider(config)
    return _yahoo_provider_instance
