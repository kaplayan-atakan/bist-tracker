"""
BİST Trading Bot - TradingView WebSocket Provider
Ana gerçek zamanlı veri kaynağı - WebSocket üzerinden canlı fiyat akışı

ÖNEMLİ NOTLAR:
- Bu provider SADECE gerçek zamanlı streaming verisi içindir.
- Geçmiş (historical) OHLCV için TradingViewHTTPProvider veya YahooProvider kullanın.
- Anonim modda veriler 15 dakika gecikmelidir (delayed_streaming_900).
- Gerçek zamanlı veri için TradingView hesabı + authentication gerekir (gelecek sprint).

Başarıyla test edildi: experiments/tradingview_ws_test.py
WebSocket URL: wss://data.tradingview.com/socket.io/websocket
"""

import asyncio
import json
import logging
import random
import string
import time
from datetime import datetime, timedelta
from typing import AsyncIterator, Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

import pandas as pd

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketClientProtocol = None

from .base import BaseDataProvider, Timeframe, ProviderHealthStatus, ProviderConfig

logger = logging.getLogger(__name__)

# ============================================================================
# SABİTLER - Çalışan test scriptinden alındı
# ============================================================================

# WebSocket bağlantı ayarları
DEFAULT_WS_URL = "wss://data.tradingview.com/socket.io/websocket"
DEFAULT_WS_ORIGIN = "https://data.tradingview.com"

# Timing ayarları
HEARTBEAT_INTERVAL = 10  # saniye
RECONNECT_MAX_ATTEMPTS = 5
RECONNECT_BASE_DELAY = 1  # saniye
RECONNECT_MAX_DELAY = 60  # saniye
MESSAGE_TIMEOUT = 30  # saniye - bu süre mesaj gelmezse sağlık durumu güncellenir
HEALTH_CHECK_INTERVAL = 15  # saniye

# Quote alanları - TradingView protokolünden
QUOTE_FIELDS = [
    "ch",              # change
    "chp",             # change percent
    "current_session", # oturum durumu
    "description",     # açıklama
    "exchange",        # borsa
    "lp",              # last price
    "lp_time",         # last price time
    "volume",          # hacim
    "update_mode",     # veri modu (delayed_streaming_900 = 15dk gecikme)
    "open_price",      # açılış fiyatı
    "high_price",      # yüksek fiyat
    "low_price",       # düşük fiyat
    "prev_close_price", # önceki kapanış
]


# ============================================================================
# BAR AGGREGATOR - Tick'lerden mum oluşturur
# ============================================================================

@dataclass
class BarAggregator:
    """
    Tick verilerinden mum (bar) oluşturan sınıf.
    Her timeframe için ayrı aggregator kullanılır.
    """
    symbol: str
    timeframe: Timeframe
    current_bar: Optional[Dict[str, Any]] = None
    bar_start_time: Optional[datetime] = None
    
    def get_bar_duration_seconds(self) -> int:
        """Timeframe'e göre bar süresini saniye cinsinden döndürür"""
        durations = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "1D": 86400,
        }
        return durations.get(self.timeframe, 60)
    
    def get_bar_start_time(self, timestamp: datetime) -> datetime:
        """Verilen timestamp için bar başlangıç zamanını hesaplar"""
        duration = self.get_bar_duration_seconds()
        epoch = timestamp.timestamp()
        bar_epoch = (epoch // duration) * duration
        return datetime.fromtimestamp(bar_epoch)
    
    def process_tick(self, price: float, volume: float, timestamp: datetime) -> Optional[Dict]:
        """
        Yeni tick verisini işler, bar kapandıysa döndürür.
        
        Args:
            price: Anlık fiyat
            volume: İşlem hacmi
            timestamp: Zaman damgası
            
        Returns:
            Dict: Kapanan bar verisi veya None
        """
        bar_start = self.get_bar_start_time(timestamp)
        completed_bar = None
        
        # Yeni bar mı başlıyor?
        if self.bar_start_time is None or bar_start > self.bar_start_time:
            # Önceki bar'ı kaydet
            if self.current_bar is not None:
                completed_bar = self.current_bar.copy()
            
            # Yeni bar başlat
            self.bar_start_time = bar_start
            self.current_bar = {
                'timestamp': bar_start,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume,
                'symbol': self.symbol,
            }
        else:
            # Mevcut bar'ı güncelle
            if self.current_bar is not None:
                self.current_bar['high'] = max(self.current_bar['high'], price)
                self.current_bar['low'] = min(self.current_bar['low'], price)
                self.current_bar['close'] = price
                self.current_bar['volume'] += volume
        
        return completed_bar


# ============================================================================
# QUOTE DATA CLASS - Parse edilmiş quote verisi
# ============================================================================

@dataclass
class QuoteData:
    """Bir sembolün quote verisi."""
    symbol: str
    last_price: float
    change: float
    change_percent: float
    volume: int
    timestamp: datetime
    update_mode: str
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0


# ============================================================================
# WEBSOCKET PROTOKOL FONKSİYONLARI
# ============================================================================

def generate_session_id(prefix: str = "qs_") -> str:
    """TradingView oturum ID'si oluşturur."""
    chars = string.ascii_lowercase
    return prefix + ''.join(random.choice(chars) for _ in range(12))


def prepend_header(message: str) -> str:
    """TradingView WebSocket mesaj header'ı ekler."""
    return f"~m~{len(message)}~m~{message}"


def construct_message(func: str, params: list) -> str:
    """TradingView WebSocket mesajı oluşturur."""
    return json.dumps({"m": func, "p": params}, separators=(",", ":"))


def create_message(func: str, params: list) -> str:
    """Header ile birlikte tam mesaj oluşturur."""
    return prepend_header(construct_message(func, params))


def parse_raw_message(raw: str) -> List[Dict]:
    """
    TradingView WebSocket raw mesajını parse eder.
    
    Format: ~m~123~m~{...json...}~m~456~m~{...json...}
    """
    messages = []
    
    try:
        parts = raw.split("~m~")
        
        for part in parts:
            if not part:
                continue
            if part.isdigit():
                continue
            try:
                if part.startswith("{"):
                    msg = json.loads(part)
                    messages.append(msg)
            except json.JSONDecodeError:
                pass
                
    except Exception:
        pass
    
    return messages


def extract_quote_data(messages: List[Dict]) -> List[QuoteData]:
    """Parse edilmiş mesajlardan quote verilerini çıkarır."""
    quotes = []
    
    for msg in messages:
        if msg.get("m") != "qsd":
            continue
        
        try:
            params = msg.get("p", [])
            if len(params) < 2:
                continue
            
            data = params[1]
            if not isinstance(data, dict):
                continue
            
            symbol = data.get("n", "")
            values = data.get("v", {})
            
            if not symbol or not values:
                continue
            
            quote = QuoteData(
                symbol=symbol,
                last_price=float(values.get("lp", 0) or 0),
                change=float(values.get("ch", 0) or 0),
                change_percent=float(values.get("chp", 0) or 0),
                volume=int(values.get("volume", 0) or 0),
                timestamp=datetime.now(),
                update_mode=str(values.get("update_mode", "unknown")),
                open_price=float(values.get("open_price", 0) or 0),
                high_price=float(values.get("high_price", 0) or 0),
                low_price=float(values.get("low_price", 0) or 0),
            )
            quotes.append(quote)
            
        except Exception as e:
            logger.debug(f"Quote parse hatası: {e}")
    
    return quotes


# ============================================================================
# ANA PROVIDER SINIFI
# ============================================================================

class TradingViewWebSocketProvider(BaseDataProvider):
    """
    TradingView WebSocket üzerinden gerçek zamanlı veri sağlayan provider.
    
    ÖNEMLİ: Bu provider SADECE gerçek zamanlı streaming içindir.
    Geçmiş OHLCV verisi için TradingViewHTTPProvider veya YahooProvider kullanın.
    
    Veri Modu:
    - Anonim kullanımda veriler 15 dakika gecikmelidir (delayed_streaming_900).
    - Gerçek zamanlı veri için TradingView hesabı + authentication gerekir.
    
    Özellikler:
    - Gerçek zamanlı fiyat akışı
    - Otomatik yeniden bağlanma (exponential backoff)
    - Heartbeat/ping-pong bağlantı kontrolü
    - Tick'lerden mum birleştirme (BarAggregator)
    - Sağlık durumu takibi
    """
    
    name = "tradingview_ws"
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        TradingView WebSocket provider'ı başlat.
        
        Args:
            config: Provider yapılandırması
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets paketi yüklü değil. Yüklemek için: pip install websockets")
        
        super().__init__(config)
        
        # WebSocket bağlantısı
        self._ws: Optional[WebSocketClientProtocol] = None
        self._ws_url = self.config.ws_url or DEFAULT_WS_URL
        self._ws_origin = DEFAULT_WS_ORIGIN
        
        # Bağlantı durumu
        self._reconnect_attempts = 0
        self._last_message_time: Optional[float] = None
        self._session_id: Optional[str] = None
        
        # Abonelikler ve veri yönetimi
        self._subscribed_symbols: Dict[str, Timeframe] = {}
        self._bar_aggregators: Dict[str, BarAggregator] = {}
        self._pending_bars: asyncio.Queue = asyncio.Queue()
        self._latest_quotes: Dict[str, QuoteData] = {}
        
        # Arka plan görevleri
        self._receive_task: Optional[asyncio.Task] = None
        self._health_monitor_task: Optional[asyncio.Task] = None
        
        # Callback'ler
        self._on_bar_callback: Optional[Callable] = None
        self._on_quote_callback: Optional[Callable] = None
        self._on_disconnect_callback: Optional[Callable] = None
        
        logger.info(f"{self.name} provider başlatıldı (WS URL: {self._ws_url})")
    
    async def connect(self) -> bool:
        """
        TradingView WebSocket'e bağlan.
        
        Returns:
            bool: Bağlantı başarılı mı
        """
        try:
            logger.info(f"TradingView WebSocket'e bağlanılıyor: {self._ws_url}")
            
            self._ws = await websockets.connect(
                self._ws_url,
                origin=self._ws_origin,
                ping_interval=None,  # Manuel heartbeat kontrolü
                close_timeout=10,
            )
            
            self._session_id = generate_session_id("qs_")
            self._is_connected = True
            self._reconnect_attempts = 0
            self._last_message_time = time.time()
            self._health_status = ProviderHealthStatus.HEALTHY
            
            # İlk mesajları gönder (auth, session, fields)
            await self._send_initial_messages()
            
            # Arka plan görevlerini başlat
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
            
            logger.info(f"TradingView WebSocket bağlantısı başarılı (session: {self._session_id})")
            return True
            
        except Exception as e:
            logger.error(f"TradingView WebSocket bağlantı hatası: {e}")
            self._health_status = ProviderHealthStatus.DOWN
            self._last_error = str(e)
            self._is_connected = False
            return False
    
    async def _send_initial_messages(self):
        """Bağlantı sonrası ilk mesajları gönder."""
        if not self._ws or not self._session_id:
            return
        
        try:
            # 1. Auth token (unauthorized için)
            await self._ws.send(create_message("set_auth_token", ["unauthorized_user_token"]))
            
            # 2. Quote session oluştur
            await self._ws.send(create_message("quote_create_session", [self._session_id]))
            
            # 3. Quote alanlarını ayarla
            await self._ws.send(create_message("quote_set_fields", [self._session_id] + QUOTE_FIELDS))
            
            logger.debug("İlk WebSocket mesajları gönderildi")
            
        except Exception as e:
            logger.error(f"İlk mesaj gönderme hatası: {e}")
    
    async def disconnect(self):
        """WebSocket bağlantısını kapat."""
        logger.info("TradingView WebSocket bağlantısı kapatılıyor...")
        
        self._is_connected = False
        
        # Arka plan görevlerini iptal et
        for task in [self._receive_task, self._health_monitor_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # WebSocket'i kapat
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"WebSocket kapatma hatası: {e}")
        
        self._ws = None
        self._subscribed_symbols.clear()
        self._bar_aggregators.clear()
        self._latest_quotes.clear()
        
        logger.info("TradingView WebSocket bağlantısı kapatıldı")
    
    async def _reconnect(self):
        """Bağlantı koptuğunda yeniden bağlan (exponential backoff)."""
        if self._reconnect_attempts >= RECONNECT_MAX_ATTEMPTS:
            logger.error(f"Maksimum yeniden bağlanma denemesi aşıldı ({RECONNECT_MAX_ATTEMPTS})")
            self._health_status = ProviderHealthStatus.DOWN
            if self._on_disconnect_callback:
                await self._on_disconnect_callback()
            return
        
        self._reconnect_attempts += 1
        delay = min(
            RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempts) + random.uniform(0, 1),
            RECONNECT_MAX_DELAY
        )
        
        logger.warning(f"Yeniden bağlanma denemesi {self._reconnect_attempts}/{RECONNECT_MAX_ATTEMPTS} "
                      f"({delay:.1f}s sonra)")
        self._health_status = ProviderHealthStatus.DEGRADED
        
        await asyncio.sleep(delay)
        
        if await self.connect():
            # Önceki abonelikleri yenile
            symbols_to_resubscribe = list(self._subscribed_symbols.items())
            self._subscribed_symbols.clear()
            
            for symbol, timeframe in symbols_to_resubscribe:
                await self._subscribe_symbol(symbol, timeframe)
    
    async def _receive_loop(self):
        """WebSocket mesajlarını sürekli dinleyen döngü."""
        try:
            while self._is_connected and self._ws:
                try:
                    message = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=MESSAGE_TIMEOUT
                    )
                    self._last_message_time = time.time()
                    await self._process_message(message)
                    
                except asyncio.TimeoutError:
                    logger.debug("WebSocket mesaj timeout'u (bekleniyor)")
                    # Timeout sağlık durumunu etkiler ama bağlantıyı kapatmaz
                    if self._health_status == ProviderHealthStatus.HEALTHY:
                        self._health_status = ProviderHealthStatus.DEGRADED
                    
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"WebSocket bağlantısı kapandı: {e}")
                    self._is_connected = False
                    await self._reconnect()
                    break
                    
        except asyncio.CancelledError:
            logger.debug("Receive loop iptal edildi")
        except Exception as e:
            logger.error(f"Receive loop hatası: {e}")
            self._is_connected = False
            await self._reconnect()
    
    async def _health_monitor_loop(self):
        """Sağlık durumunu periyodik kontrol eden döngü."""
        try:
            while self._is_connected:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                
                if self._last_message_time:
                    elapsed = time.time() - self._last_message_time
                    
                    if elapsed > MESSAGE_TIMEOUT * 2:
                        logger.warning(f"Uzun süredir mesaj yok ({elapsed:.0f}s)")
                        self._health_status = ProviderHealthStatus.DOWN
                    elif elapsed > MESSAGE_TIMEOUT:
                        self._health_status = ProviderHealthStatus.DEGRADED
                    else:
                        self._health_status = ProviderHealthStatus.HEALTHY
                        
        except asyncio.CancelledError:
            logger.debug("Health monitor loop iptal edildi")
    
    async def _process_message(self, message: str):
        """Gelen WebSocket mesajını işle."""
        try:
            # Heartbeat kontrolü (~h~ mesajları)
            if "~h~" in message:
                # Heartbeat mesajını aynen geri gönder
                await self._ws.send(message)
                return
            
            # Parse et ve quote'ları çıkar
            messages = parse_raw_message(message)
            quotes = extract_quote_data(messages)
            
            for quote in quotes:
                # Quote'u kaydet
                self._latest_quotes[quote.symbol] = quote
                
                # Callback varsa çağır
                if self._on_quote_callback:
                    try:
                        await self._on_quote_callback(quote)
                    except Exception as e:
                        logger.debug(f"Quote callback hatası: {e}")
                
                # Bar aggregator'a gönder
                clean_symbol = quote.symbol.replace("BIST:", "")
                if clean_symbol in self._bar_aggregators:
                    aggregator = self._bar_aggregators[clean_symbol]
                    completed_bar = aggregator.process_tick(
                        quote.last_price, 
                        quote.volume, 
                        quote.timestamp
                    )
                    
                    if completed_bar:
                        await self._pending_bars.put(completed_bar)
                        
                        if self._on_bar_callback:
                            try:
                                await self._on_bar_callback(completed_bar)
                            except Exception as e:
                                logger.debug(f"Bar callback hatası: {e}")
                                
        except Exception as e:
            logger.debug(f"Mesaj işleme hatası: {e}")
    
    async def _subscribe_symbol(self, symbol: str, timeframe: Timeframe):
        """
        Sembole abone ol.
        
        Args:
            symbol: Hisse sembolü (GARAN, THYAO, vs.)
            timeframe: Zaman dilimi
        """
        if not self._ws or not self._is_connected:
            logger.warning("WebSocket bağlantısı yok, abone olunamıyor")
            return
        
        try:
            tv_symbol = self.convert_symbol_to_provider_format(symbol, "tradingview")
            
            # Sembol ekle
            await self._ws.send(create_message("quote_add_symbols", [self._session_id, tv_symbol]))
            
            # Fast symbols (gerçek zamanlı güncelleme)
            await self._ws.send(create_message("quote_fast_symbols", [self._session_id, tv_symbol]))
            
            self._subscribed_symbols[symbol] = timeframe
            self._bar_aggregators[symbol] = BarAggregator(symbol=symbol, timeframe=timeframe)
            
            logger.info(f"Sembole abone olundu: {symbol} ({timeframe}) -> {tv_symbol}")
            
        except Exception as e:
            logger.error(f"Sembol abonelik hatası ({symbol}): {e}")
    
    async def _unsubscribe_symbol(self, symbol: str):
        """Sembol aboneliğini iptal et."""
        if not self._ws or not self._is_connected:
            return
        
        try:
            tv_symbol = self.convert_symbol_to_provider_format(symbol, "tradingview")
            
            await self._ws.send(create_message("quote_remove_symbols", [self._session_id, tv_symbol]))
            
            self._subscribed_symbols.pop(symbol, None)
            self._bar_aggregators.pop(symbol, None)
            self._latest_quotes.pop(tv_symbol, None)
            
            logger.info(f"Sembol aboneliği iptal edildi: {symbol}")
            
        except Exception as e:
            logger.error(f"Sembol abonelik iptal hatası ({symbol}): {e}")
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        TradingView WebSocket provider geçmiş OHLCV verisi DESTEKLEMİYOR.
        
        Bu provider SADECE gerçek zamanlı streaming için kullanılır.
        Geçmiş (historical) OHLCV verisi için:
        - TradingViewHTTPProvider (intraday snapshots)
        - YahooProvider (daily + fundamentals)
        
        Args:
            symbol: Hisse sembolü
            timeframe: Zaman dilimi
            limit: Bar sayısı
            
        Raises:
            NotImplementedError: Her zaman - WebSocket geçmiş veri desteklemez
        """
        raise NotImplementedError(
            "TradingViewWebSocketProvider does not support historical OHLCV; "
            "use TradingViewHTTPProvider for intraday snapshots or YahooProvider for daily data. "
            "This provider is strictly for real-time streaming via get_realtime_stream()."
        )
    
    async def get_realtime_stream(
        self,
        symbols: List[str],
        timeframe: Timeframe,
    ) -> AsyncIterator[pd.DataFrame]:
        """
        Gerçek zamanlı bar stream'i sağlar.
        
        NOT: Anonim kullanımda veriler 15 dakika gecikmelidir (delayed_streaming_900).
        Gerçek zamanlı veri için TradingView authentication gerekir.
        
        Args:
            symbols: Sembol listesi (GARAN, THYAO, vs.)
            timeframe: Zaman dilimi (1m, 5m, 15m, 1h)
            
        Yields:
            DataFrame: Her kapanan bar için standart OHLCV verileri
                ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
        """
        # Bağlantı yoksa bağlan
        if not self._is_connected:
            if not await self.connect():
                raise ConnectionError("TradingView WebSocket bağlantısı kurulamadı")
        
        # Sembollere abone ol
        for symbol in symbols:
            if symbol not in self._subscribed_symbols:
                await self._subscribe_symbol(symbol, timeframe)
        
        # İlk quote'ları bekle
        await asyncio.sleep(2)
        
        # Bar'ları yield et
        try:
            while self._is_connected:
                try:
                    bar = await asyncio.wait_for(
                        self._pending_bars.get(),
                        timeout=1.0
                    )
                    
                    # Bar'ı DataFrame'e çevir
                    df = pd.DataFrame([bar])
                    df = self.normalize_dataframe(df)
                    yield df
                    
                except asyncio.TimeoutError:
                    # Timeout - bağlantı kontrolü yap
                    if not self._is_connected:
                        break
                    continue
                    
        except asyncio.CancelledError:
            logger.info("Realtime stream iptal edildi")
        finally:
            # Temizlik
            for symbol in symbols:
                await self._unsubscribe_symbol(symbol)
    
    async def get_health(self) -> ProviderHealthStatus:
        """
        Sağlık durumunu döndürür.
        
        HEALTHY: Bağlı ve son 30 saniye içinde mesaj alınmış
        DEGRADED: Bağlı ama mesaj yok veya bağlantı sorunlu
        DOWN: Bağlantı yok veya birden fazla reconnect başarısız
        """
        if not self._is_connected:
            return ProviderHealthStatus.DOWN
        return self._health_status
    
    def get_latest_quote(self, symbol: str) -> Optional[QuoteData]:
        """Son alınan quote verisini döndürür."""
        tv_symbol = self.convert_symbol_to_provider_format(symbol, "tradingview")
        return self._latest_quotes.get(tv_symbol)
    
    def get_subscribed_symbols(self) -> List[str]:
        """Abone olunan sembollerin listesini döndürür."""
        return list(self._subscribed_symbols.keys())
    
    def set_on_bar_callback(self, callback: Callable):
        """Yeni bar callback'i ayarla."""
        self._on_bar_callback = callback
    
    def set_on_quote_callback(self, callback: Callable):
        """Yeni quote callback'i ayarla."""
        self._on_quote_callback = callback
    
    def set_on_disconnect_callback(self, callback: Callable):
        """Bağlantı kopma callback'i ayarla."""
        self._on_disconnect_callback = callback


# ============================================================================
# SINGLETON FACTORY
# ============================================================================

_tradingview_ws_provider_instance: Optional[TradingViewWebSocketProvider] = None


def get_tradingview_ws_provider(config: Optional[ProviderConfig] = None) -> TradingViewWebSocketProvider:
    """TradingView WebSocket provider singleton instance döndürür."""
    global _tradingview_ws_provider_instance
    if _tradingview_ws_provider_instance is None:
        _tradingview_ws_provider_instance = TradingViewWebSocketProvider(config)
    return _tradingview_ws_provider_instance
