"""
BİST Trading Bot - Provider Manager
Provider öncelik ve failover yönetimi

Sprint 2 Güncellemesi:
- TradingView HTTP: İntraday anlık veriler için primary provider
- TradingView WebSocket: Gerçek zamanlı streaming için (gelecek sprint)
- Yahoo: Günlük veriler + fundamentals için
- Finnhub: Backup (API key gerekli, BİST sınırlı destek)

VERİ GECİKMESİ UYARISI:
Anonim kullanımda TradingView verileri 15 dakika gecikmelidir (delayed_streaming_900).
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, AsyncIterator

import pandas as pd

from .base import BaseDataProvider, Timeframe, ProviderHealthStatus, ProviderConfig
from .tradingview_ws import TradingViewWebSocketProvider, get_tradingview_ws_provider
from .tradingview_http import TradingViewHTTPProvider, get_tradingview_http_provider
from .finnhub import FinnhubProvider, get_finnhub_provider
from .yahoo import YahooProvider, get_yahoo_provider

logger = logging.getLogger(__name__)

# ============================================================================
# PROVIDER ÖNCELİK SIRALAMALARI
# ============================================================================

# İntraday (1m, 5m, 15m, 1h) için öncelik sırası
# TradingView HTTP: Anlık snapshot, düşük latency (~200ms)
# Yahoo: Fallback - yfinance ile intraday çekilebilir
DATA_PRIORITY_INTRADAY = ["tradingview_http", "yahoo"]

# Günlük (1D, 1W) için öncelik sırası
# Yahoo: Ana kaynak - yfinance ile güvenilir günlük veri
DATA_PRIORITY_DAILY = ["yahoo"]

# Fundamentals için öncelik sırası
# TradingView HTTP: Sector, market cap, PE, PB (screener'dan)
# Yahoo: Kapsamlı fundamental data
DATA_PRIORITY_FUNDAMENTALS = ["tradingview_http", "yahoo"]

# Gerçek zamanlı streaming için provider
# TradingView WebSocket: Quote streaming
STREAMING_PROVIDER_INTRADAY = "tradingview_ws"

# Intraday timeframe'ler
INTRADAY_TIMEFRAMES = ["1m", "5m", "15m", "1h"]


class ProviderManager:
    """
    Tüm veri sağlayıcılarını yöneten ve failover mantığını uygulayan sınıf.
    
    Sprint 2 Özellikleri:
    - TradingView HTTP: İntraday snapshot'lar için primary
    - TradingView WebSocket: Gerçek zamanlı streaming
    - Yahoo: Günlük veriler + fundamentals
    - Otomatik failover (sağlıksız provider'ları atla)
    
    VERİ GECİKMESİ:
    Anonim modda TradingView verileri 15 dakika gecikmelidir.
    """
    
    def __init__(
        self,
        tradingview_ws: Optional[TradingViewWebSocketProvider] = None,
        tradingview_http: Optional[TradingViewHTTPProvider] = None,
        finnhub: Optional[FinnhubProvider] = None,
        yahoo: Optional[YahooProvider] = None,
    ):
        """
        Provider Manager'ı başlat.
        
        Args:
            tradingview_ws: TradingView WebSocket provider (streaming)
            tradingview_http: TradingView HTTP provider (snapshots)
            finnhub: Finnhub REST provider (backup)
            yahoo: Yahoo (yfinance) provider (daily + fundamentals)
        """
        # Provider'ları kaydet
        self.providers: Dict[str, BaseDataProvider] = {}
        
        if tradingview_ws:
            self.providers["tradingview_ws"] = tradingview_ws
        if tradingview_http:
            self.providers["tradingview_http"] = tradingview_http
        if finnhub:
            self.providers["finnhub"] = finnhub
        if yahoo:
            self.providers["yahoo"] = yahoo
        
        # Sağlık durumları
        self.health: Dict[str, ProviderHealthStatus] = {
            name: ProviderHealthStatus.UNKNOWN 
            for name in self.providers
        }
        
        # İstatistikler
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failover_count': 0,
            'provider_failures': {name: 0 for name in self.providers},
        }
        
        logger.info(f"ProviderManager başlatıldı. Aktif provider'lar: {list(self.providers.keys())}")
        logger.info(f"İntraday öncelik: {DATA_PRIORITY_INTRADAY}")
        logger.info(f"Günlük öncelik: {DATA_PRIORITY_DAILY}")
    
    def get_provider(self, name: str) -> Optional[BaseDataProvider]:
        """İsme göre provider döndür"""
        return self.providers.get(name)
    
    def get_tradingview_ws(self) -> Optional[TradingViewWebSocketProvider]:
        """TradingView WebSocket provider'ı döndür"""
        return self.providers.get("tradingview_ws")
    
    def get_tradingview_http(self) -> Optional[TradingViewHTTPProvider]:
        """TradingView HTTP provider'ı döndür"""
        return self.providers.get("tradingview_http")
    
    async def initialize_providers(self):
        """Tüm provider'ları başlat ve bağlantı kur"""
        for name, provider in self.providers.items():
            try:
                # WebSocket provider için connect çağır (diğerleri için opsiyonel)
                if hasattr(provider, 'connect'):
                    await provider.connect()
                self.health[name] = await provider.get_health()
                logger.info(f"{name} provider başlatıldı: {self.health[name].value}")
            except Exception as e:
                logger.error(f"{name} provider başlatma hatası: {e}")
                self.health[name] = ProviderHealthStatus.DOWN
    
    async def shutdown_providers(self):
        """Tüm provider bağlantılarını kapat"""
        for name, provider in self.providers.items():
            try:
                if hasattr(provider, 'disconnect'):
                    await provider.disconnect()
                logger.info(f"{name} provider kapatıldı")
            except Exception as e:
                logger.warning(f"{name} provider kapatma hatası: {e}")
    
    async def update_health(self, name: str) -> ProviderHealthStatus:
        """
        Belirli bir provider'ın sağlık durumunu güncelle.
        
        Args:
            name: Provider adı
            
        Returns:
            ProviderHealthStatus: Güncel sağlık durumu
        """
        provider = self.providers.get(name)
        if not provider:
            return ProviderHealthStatus.UNKNOWN
        
        try:
            health = await provider.get_health()
            self.health[name] = health
            return health
        except Exception as e:
            logger.warning(f"{name} sağlık kontrolü hatası: {e}")
            self.health[name] = ProviderHealthStatus.DOWN
            return ProviderHealthStatus.DOWN
    
    async def update_all_health(self):
        """Tüm provider'ların sağlık durumunu güncelle"""
        for name in self.providers:
            await self.update_health(name)
    
    def _get_available_providers(self, priority_list: List[str]) -> List[str]:
        """
        Öncelik listesinden kullanılabilir provider'ları filtrele.
        
        Args:
            priority_list: Provider öncelik listesi
            
        Returns:
            List[str]: Kullanılabilir provider isimleri
        """
        available = []
        for name in priority_list:
            if name in self.providers:
                health = self.health.get(name, ProviderHealthStatus.UNKNOWN)
                if health in (ProviderHealthStatus.HEALTHY, ProviderHealthStatus.DEGRADED, ProviderHealthStatus.UNKNOWN):
                    available.append(name)
                else:
                    logger.debug(f"{name} provider sağlıksız: {health.value}")
        return available
    
    def _is_intraday(self, timeframe: Timeframe) -> bool:
        """Timeframe intraday mı kontrol et"""
        return timeframe in INTRADAY_TIMEFRAMES
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        OHLCV verisi çeker, failover mantığıyla.
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        self._stats['total_requests'] += 1
        
        # Timeframe'e göre öncelik listesi seç
        if self._is_intraday(timeframe):
            priority_list = DATA_PRIORITY_INTRADAY
        else:
            priority_list = DATA_PRIORITY_DAILY
        
        # Kullanılabilir provider'ları al
        available_providers = self._get_available_providers(priority_list)
        
        if not available_providers:
            logger.error(f"Kullanılabilir provider yok! Timeframe: {timeframe}")
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Provider'ları sırayla dene
        last_error = None
        for provider_name in available_providers:
            provider = self.providers[provider_name]
            
            try:
                logger.debug(f"OHLCV çekiliyor: {symbol} ({timeframe}) - Provider: {provider_name}")
                df = await provider.get_ohlcv(symbol, timeframe, limit)
                
                if df is not None and not df.empty:
                    self._stats['successful_requests'] += 1
                    return df
                else:
                    logger.warning(f"{provider_name} boş veri döndürdü: {symbol}")
            
            except NotImplementedError as e:
                # Provider bu işlemi desteklemiyor (örn: TradingView WS geçmiş veri)
                # Sağlık durumunu DEĞİŞTİRME, sadece sonrakine geç
                logger.debug(f"{provider_name} bu işlemi desteklemiyor: {e}")
                self._stats['failover_count'] += 1
                continue
                    
            except Exception as e:
                last_error = e
                self._stats['provider_failures'][provider_name] += 1
                self._stats['failover_count'] += 1
                logger.warning(f"{provider_name} hatası ({symbol}): {e}")
                
                # Provider sağlığını güncelle
                self.health[provider_name] = ProviderHealthStatus.DEGRADED
                continue
        
        # Tüm provider'lar başarısız
        logger.error(f"Tüm provider'lar başarısız: {symbol} ({timeframe}). Son hata: {last_error}")
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    async def get_ohlcv_intraday(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Intraday OHLCV verisi çeker.
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi (1m, 5m, 15m, 1h)
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        if timeframe not in INTRADAY_TIMEFRAMES:
            logger.warning(f"Intraday için geçersiz timeframe: {timeframe}")
        
        return await self.get_ohlcv(symbol, timeframe, limit)
    
    async def get_ohlcv_daily(
        self,
        symbol: str,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Günlük OHLCV verisi çeker.
        
        Args:
            symbol: Hisse sembolü
            limit: Bar sayısı
            
        Returns:
            DataFrame: OHLCV verileri
        """
        return await self.get_ohlcv(symbol, "1D", limit)
    
    async def get_realtime_stream(
        self,
        symbols: List[str],
        timeframe: Timeframe,
    ) -> AsyncIterator[pd.DataFrame]:
        """
        Gerçek zamanlı bar stream'i sağlar.
        
        NOT: Anonim kullanımda veriler 15 dakika gecikmelidir.
        
        Args:
            symbols: Sembol listesi
            timeframe: Zaman dilimi
            
        Yields:
            DataFrame: Her bar için OHLCV verileri
        """
        ws_provider = self.get_tradingview_ws()
        
        if not ws_provider:
            raise RuntimeError("TradingView WebSocket provider mevcut değil")
        
        async for df in ws_provider.get_realtime_stream(symbols, timeframe):
            yield df
    
    async def get_fundamentals(self, symbol: str) -> Optional[Dict]:
        """
        Temel analiz verisi çeker.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Temel analiz verileri
        """
        # Önce TradingView HTTP dene (daha hızlı)
        http_provider = self.get_tradingview_http()
        if http_provider:
            try:
                result = await http_provider.get_fundamentals(symbol)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"TradingView HTTP fundamentals hatası: {e}")
        
        # Fallback: Yahoo
        yahoo = self.providers.get("yahoo")
        if yahoo and isinstance(yahoo, YahooProvider):
            try:
                return await yahoo.get_fundamentals(symbol)
            except Exception as e:
                logger.error(f"Temel analiz çekme hatası ({symbol}): {e}")
        
        return None
    
    async def get_daily_stats(self, symbol: str) -> Optional[Dict]:
        """
        Günlük istatistikleri çeker.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Dict: Günlük istatistikler
        """
        # Önce TradingView HTTP dene (anlık veri)
        http_provider = self.get_tradingview_http()
        if http_provider:
            try:
                result = await http_provider.get_daily_stats(symbol)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"TradingView HTTP daily stats hatası: {e}")
        
        # Fallback: Yahoo'dan günlük OHLCV hesapla
        df = await self.get_ohlcv_daily(symbol, limit=5)
        
        if df is None or len(df) < 2:
            return None
        
        try:
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            
            daily_change = ((today['close'] - yesterday['close']) / yesterday['close']) * 100
            daily_volume_tl = today['volume'] * today['close']
            
            return {
                'symbol': symbol,
                'current_price': today['close'],
                'open': today['open'],
                'high': today['high'],
                'low': today['low'],
                'close': today['close'],
                'volume': today['volume'],
                'daily_volume_tl': daily_volume_tl,
                'daily_change_percent': daily_change,
                'timestamp': today.get('timestamp', pd.Timestamp.now()),
            }
        except Exception as e:
            logger.error(f"Daily stats hesaplama hatası ({symbol}): {e}")
            return None
    
    async def get_snapshots(self, symbols: List[str]) -> List[Dict]:
        """
        Birden fazla sembol için anlık snapshot verileri çeker.
        
        Args:
            symbols: Sembol listesi
            
        Returns:
            List[Dict]: Her sembol için snapshot verisi
        """
        http_provider = self.get_tradingview_http()
        if http_provider:
            try:
                from .tradingview_http import OHLCVSnapshot
                snapshots = await http_provider.get_snapshots(symbols)
                return [
                    {
                        'symbol': s.symbol,
                        'open': s.open,
                        'high': s.high,
                        'low': s.low,
                        'close': s.close,
                        'volume': s.volume,
                        'change': s.change,
                        'change_percent': s.change_percent,
                        'timestamp': s.timestamp.isoformat(),
                        'update_mode': s.update_mode,
                    }
                    for s in snapshots
                ]
            except Exception as e:
                logger.error(f"Snapshot çekme hatası: {e}")
        
        return []
    
    async def get_bid_ask_spread(self, symbol: str) -> Optional[float]:
        """
        Alış-satış makası tahmini çeker.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: Spread yüzdesi
        """
        yahoo = self.providers.get("yahoo")
        if yahoo and isinstance(yahoo, YahooProvider):
            try:
                return await yahoo.get_bid_ask_spread(symbol)
            except Exception as e:
                logger.debug(f"Spread çekme hatası ({symbol}): {e}")
        
        return None
    
    def get_health_summary(self) -> Dict[str, str]:
        """Tüm provider'ların sağlık özeti"""
        return {name: status.value for name, status in self.health.items()}
    
    def get_stats(self) -> Dict:
        """İstatistikleri döndür"""
        return {
            **self._stats,
            'health': self.get_health_summary(),
            'active_providers': len([h for h in self.health.values() 
                                    if h in (ProviderHealthStatus.HEALTHY, ProviderHealthStatus.DEGRADED)]),
            'priority_intraday': DATA_PRIORITY_INTRADAY,
            'priority_daily': DATA_PRIORITY_DAILY,
            'streaming_provider': STREAMING_PROVIDER_INTRADAY,
        }


# ============================================================================
# SINGLETON FACTORY
# ============================================================================

_provider_manager_instance: Optional[ProviderManager] = None


def get_provider_manager(
    tradingview_ws_config: Optional[ProviderConfig] = None,
    tradingview_http_config: Optional[ProviderConfig] = None,
    finnhub_config: Optional[ProviderConfig] = None,
    yahoo_config: Optional[ProviderConfig] = None,
    force_new: bool = False,
) -> ProviderManager:
    """
    ProviderManager singleton instance döndürür.
    
    Args:
        tradingview_ws_config: TradingView WebSocket yapılandırması
        tradingview_http_config: TradingView HTTP yapılandırması
        finnhub_config: Finnhub yapılandırması
        yahoo_config: Yahoo yapılandırması
        force_new: Yeni instance oluşturmayı zorla
        
    Returns:
        ProviderManager: Manager instance
    """
    global _provider_manager_instance
    
    if _provider_manager_instance is None or force_new:
        # Provider'ları oluştur
        tradingview_ws = None
        tradingview_http = None
        finnhub = None
        yahoo = None
        
        # Yahoo - her zaman yükle (temel provider)
        try:
            yahoo = get_yahoo_provider(yahoo_config)
            logger.info("Yahoo provider yüklendi")
        except ImportError as e:
            logger.warning(f"Yahoo provider yüklenemedi: {e}")
        
        # TradingView HTTP - intraday için primary
        try:
            tradingview_http = get_tradingview_http_provider(tradingview_http_config)
            logger.info("TradingView HTTP provider yüklendi")
        except ImportError as e:
            logger.warning(f"TradingView HTTP provider yüklenemedi: {e}")
        
        # TradingView WebSocket - streaming için
        try:
            tradingview_ws = get_tradingview_ws_provider(tradingview_ws_config)
            logger.info("TradingView WebSocket provider yüklendi")
        except ImportError as e:
            logger.warning(f"TradingView WebSocket provider yüklenemedi: {e}")
        
        # Finnhub - backup (API key gerekli)
        try:
            finnhub = get_finnhub_provider(finnhub_config)
            logger.info("Finnhub provider yüklendi")
        except ImportError as e:
            logger.debug(f"Finnhub provider yüklenemedi (opsiyonel): {e}")
        
        _provider_manager_instance = ProviderManager(
            tradingview_ws=tradingview_ws,
            tradingview_http=tradingview_http,
            finnhub=finnhub,
            yahoo=yahoo,
        )
    
    return _provider_manager_instance
