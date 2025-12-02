"""
BİST Trading Bot - Base Provider Module
Tüm veri sağlayıcıları için soyut temel sınıf ve ortak tipler
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import AsyncIterator, List, Literal, Optional, Dict, Any
from dataclasses import dataclass
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Desteklenen zaman dilimleri
Timeframe = Literal["1m", "5m", "15m", "1h", "1D"]


class ProviderHealthStatus(str, Enum):
    """Provider sağlık durumu"""
    HEALTHY = "healthy"      # Tam çalışır durumda
    DEGRADED = "degraded"    # Kısmi sorun, yavaşlık veya ara sıra hata
    DOWN = "down"            # Tamamen erişilemez
    UNKNOWN = "unknown"      # Durum bilinmiyor (henüz kontrol edilmedi)


@dataclass
class ProviderConfig:
    """Provider yapılandırma bilgileri"""
    name: str
    enabled: bool = True
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: Optional[str] = None
    ws_url: Optional[str] = None
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class OHLCVBar:
    """Tek bir OHLCV bar'ı temsil eder"""
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: Optional[str] = None


class BaseDataProvider(ABC):
    """
    Tüm veri sağlayıcıları için soyut temel sınıf.
    TradingView, Finnhub ve Yahoo provider'ları bu sınıftan türer.
    
    Tüm provider'lar OHLCV geçmişi ve (uygulanabilirse) gerçek zamanlı
    stream sağlamalıdır.
    """

    name: str = "base"  # Alt sınıflar tarafından override edilmeli

    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        Provider'ı yapılandırma ile başlat
        
        Args:
            config: Provider yapılandırması (opsiyonel)
        """
        self.config = config or ProviderConfig(name=self.name)
        self._health_status = ProviderHealthStatus.UNKNOWN
        self._last_error: Optional[str] = None
        self._is_connected = False
        logger.info(f"{self.name} provider başlatıldı")

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Belirtilen sembol ve zaman dilimi için geçmiş OHLCV verisi çeker.
        
        Args:
            symbol: Hisse sembolü (ör: THYAO)
            timeframe: Zaman dilimi ('1m', '5m', '15m', '1h', '1D')
            limit: Çekilecek bar sayısı
            
        Returns:
            DataFrame: Standart sütunlarla OHLCV verileri
                ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                timestamp'e göre artan sıralı
                
        Raises:
            NotImplementedError: Alt sınıf implement etmeli
        """
        raise NotImplementedError("Alt sınıf get_ohlcv metodunu implement etmeli")

    async def get_realtime_stream(
        self,
        symbols: List[str],
        timeframe: Timeframe,
    ) -> AsyncIterator[pd.DataFrame]:
        """
        Opsiyonel: Belirtilen semboller için gerçek zamanlı bar stream'i.
        Yeni bar'lar oluştukça yield eder.
        
        Args:
            symbols: Sembol listesi
            timeframe: Zaman dilimi
            
        Yields:
            DataFrame: Her yeni bar için standart OHLCV DataFrame
            
        Raises:
            NotImplementedError: Streaming desteklemeyen provider'lar için
        """
        raise NotImplementedError(f"{self.name} provider gerçek zamanlı stream desteklemiyor")
        # Async generator olması için dummy yield
        yield pd.DataFrame()

    async def get_health(self) -> ProviderHealthStatus:
        """
        Hafif sağlık kontrolü yapar.
        
        Returns:
            ProviderHealthStatus: Provider'ın mevcut sağlık durumu
        """
        return self._health_status

    async def check_health(self) -> ProviderHealthStatus:
        """
        Aktif sağlık kontrolü yapar ve durumu günceller.
        Alt sınıflar daha detaylı kontroller için override edebilir.
        
        Returns:
            ProviderHealthStatus: Güncellenmiş sağlık durumu
        """
        try:
            # Basit kontrol: küçük bir veri çekmeyi dene
            df = await self.get_ohlcv("THYAO", "1D", limit=1)
            if df is not None and not df.empty:
                self._health_status = ProviderHealthStatus.HEALTHY
            else:
                self._health_status = ProviderHealthStatus.DEGRADED
        except Exception as e:
            self._last_error = str(e)
            self._health_status = ProviderHealthStatus.DOWN
            logger.warning(f"{self.name} sağlık kontrolü başarısız: {e}")
        
        return self._health_status

    def set_health_status(self, status: ProviderHealthStatus, error: Optional[str] = None):
        """
        Sağlık durumunu manuel olarak ayarlar.
        
        Args:
            status: Yeni sağlık durumu
            error: Hata mesajı (opsiyonel)
        """
        self._health_status = status
        if error:
            self._last_error = error
        logger.debug(f"{self.name} sağlık durumu güncellendi: {status.value}")

    def get_last_error(self) -> Optional[str]:
        """Son hata mesajını döndürür"""
        return self._last_error

    def is_healthy(self) -> bool:
        """Provider sağlıklı mı kontrol eder"""
        return self._health_status == ProviderHealthStatus.HEALTHY

    def is_available(self) -> bool:
        """Provider kullanılabilir mi kontrol eder (healthy veya degraded)"""
        return self._health_status in (ProviderHealthStatus.HEALTHY, ProviderHealthStatus.DEGRADED)

    @staticmethod
    def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        DataFrame'i standart formata dönüştürür.
        
        Args:
            df: Ham DataFrame
            
        Returns:
            DataFrame: Standart sütunlarla normalize edilmiş DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Sütun isimlerini küçük harfe çevir
        df.columns = [col.lower() for col in df.columns]
        
        # Index timestamp ise sütuna çevir
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            # Index adına göre sütun adını ayarla
            if 'index' in df.columns:
                df = df.rename(columns={'index': 'timestamp'})
            elif 'date' in df.columns:
                df = df.rename(columns={'date': 'timestamp'})
        
        # Gerekli sütunları kontrol et
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in df.columns:
                logger.warning(f"Eksik sütun: {col}")
        
        # Timestamp sütununu düzenle
        if 'timestamp' not in df.columns:
            if 'datetime' in df.columns:
                df = df.rename(columns={'datetime': 'timestamp'})
            elif 'time' in df.columns:
                df = df.rename(columns={'time': 'timestamp'})
        
        # Timestamp'e göre sırala (artan)
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp', ascending=True).reset_index(drop=True)
        
        return df

    @staticmethod
    def convert_symbol_to_provider_format(symbol: str, provider_name: str) -> str:
        """
        Sembolü provider'a özgü formata çevirir.
        
        Args:
            symbol: BİST sembol kodu (ör: THYAO)
            provider_name: Provider adı
            
        Returns:
            str: Provider formatında sembol
        """
        symbol = symbol.upper().strip()
        
        if provider_name == "yahoo":
            # yfinance için .IS uzantısı
            if not symbol.endswith('.IS'):
                return f"{symbol}.IS"
            return symbol
        elif provider_name == "finnhub":
            # Finnhub için BIST: prefix
            if not symbol.startswith('BIST:'):
                return f"BIST:{symbol}"
            return symbol
        elif provider_name == "tradingview":
            # TradingView için BIST: prefix
            if not symbol.startswith('BIST:'):
                return f"BIST:{symbol}"
            return symbol
        else:
            return symbol

    @staticmethod
    def convert_timeframe_to_provider_format(timeframe: Timeframe, provider_name: str) -> str:
        """
        Zaman dilimini provider'a özgü formata çevirir.
        
        Args:
            timeframe: Standart zaman dilimi
            provider_name: Provider adı
            
        Returns:
            str: Provider formatında zaman dilimi
        """
        # Provider'a özgü mapping'ler
        mappings = {
            "yahoo": {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "1h": "1h",
                "1D": "1d",
            },
            "finnhub": {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "1h": "60",
                "1D": "D",
            },
            "tradingview": {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "1h": "60",
                "1D": "1D",
            },
        }
        
        provider_map = mappings.get(provider_name, {})
        return provider_map.get(timeframe, timeframe)

    async def connect(self) -> bool:
        """
        Provider'a bağlan (WebSocket provider'lar için).
        REST provider'lar için varsayılan olarak True döner.
        
        Returns:
            bool: Bağlantı başarılı mı
        """
        self._is_connected = True
        return True

    async def disconnect(self):
        """
        Provider bağlantısını kapat (WebSocket provider'lar için).
        """
        self._is_connected = False
        logger.info(f"{self.name} bağlantısı kapatıldı")

    def is_connected(self) -> bool:
        """Bağlantı durumunu döndürür"""
        return self._is_connected

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} health={self._health_status.value}>"
