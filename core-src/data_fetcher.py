"""
BİST Trading Bot - Data Fetcher Module
Veri toplama katmanı - fiyat, hacim ve temel verileri toplar

Not: Sprint 1 ile birlikte bu modül artık providers katmanını kullanmaktadır.
Public API geriye dönük uyumlu kalacak şekilde korunmuştur.
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import logging
from functools import lru_cache

import config

# Yeni provider katmanı importları
try:
    from providers import get_provider_manager, ProviderConfig
    from providers.yahoo import get_yahoo_provider
    PROVIDERS_AVAILABLE = True
except ImportError:
    PROVIDERS_AVAILABLE = False

# Eski yfinance import (geriye dönük uyumluluk için)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    BİST hisse verilerini toplayan sınıf.
    
    Sprint 1 ile birlikte yeni provider katmanını kullanır.
    Public API geriye dönük uyumlu kalacak şekilde korunmuştur.
    """
    
    def __init__(self, use_providers: bool = True):
        """
        DataFetcher'ı başlat.
        
        Args:
            use_providers: Yeni provider katmanını kullan (varsayılan: True)
        """
        self.cache = {}
        self.cache_timestamp = {}
        self._use_providers = use_providers and PROVIDERS_AVAILABLE
        self._provider_manager = None
        self._yahoo_provider = None
        
        # Provider'ları başlat
        if self._use_providers:
            self._init_providers()
        
        logger.info(f"DataFetcher başlatıldı (providers: {self._use_providers})")
    
    def _init_providers(self):
        """Provider manager'ı başlat"""
        try:
            # Config'den provider ayarlarını oku
            finnhub_config = ProviderConfig(
                name="finnhub",
                enabled=getattr(config, 'FINNHUB_ENABLED', True),
                api_key=getattr(config, 'FINNHUB_API_KEY', ''),
                base_url=getattr(config, 'FINNHUB_BASE_URL', 'https://finnhub.io/api/v1'),
                timeout_seconds=getattr(config, 'FINNHUB_TIMEOUT', 30),
            )
            
            tradingview_config = ProviderConfig(
                name="tradingview",
                enabled=getattr(config, 'TRADINGVIEW_ENABLED', True),
                ws_url=getattr(config, 'TRADINGVIEW_WS_URL', None),
            )
            
            yahoo_config = ProviderConfig(
                name="yahoo",
                enabled=getattr(config, 'YAHOO_ENABLED', True),
            )
            
            self._provider_manager = get_provider_manager(
                tradingview_config=tradingview_config,
                finnhub_config=finnhub_config,
                yahoo_config=yahoo_config,
            )
            
            # Doğrudan Yahoo provider erişimi (temel analiz için)
            self._yahoo_provider = get_yahoo_provider(yahoo_config)
            
        except Exception as e:
            logger.error(f"Provider başlatma hatası: {e}")
            self._use_providers = False
        
    def get_symbol_list(self) -> List[str]:
        """
        BİST'te işlem gören hisse listesini döndürür
        
        Returns:
            List[str]: Sembol listesi
        """
        # Kara liste filtresi uygula
        symbols = [s for s in config.BIST_SYMBOLS if s not in config.BLACKLIST_SYMBOLS]
        logger.info(f"Toplam {len(symbols)} sembol taranacak")
        return symbols
    
    def _get_yfinance_symbol(self, symbol: str) -> str:
        """
        BİST sembolu için yfinance formatına çevirir
        
        Args:
            symbol: BİST sembol kodu (ör: THYAO)
            
        Returns:
            str: yfinance formatı (ör: THYAO.IS)
        """
        if not symbol.endswith('.IS'):
            return f"{symbol}.IS"
        return symbol
    
    def _convert_timeframe(self, timeframe: str) -> str:
        """Timeframe'i yeni provider formatına çevir"""
        mapping = {
            '1d': '1D',
            '1h': '1h',
            '15m': '15m',
            '5m': '5m',
            '1m': '1m',
        }
        return mapping.get(timeframe.lower(), '1D')
    
    def get_ohlcv(self, symbol: str, timeframe: str = '1d', limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Sembol için OHLCV verilerini çeker.
        
        Public, geriye dönük uyumlu senkron API.
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi ('1d', '15m', vb.)
            limit: Kaç bar veri çekilecek
            
        Returns:
            DataFrame: OHLCV verileri veya None
        """
        # Cache kontrolü
        cache_key = f"{symbol}_{timeframe}_{limit}"
        if cache_key in self.cache:
            cache_time = self.cache_timestamp.get(cache_key, 0)
            if time.time() - cache_time < config.CACHE_DURATION_SECONDS:
                logger.debug(f"Cache'den veri döndürülüyor: {symbol}")
                return self.cache[cache_key]
        
        # Provider katmanı kullanılmıyorsa doğrudan legacy'ye git
        if not self._use_providers or not self._provider_manager:
            return self._legacy_get_ohlcv(symbol, timeframe, limit)
        
        # Provider katmanını güvenli şekilde kullanmaya çalış
        try:
            # Halihazırda çalışan bir event loop var mı kontrol et
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop is None:
                # Çalışan loop yok: asyncio.run kullanmak güvenli
                df = asyncio.run(self._async_get_ohlcv_via_providers(symbol, timeframe, limit))
            else:
                # Zaten async context'teyiz (örn: async fonksiyondan çağrıldı)
                # Sprint 1 için nested loop sorunlarından kaçınmak adına
                # legacy senkron implementasyona düş
                logger.debug(
                    "get_ohlcv() async context'ten çağrıldı; legacy yfinance kullanılıyor. "
                    "Async kullanım için async_get_ohlcv() tercih edin."
                )
                return self._legacy_get_ohlcv(symbol, timeframe, limit)
            
            if df is not None and not df.empty:
                self.cache[cache_key] = df
                self.cache_timestamp[cache_key] = time.time()
                return df
            else:
                # Provider boş döndü, legacy'ye düş
                logger.debug(f"Provider boş veri döndürdü, legacy kullanılıyor: {symbol}")
                return self._legacy_get_ohlcv(symbol, timeframe, limit)
                
        except Exception as e:
            logger.warning(f"Provider hatası, legacy yfinance'e düşülüyor: {e}")
            return self._legacy_get_ohlcv(symbol, timeframe, limit)
    
    async def _async_get_ohlcv_via_providers(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """
        Provider katmanı üzerinden async OHLCV çekme.
        
        Bu internal metod, ProviderManager'ı kullanarak veri çeker.
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        provider_timeframe = self._convert_timeframe(timeframe)
        df = await self._provider_manager.get_ohlcv(symbol, provider_timeframe, limit)
        return df
    
    def _legacy_get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """
        Eski yfinance yöntemiyle OHLCV çeker (geriye dönük uyumluluk).
        """
        if not YFINANCE_AVAILABLE:
            logger.error("yfinance paketi yüklü değil")
            return None
            
        try:
            yf_symbol = self._get_yfinance_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            
            # Timeframe'e göre period hesapla
            if timeframe == '1d':
                period = f"{limit}d"
                interval = '1d'
            elif timeframe == '15m':
                period = "5d"
                interval = '15m'
            elif timeframe == '5m':
                period = "1d"
                interval = '5m'
            else:
                period = f"{limit}d"
                interval = timeframe
            
            df = ticker.history(period=period, interval=interval)
            
            if df is None or df.empty:
                logger.warning(f"Veri çekilemedi: {symbol}")
                return None
            
            df.columns = [col.lower() for col in df.columns]
            
            # Cache'e kaydet
            cache_key = f"{symbol}_{timeframe}_{limit}"
            self.cache[cache_key] = df
            self.cache_timestamp[cache_key] = time.time()
            
            logger.debug(f"Veri başarıyla çekildi: {symbol} - {len(df)} bar")
            return df
            
        except Exception as e:
            logger.error(f"Veri çekme hatası ({symbol}): {str(e)}")
            return None
    
    def get_daily_stats(self, symbol: str) -> Optional[Dict]:
        """
        Güncel fiyat, hacim ve günlük değişim bilgilerini döndürür
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            dict: Günlük istatistikler veya None
        """
        # Provider katmanı kullanılmıyorsa doğrudan legacy'ye git
        if not self._use_providers or not self._provider_manager:
            return self._legacy_get_daily_stats(symbol)
        
        try:
            # Halihazırda çalışan bir event loop var mı kontrol et
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop is None:
                # Çalışan loop yok: asyncio.run kullanmak güvenli
                stats = asyncio.run(self._provider_manager.get_daily_stats(symbol))
            else:
                # Async context'te, legacy'ye düş
                return self._legacy_get_daily_stats(symbol)
            
            if stats:
                return stats
                    
        except Exception as e:
            logger.warning(f"Provider daily_stats hatası: {e}")
        
        # Fallback: Eski yöntem
        return self._legacy_get_daily_stats(symbol)
    
    def _legacy_get_daily_stats(self, symbol: str) -> Optional[Dict]:
        """Eski yöntemle daily stats çeker"""
        try:
            df = self.get_ohlcv(symbol, timeframe='1d', limit=5)
            
            if df is None or len(df) < 2:
                return None
            
            # Son iki günün verisi
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            
            # Günlük değişim hesapla
            daily_change = ((today['close'] - yesterday['close']) / yesterday['close']) * 100
            
            # Günlük hacim (TL cinsinden)
            daily_volume_tl = today['volume'] * today['close']
            
            stats = {
                'symbol': symbol,
                'current_price': today['close'],
                'open': today['open'],
                'high': today['high'],
                'low': today['low'],
                'close': today['close'],
                'volume': today['volume'],
                'daily_volume_tl': daily_volume_tl,
                'daily_change_percent': daily_change,
                'timestamp': today.name
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Günlük stats hatası ({symbol}): {str(e)}")
            return None
    
    def get_fundamentals(self, symbol: str) -> Optional[Dict]:
        """
        Temel analiz verilerini çeker (F/K, PD/DD, vb.)
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            dict: Temel veriler veya None
        """
        # Provider katmanı kullanılmıyorsa doğrudan legacy'ye git
        if not self._use_providers or not self._yahoo_provider:
            return self._legacy_get_fundamentals(symbol)
        
        try:
            # Halihazırda çalışan bir event loop var mı kontrol et
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop is None:
                # Çalışan loop yok: asyncio.run kullanmak güvenli
                fundamentals = asyncio.run(self._yahoo_provider.get_fundamentals(symbol))
            else:
                # Async context'te, legacy'ye düş
                return self._legacy_get_fundamentals(symbol)
            
            if fundamentals:
                return fundamentals
                    
        except Exception as e:
            logger.warning(f"Provider fundamentals hatası: {e}")
        
        # Fallback: Eski yöntem
        return self._legacy_get_fundamentals(symbol)
    
    def _legacy_get_fundamentals(self, symbol: str) -> Optional[Dict]:
        """Eski yöntemle temel analiz verisi çeker"""
        if not YFINANCE_AVAILABLE:
            return None
            
        try:
            yf_symbol = self._get_yfinance_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
            
            fundamentals = {
                'symbol': symbol,
                'pe_ratio': info.get('trailingPE', None),
                'forward_pe': info.get('forwardPE', None),
                'pb_ratio': info.get('priceToBook', None),
                'ps_ratio': info.get('priceToSalesTrailing12Months', None),
                'market_cap': info.get('marketCap', None),
                'enterprise_value': info.get('enterpriseValue', None),
                'profit_margin': info.get('profitMargins', None),
                'debt_to_equity': info.get('debtToEquity', None),
                'revenue_growth': info.get('revenueGrowth', None),
                'earnings_growth': info.get('earningsGrowth', None),
                'sector': info.get('sector', None),
                'industry': info.get('industry', None)
            }
            
            return fundamentals
            
        except Exception as e:
            logger.warning(f"Temel veri çekme hatası ({symbol}): {str(e)}")
            return None
    
    def get_bid_ask_spread(self, symbol: str) -> Optional[float]:
        """
        Alış-satış makası hesaplar (tahminî)
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: Spread yüzdesi veya None
        """
        # Provider katmanı kullanılmıyorsa doğrudan legacy'ye git
        if not self._use_providers or not self._provider_manager:
            return self._legacy_get_bid_ask_spread(symbol)
        
        try:
            # Halihazırda çalışan bir event loop var mı kontrol et
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop is None:
                # Çalışan loop yok: asyncio.run kullanmak güvenli
                spread = asyncio.run(self._provider_manager.get_bid_ask_spread(symbol))
            else:
                # Async context'te, legacy'ye düş
                return self._legacy_get_bid_ask_spread(symbol)
            
            if spread is not None:
                return spread
                    
        except Exception as e:
            logger.debug(f"Provider spread hatası: {e}")
        
        # Fallback: Eski yöntem
        return self._legacy_get_bid_ask_spread(symbol)
    
    def _legacy_get_bid_ask_spread(self, symbol: str) -> Optional[float]:
        """Eski yöntemle spread hesaplar"""
        try:
            df = self.get_ohlcv(symbol, timeframe='1d', limit=1)
            if df is None or df.empty:
                return None
            
            last_bar = df.iloc[-1]
            spread_estimate = ((last_bar['high'] - last_bar['low']) / last_bar['close']) * 100
            
            return spread_estimate
            
        except Exception as e:
            logger.debug(f"Spread hesaplama hatası ({symbol}): {str(e)}")
            return None
    
    def batch_fetch_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Birden fazla sembol için toplu veri çeker
        
        Args:
            symbols: Sembol listesi
            
        Returns:
            dict: Sembol -> veri dict mapping
        """
        results = {}
        
        for symbol in symbols:
            try:
                # OHLCV verisi
                ohlcv = self.get_ohlcv(symbol, timeframe='1d', limit=config.HISTORICAL_DAYS)
                
                # Günlük stats
                daily_stats = self.get_daily_stats(symbol)
                
                # Temel veriler (opsiyonel)
                fundamentals = self.get_fundamentals(symbol)
                
                if ohlcv is not None and daily_stats is not None:
                    results[symbol] = {
                        'ohlcv': ohlcv,
                        'daily_stats': daily_stats,
                        'fundamentals': fundamentals
                    }
                    
                # Rate limiting
                time.sleep(0.1)  # API'ye çok hızlı istek atmamak için
                
            except Exception as e:
                logger.error(f"Batch fetch hatası ({symbol}): {str(e)}")
                continue
        
        logger.info(f"Batch fetch tamamlandı: {len(results)}/{len(symbols)} başarılı")
        return results
    
    def get_provider_stats(self) -> Optional[Dict]:
        """
        Provider istatistiklerini döndürür (Sprint 1).
        
        Returns:
            Dict: Provider istatistikleri
        """
        if self._use_providers and self._provider_manager:
            return self._provider_manager.get_stats()
        return None
    
    async def async_get_ohlcv(self, symbol: str, timeframe: str = '1d', limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Async OHLCV veri çekme API'si.
        
        Async context'lerden (örn: async fonksiyonlar, Sprint 2 main loop) 
        doğrudan çağrılabilir.
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        if self._use_providers and self._provider_manager:
            return await self._async_get_ohlcv_via_providers(symbol, timeframe, limit)
        
        # Provider yoksa, legacy implementasyonu executor'da çalıştır
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, self._legacy_get_ohlcv, symbol, timeframe, limit)
        return df


# Singleton instance
_data_fetcher_instance = None

def get_data_fetcher() -> DataFetcher:
    """DataFetcher singleton instance döndürür"""
    global _data_fetcher_instance
    if _data_fetcher_instance is None:
        _data_fetcher_instance = DataFetcher()
    return _data_fetcher_instance