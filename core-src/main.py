"""
BİST Trading Bot - Main Module
Ana çalıştırma ve zamanlama modülü

MVP Sprint: Provider katmanı entegrasyonu tamamlandı.
- ProviderManager ile veri çekme
- Async-native tarama döngüsü
- Graceful shutdown (SIGINT/SIGTERM)
- 15 dakika veri gecikmesi uyarısı
- Turkey timezone desteği (VPS lokasyonundan bağımsız)

VERİ GECİKMESİ:
TradingView anonim kullanımda veriler 15 dakika gecikmelidir (delayed_streaming_900).
Bu, swing trading için kabul edilebilir; day trading için uygun DEĞİLDİR.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, time as datetime_time, timedelta
from typing import List, Dict, Optional, Any
import traceback

import config
from providers import get_provider_manager, ProviderManager
from indicators import (
    calculate_trend_indicators,
    calculate_momentum_indicators,
    calculate_volume_indicators,
    calculate_price_action_features
)
from scoring import calculate_total_score
from filters import apply_all_filters, reset_filter_stats, get_filter_stats
from cooldown_manager import get_cooldown_manager
from telegram_notifier import get_telegram_notifier
from utils.error_logger import scan_error_logger
from utils.timezone import (
    now_turkey,
    today_turkey,
    is_market_hours,
    is_weekday,
    get_next_market_open as tz_get_next_market_open,
    format_timestamp,
)


# ============================================================
# DAILY DATA CACHE - Günlük veri önbellekleme sistemi
# ============================================================

class DailyDataCache:
    """
    Günlük trend verileri için in-memory cache.
    
    Neden gerekli:
    - Günlük trend analizi sadece günde 2x yenilenir (09:55 + 18:05)
    - İntraday taramalar bu cache'den trend verilerini kullanır
    - Her 15dk'da 81 sembol için günlük veri çekmek gereksiz yük
    
    TTL: 12 saat (yarım gün, sabah ve akşam yenilenir)
    """
    
    def __init__(self, ttl_hours: int = 12):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(hours=ttl_hours)
        self._last_refresh: Optional[datetime] = None
    
    def get(self, symbol: str) -> Optional[Dict]:
        """
        Cache'ten sembol verisini al.
        TTL kontrolü yapar.
        """
        if symbol in self._cache:
            entry = self._cache[symbol]
            if now_turkey() - entry.get("updated_at", datetime.min.replace(tzinfo=now_turkey().tzinfo)) < self._ttl:
                return entry
        return None
    
    def set(self, symbol: str, ohlcv_df, daily_stats: Dict, trend_data: Dict):
        """
        Sembol verisini cache'e kaydet.
        
        Args:
            symbol: Sembol kodu
            ohlcv_df: Pandas DataFrame (OHLCV)
            daily_stats: Günlük istatistikler
            trend_data: Hesaplanmış trend indikatörleri
        """
        self._cache[symbol] = {
            "df": ohlcv_df,
            "stats": daily_stats,
            "trend": trend_data,
            "updated_at": now_turkey()
        }
    
    def clear(self):
        """Tüm cache'i temizle"""
        self._cache.clear()
        self._last_refresh = None
    
    def get_all_symbols(self) -> List[str]:
        """Cache'teki tüm sembolleri döndür"""
        return list(self._cache.keys())
    
    def get_stats(self) -> Dict:
        """Cache istatistiklerini döndür"""
        return {
            "cached_symbols": len(self._cache),
            "last_refresh": self._last_refresh.strftime("%H:%M:%S") if self._last_refresh else "Never",
            "ttl_hours": self._ttl.total_seconds() / 3600
        }
    
    def mark_refreshed(self):
        """Son yenileme zamanını işaretle"""
        self._last_refresh = now_turkey()


# Global cache instance
daily_cache = DailyDataCache(ttl_hours=12)


# Logging yapılandırması
def setup_logging():
    """
    Logging sistemini yapılandırır.
    
    - Kendi modüllerimiz: LOG_LEVEL (varsayılan INFO)
    - Üçüncü parti kütüphaneler: LOG_LEVEL_THIRD_PARTY (varsayılan WARNING)
    """
    # Ana log seviyesi
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    log_format = getattr(config, 'LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_date_format = getattr(config, 'LOG_DATE_FORMAT', '%Y-%m-%d %H:%M:%S')
    
    # Root logger yapılandırması
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=log_date_format,
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Üçüncü parti kütüphaneleri sustur (çok gürültülü)
    third_party_level = getattr(
        logging, 
        getattr(config, 'LOG_LEVEL_THIRD_PARTY', 'WARNING').upper(), 
        logging.WARNING
    )
    
    noisy_loggers = [
        'yfinance',
        'peewee', 
        'urllib3',
        'urllib3.connectionpool',
        'aiohttp',
        'websockets',
        'websockets.client',
        'asyncio',
        'charset_normalizer',
        'requests',
        'httpx',
    ]
    
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(third_party_level)
    
    # Kendi modüllerimiz ana log seviyesinde
    our_modules = [
        '__main__',
        'providers',
        'providers.yahoo',
        'providers.tradingview_http',
        'providers.tradingview_ws',
        'providers.finnhub',
        'providers.manager',
        'telegram_notifier',
        'scoring',
        'indicators',
        'filters',
        'data_fetcher',
        'cooldown_manager',
    ]
    
    for module_name in our_modules:
        logging.getLogger(module_name).setLevel(log_level)
    
    # Başlangıç logu
    logging.info(f"📋 Log seviyesi: {config.LOG_LEVEL} (3rd party: {getattr(config, 'LOG_LEVEL_THIRD_PARTY', 'WARNING')})")


logger = logging.getLogger(__name__)


class BISTTradingBot:
    """
    BİST Trading Bot ana sınıfı
    
    MVP Sprint: Provider katmanı ile tam entegrasyon.
    - ProviderManager üzerinden veri çekme
    - Async-native operasyonlar
    - Graceful shutdown desteği
    """
    
    def __init__(self):
        # Provider manager (async veri kaynağı)
        self.provider_manager: Optional[ProviderManager] = None
        
        # Cooldown ve Telegram (senkron helper'lar)
        self.cooldown_manager = get_cooldown_manager()
        self.telegram_notifier = get_telegram_notifier()
        
        # Shutdown flag
        self._shutdown_requested = False
        
        # İstatistikler
        self.stats = {
            'total_scans': 0,
            'total_symbols_analyzed': 0,
            'total_signals_generated': 0,
            'total_signals_sent': 0,
            'errors': 0,
            'provider_failovers': 0
        }
        
        # Veri erişimi takibi
        self._last_successful_data_time: Optional[datetime] = None
        self._data_outage_alert_sent: bool = False
        self._last_market_open_report: Optional[datetime] = None
        self._last_market_close_report: Optional[datetime] = None
        
        # Günlük tarama takibi (open_close modu için)
        self._last_open_scan: Optional[datetime] = None
        self._last_close_scan: Optional[datetime] = None
        self._startup_scan_done: bool = False
        
        # Hybrid mod takibi
        self._last_daily_refresh: Optional[datetime] = None
        self._last_intraday_scan: Optional[datetime] = None
        self._intraday_scan_count: int = 0  # Günlük intraday tarama sayısı
        self._first_intraday_scan_time: Optional[datetime] = None  # İlk intraday tarama başlangıç zamanı
        
        logger.info("🤖 BİST Trading Bot başlatıldı")
    
    async def initialize(self):
        """
        Bot'u async olarak başlat.
        Provider'ları initialize et ve bağlantıları kur.
        """
        logger.info("🔌 Provider'lar başlatılıyor...")
        
        # Provider manager'ı al
        self.provider_manager = get_provider_manager()
        
        # Provider'ları initialize et (bağlantı kur)
        await self.provider_manager.initialize_providers()
        
        # Aktif provider'ları logla
        health_summary = self.provider_manager.get_health_summary()
        logger.info(f"📡 Provider sağlık durumu: {health_summary}")
        
        # Veri gecikmesi uyarısı
        if config.DATA_DELAY_ENABLED:
            logger.warning(f"⏱️ VERİ GECİKMESİ: {config.DATA_DELAY_MINUTES} dakika (TradingView free tier)")
            logger.warning("   Bu gecikme swing trading için kabul edilebilir; day trading için uygun DEĞİLDİR.")
    
    async def shutdown(self):
        """
        Bot'u graceful olarak kapat.
        Provider bağlantılarını temizle.
        """
        logger.info("🛑 Bot kapatılıyor...")
        
        if self.provider_manager:
            await self.provider_manager.shutdown_providers()
        
        logger.info("✅ Bot kapatıldı")
    
    def request_shutdown(self):
        """Shutdown isteği gönder (signal handler'dan çağrılır)"""
        self._shutdown_requested = True
        logger.info("⚠️ Shutdown isteği alındı...")
    
    def is_market_open(self) -> bool:
        """
        Piyasa açık mı kontrol eder (Türkiye saati)
        
        Returns:
            bool: Piyasa açık mı?
        """
        return is_market_hours(config.MARKET_OPEN_HOUR, config.MARKET_CLOSE_HOUR)
    
    def is_market_opening(self) -> bool:
        """
        Piyasa açılış saati mi kontrol eder (10:00-10:05 arası, Türkiye saati)
        
        Returns:
            bool: Açılış saati mi?
        """
        now = now_turkey()
        if now.weekday() >= 5:
            return False
        
        current_time = now.time()
        market_open_start = datetime_time(config.MARKET_OPEN_HOUR, 0)
        market_open_end = datetime_time(config.MARKET_OPEN_HOUR, 5)  # İlk 5 dakika
        
        return market_open_start <= current_time <= market_open_end
    
    def is_market_closing(self) -> bool:
        """
        Piyasa kapanış saati mi kontrol eder (17:55-18:05 arası, Türkiye saati)
        
        Returns:
            bool: Kapanış saati mi?
        """
        now = now_turkey()
        if now.weekday() >= 5:
            return False
        
        current_time = now.time()
        # Kapanıştan 5 dakika önce - 5 dakika sonra
        close_start = datetime_time(config.MARKET_CLOSE_HOUR - 1, 55)
        close_end = datetime_time(config.MARKET_CLOSE_HOUR, 5)
        
        return close_start <= current_time <= close_end
    
    def get_next_market_open(self) -> str:
        """
        Sonraki piyasa açılış zamanını hesaplar (Türkiye saati).
        
        Returns:
            str: İnsan okunabilir açılış zamanı
        """
        # Timezone modülündeki fonksiyonu kullan
        return tz_get_next_market_open()
    
    async def send_market_closed_status_report(self):
        """
        Piyasa kapalıyken durum raporu gönderir.
        Bot başlatıldığında piyasa kapalıysa bu rapor gönderilir.
        """
        logger.info("📊 Piyasa kapalı durum raporu hazırlanıyor...")
        
        # Provider sağlık durumlarını güncelle
        await self.provider_manager.update_all_health()
        
        # Rapor verilerini hazırla
        provider_health = self.provider_manager.get_health_summary()
        symbol_count = len(self.get_symbol_list())
        next_open = self.get_next_market_open()
        
        # Raporu gönder
        self.telegram_notifier.send_status_report(
            market_open=False,
            next_open_time=next_open,
            provider_health=provider_health,
            symbol_count=symbol_count,
            bot_version="2.0",
            last_data_time=self._last_successful_data_time
        )
        
        logger.info(f"✅ Durum raporu gönderildi (Sonraki açılış: {next_open})")
    
    def _record_successful_data_fetch(self):
        """Başarılı veri çekme zamanını kaydet"""
        self._last_successful_data_time = now_turkey()
        self._data_outage_alert_sent = False  # Uyarı flag'ini sıfırla
    
    def _check_data_outage(self):
        """
        Veri kesintisi kontrolü.
        2 günden fazla veri alınamazsa Telegram uyarısı gönder.
        """
        if self._last_successful_data_time is None:
            return
        
        # Zaten uyarı gönderilmişse tekrar gönderme
        if self._data_outage_alert_sent:
            return
        
        time_since_last_data = now_turkey() - self._last_successful_data_time
        outage_threshold = timedelta(days=getattr(config, 'DATA_OUTAGE_ALERT_DAYS', 2))
        
        if time_since_last_data > outage_threshold:
            logger.critical(f"⚠️ KRİTİK: {time_since_last_data.days} gündür veri alınamıyor!")
            
            # Telegram uyarısı gönder
            self.telegram_notifier.send_data_outage_alert(
                last_data_time=self._last_successful_data_time,
                outage_duration=time_since_last_data
            )
            
            self._data_outage_alert_sent = True
    
    def get_symbol_list(self) -> List[str]:
        """BİST sembol listesini döndürür"""
        symbols = [s for s in config.BIST_SYMBOLS if s not in config.BLACKLIST_SYMBOLS]
        return symbols
    
    async def analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Tek bir sembolü analiz eder (async).
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            dict: Analiz sonuçları veya None
        """
        try:
            logger.debug(f"Analiz başlıyor: {symbol}")
            
            # ===== VERİ TOPLAMA (Provider Manager) =====
            
            # OHLCV verisi (günlük - indikatörler için)
            # Retry mekanizması ile veri çekme
            max_retries = getattr(config, 'DATA_FETCH_MAX_RETRIES', 3)
            retry_delay = getattr(config, 'DATA_FETCH_RETRY_DELAY', 5)
            
            ohlcv = None
            for attempt in range(max_retries):
                ohlcv = await self.provider_manager.get_ohlcv_daily(symbol, limit=config.HISTORICAL_DAYS)
                
                if ohlcv is not None and not ohlcv.empty:
                    self._record_successful_data_fetch()  # Başarılı veri kaydı
                    break
                
                if attempt < max_retries - 1:
                    logger.debug(f"{symbol}: OHLCV verisi alınamadı, retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(retry_delay)
            
            if ohlcv is None or ohlcv.empty:
                logger.warning(f"{symbol}: OHLCV verisi alınamadı ({max_retries} deneme)")
                return None
            
            # Günlük istatistikler (TradingView HTTP veya fallback)
            daily_stats = await self.provider_manager.get_daily_stats(symbol)
            
            if daily_stats is None:
                logger.warning(f"{symbol}: Daily stats alınamadı")
                return None
            
            # Temel analiz verileri (opsiyonel)
            fundamentals = await self.provider_manager.get_fundamentals(symbol)
            
            # Spread tahmini (opsiyonel)
            spread = await self.provider_manager.get_bid_ask_spread(symbol)
            
            # ===== VERİ YAPISINI OLUŞTUR =====
            
            # daily_stats'a eksik alanları ekle (filters.py uyumluluğu)
            if 'symbol' not in daily_stats:
                daily_stats['symbol'] = symbol
            
            # daily_volume_tl hesapla (yoksa)
            if 'daily_volume_tl' not in daily_stats:
                volume = daily_stats.get('volume', 0)
                price = daily_stats.get('current_price', daily_stats.get('close', 0))
                daily_stats['daily_volume_tl'] = volume * price
            
            # Sembol verilerini birleştir
            symbol_data = {
                'ohlcv': ohlcv,
                'daily_stats': daily_stats,
                'fundamentals': fundamentals,
                'spread': spread
            }
            
            # ===== ÖN FİLTRELER =====
            
            passes_filters, filter_message = apply_all_filters(symbol_data)
            if not passes_filters:
                logger.debug(f"{symbol}: Filtreden elendi - {filter_message}")
                return None
            
            # ===== İNDİKATÖR HESAPLAMALARI =====
            
            trend_indicators = calculate_trend_indicators(ohlcv)
            momentum_indicators = calculate_momentum_indicators(ohlcv)
            volume_indicators = calculate_volume_indicators(ohlcv)
            pa_indicators = calculate_price_action_features(ohlcv)
            
            # Verileri symbol_data'ya ekle (filters uyumluluğu)
            symbol_data['volume_indicators'] = volume_indicators
            symbol_data['pa_indicators'] = pa_indicators
            
            # ===== SKORLAMA =====
            
            signal = calculate_total_score(
                symbol=symbol,
                trend_indicators=trend_indicators,
                momentum_indicators=momentum_indicators,
                volume_indicators=volume_indicators,
                pa_indicators=pa_indicators,
                fundamentals=fundamentals
            )
            
            logger.info(f"{symbol}: {signal['signal_level']} - Skor: {signal['total_score']}/{signal['max_possible_score']}")
            
            return {
                'symbol': symbol,
                'signal': signal,
                'daily_stats': daily_stats
            }
            
        except Exception as e:
            logger.error(f"{symbol} analiz hatası: {str(e)}")
            logger.debug(traceback.format_exc())
            self.stats['errors'] += 1
            return None
    
    async def send_market_open_report(self):
        """Piyasa açılışında veri akışı raporu gönder"""
        today = today_turkey()
        
        # Bugün zaten rapor gönderilmiş mi?
        if self._last_market_open_report and self._last_market_open_report.date() == today:
            return
        
        logger.info("📊 Piyasa açılış raporu hazırlanıyor...")
        
        # Provider sağlık durumlarını güncelle
        await self.provider_manager.update_all_health()
        
        # Raporu gönder
        self.telegram_notifier.send_market_open_report(
            provider_health=self.provider_manager.get_health_summary(),
            last_data_time=self._last_successful_data_time,
            stats=self.stats
        )
        
        self._last_market_open_report = now_turkey()
    
    async def send_market_close_report(self):
        """Piyasa kapanışında veri akışı raporu gönder"""
        today = today_turkey()
        
        # Bugün zaten rapor gönderilmiş mi?
        if self._last_market_close_report and self._last_market_close_report.date() == today:
            return
        
        logger.info("📊 Piyasa kapanış raporu hazırlanıyor...")
        
        # Provider istatistiklerini al
        provider_stats = self.provider_manager.get_stats()
        
        # Raporu gönder
        self.telegram_notifier.send_market_close_report(
            provider_stats=provider_stats,
            bot_stats=self.stats,
            last_data_time=self._last_successful_data_time
        )
        
        self._last_market_close_report = now_turkey()
    
    async def debug_single_symbol_scan(self, symbol: str = "GARAN"):
        """
        Tek sembol için detaylı debug taraması.
        
        Tüm veri akışını ve skorlamayı test eder.
        """
        logger.info(f"🔍 DEBUG TARAMA: {symbol}")
        logger.info("=" * 50)
        
        try:
            # 1. Daily veri
            df_daily = await self.provider_manager.get_ohlcv_daily(symbol, limit=100)
            logger.info(f"  📊 Daily veri: {len(df_daily) if df_daily is not None and not df_daily.empty else 0} bar")
            
            if df_daily is not None and not df_daily.empty:
                logger.info(f"     Son tarih: {df_daily.index[-1]}")
                logger.info(f"     Son kapanış: {df_daily['close'].iloc[-1]:.2f}")
            
            # 2. Daily stats
            stats = await self.provider_manager.get_daily_stats(symbol)
            logger.info(f"  📈 Daily stats: {'✅' if stats else '❌'}")
            if stats:
                logger.info(f"     Fiyat: {stats.get('current_price', 'N/A')}")
                logger.info(f"     Hacim: {stats.get('volume', 'N/A')}")
                logger.info(f"     Değişim: {stats.get('daily_change_percent', 'N/A')}%")
            
            # 3. Fundamentals
            fundamentals = await self.provider_manager.get_fundamentals(symbol)
            logger.info(f"  💰 Fundamentals: {'✅' if fundamentals else '❌'}")
            if fundamentals:
                logger.info(f"     P/E: {fundamentals.get('pe_ratio', 'N/A')}")
            
            # 4. İndikatörler
            if df_daily is not None and not df_daily.empty:
                trend_ind = calculate_trend_indicators(df_daily)
                mom_ind = calculate_momentum_indicators(df_daily)
                vol_ind = calculate_volume_indicators(df_daily)
                pa_ind = calculate_price_action_features(df_daily)
                
                logger.info(f"  📉 Trend indikatörleri: {len(trend_ind)} adet")
                logger.info(f"     RSI: {trend_ind.get('rsi_14', 'N/A')}")
                logger.info(f"     EMA20: {trend_ind.get('ema_20', 'N/A')}")
                
                # 5. Skor
                signal = calculate_total_score(
                    symbol=symbol,
                    trend_indicators=trend_ind,
                    momentum_indicators=mom_ind,
                    volume_indicators=vol_ind,
                    pa_indicators=pa_ind,
                    fundamentals=fundamentals
                )
                
                logger.info(f"  🎯 SKOR: {signal.get('total_score', 0)}/20")
                logger.info(f"     Trend: {signal.get('trend_score', 0)}/5")
                logger.info(f"     Momentum: {signal.get('momentum_score', 0)}/5")
                logger.info(f"     Hacim: {signal.get('volume_score', 0)}/5")
                logger.info(f"     Temel/PA: {signal.get('fundamental_pa_score', 0)}/5")
                logger.info(f"     Seviye: {signal.get('signal_level', 'N/A')}")
                
                if signal.get('triggered_criteria'):
                    logger.info(f"  📋 Tetiklenen kriterler:")
                    for crit in signal.get('triggered_criteria', [])[:5]:
                        logger.info(f"     • {crit}")
            
        except Exception as e:
            logger.error(f"  ❌ Hata: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        logger.info("=" * 50)
    
    async def scan_all_symbols(self, is_startup: bool = False):
        """
        Tüm sembolleri tarar ve sinyal üretir.
        
        Args:
            is_startup: Bot başlangıcında mı çağrılıyor (piyasa kontrolü atlanır)
        """
        try:
            scan_type = "BAŞLANGIÇ" if is_startup else "YENİ"
            logger.info("=" * 60)
            logger.info(f"🔍 {scan_type} TARAMA BAŞLIYOR - {format_timestamp()}")
            logger.info("=" * 60)
            
            self.stats['total_scans'] += 1
            
            # Piyasa kontrolü (startup taramasında atla)
            if not is_startup and not self.is_market_open():
                logger.info("⏸️  Piyasa kapalı, tarama yapılmıyor")
                return
            
            # Sembol listesi
            symbols = self.get_symbol_list()
            logger.info(f"📊 {len(symbols)} sembol taranacak")
            
            # Veri gecikmesi uyarısı (her taramada hatırlat)
            if config.DATA_DELAY_ENABLED:
                logger.info(f"⏱️ Veriler {config.DATA_DELAY_MINUTES} dakika gecikmelidir")
            
            # Her sembolü analiz et
            signals_to_send = []
            # 🔍 DEBUG: Tüm analiz sonuçlarını topla (sinyal üretmese bile)
            all_analyzed_results = []
            
            for symbol in symbols:
                # Shutdown kontrolü
                if self._shutdown_requested:
                    logger.info("Tarama durduruldu (shutdown isteği)")
                    break
                
                self.stats['total_symbols_analyzed'] += 1
                
                result = await self.analyze_symbol(symbol)
                
                if result is None:
                    continue
                
                signal = result['signal']
                daily_stats = result['daily_stats']
                
                # 🔍 DEBUG: Tüm sonuçları topla (skor > 0 olanları)
                if signal.get('total_score', 0) > 0:
                    all_analyzed_results.append({
                        'symbol': symbol,
                        'signal': signal,
                        'daily_stats': daily_stats
                    })
                
                # Sinyal seviyesi kontrolü
                signal_level = signal['signal_level']
                
                if signal_level in ['STRONG_BUY', 'ULTRA_BUY']:
                    self.stats['total_signals_generated'] += 1
                    
                    # Cooldown kontrolü
                    if self.cooldown_manager.can_send_signal(symbol, signal_level):
                        signals_to_send.append({
                            'signal': signal,
                            'daily_stats': daily_stats
                        })
                        
                        # Cooldown'a kaydet
                        self.cooldown_manager.register_signal(symbol, signal_level)
                    else:
                        logger.info(f"{symbol}: Cooldown aktif, sinyal gönderilmedi")
                
                # Rate limiting için kısa bekleme
                await asyncio.sleep(0.1)
            
            # Sinyalleri gönder
            logger.info(f"📤 {len(signals_to_send)} sinyal gönderilecek")
            
            for item in signals_to_send:
                success = self.telegram_notifier.send_signal_message(
                    signal=item['signal'],
                    daily_stats=item['daily_stats']
                )
                
                if success:
                    self.stats['total_signals_sent'] += 1
                
                await asyncio.sleep(1)  # Telegram rate limit
            
            # Provider istatistiklerini güncelle
            provider_stats = self.provider_manager.get_stats()
            self.stats['provider_failovers'] = provider_stats.get('failover_count', 0)
            
            # 🔍 DEBUG: En yüksek skorlu 5 hisseyi logla
            top_5 = self._get_top_scored_results(all_analyzed_results, limit=5)
            self._log_top_scored_results(top_5)
            
            # Telegram'a tarama özeti gönder
            self.telegram_notifier.send_scan_summary(
                total_scanned=len(symbols),
                signals_generated=len(signals_to_send),
                top_results=top_5
            )
            
            # Tarama özeti
            logger.info("=" * 60)
            logger.info("📊 TARAMA ÖZETİ:")
            logger.info(f"  ✓ Analiz edilen: {len(symbols)}")
            logger.info(f"  ✓ Sinyal üretilen: {self.stats['total_signals_generated']}")
            logger.info(f"  ✓ Gönderilen: {len(signals_to_send)}")
            logger.info(f"  ⚡ Provider failover: {self.stats['provider_failovers']}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Tarama hatası: {str(e)}")
            logger.debug(traceback.format_exc())
            self.stats['errors'] += 1
            
            # Kritik hata bildirimi
            try:
                self.telegram_notifier.send_error_alert(f"Tarama hatası: {str(e)}")
            except:
                pass
    
    def should_scan_at_open(self) -> bool:
        """
        Açılış taraması yapılmalı mı kontrol eder.
        Bugün henüz açılış taraması yapılmadıysa True döner.
        """
        if not self.is_market_opening():
            return False
        
        today = today_turkey()
        if self._last_open_scan and self._last_open_scan.date() == today:
            return False
        
        return True
    
    def should_scan_at_close(self) -> bool:
        """
        Kapanış taraması yapılmalı mı kontrol eder.
        Bugün henüz kapanış taraması yapılmadıysa True döner.
        """
        if not self.is_market_closing():
            return False
        
        today = today_turkey()
        if self._last_close_scan and self._last_close_scan.date() == today:
            return False
        
        return True
    
    async def run_startup_analysis(self):
        """
        Bot başlarken günlük analiz raporu gönderir.
        Piyasa durumundan bağımsız olarak çalışır.
        Piyasa kapalıysa durum raporu da gönderir.
        """
        if self._startup_scan_done:
            return
        
        logger.info("="*60)
        logger.info("🚀 BAŞLANGIÇ ANALİZİ")
        logger.info("="*60)
        
        # Provider sağlık durumlarını güncelle
        await self.provider_manager.update_all_health()
        
        # Piyasa kapalıysa durum raporu gönder
        if not self.is_market_open():
            logger.info("🔴 Piyasa kapalı - durum raporu gönderiliyor...")
            await self.send_market_closed_status_report()
        
        # Tarama yap ve rapor gönder
        await self.scan_all_symbols(is_startup=True)
        
        self._startup_scan_done = True
        logger.info("✅ Başlangıç analizi tamamlandı")
    
    async def run_scheduler(self):
        """
        Zamanlayıcı - tarama moduna göre çalışır.
        
        Modlar:
        - "open_close": Sadece piyasa açılış ve kapanışında tarama (günde 2x)
        - "continuous": Sürekli tarama (eski davranış)
        - "hybrid": Günlük veri yenileme + 15dk intraday tarama (ÖNERİLEN)
        """
        scan_mode = getattr(config, 'SCAN_MODE', 'continuous')
        check_interval = getattr(config, 'MARKET_CHECK_INTERVAL', 60)
        intraday_interval = getattr(config, 'INTRADAY_SCAN_INTERVAL', 900)
        
        logger.info(f"⏰ Zamanlayıcı başlatıldı (mod: {scan_mode})")
        
        if scan_mode == 'hybrid':
            logger.info(f"🔄 Hybrid mod aktif:")
            logger.info(f"   📊 Günlük yenileme: {getattr(config, 'DAILY_DATA_REFRESH_TIMES', ['09:55', '18:05'])}")
            logger.info(f"   🔍 İntraday tarama: Her {intraday_interval // 60} dakika")
            logger.info(f"   ⏱️ İlk tarama: Açılıştan {getattr(config, 'FIRST_SCAN_DELAY_MINUTES', 15)} dk sonra")
        elif scan_mode == 'open_close':
            logger.info("📅 Açılış + Kapanış modu aktif (günde 2 tarama)")
        else:
            logger.info(f"🔄 Sürekli tarama modu (her {config.SCAN_INTERVAL_SECONDS}s)")
        
        while not self._shutdown_requested:
            try:
                if scan_mode == 'hybrid':
                    # ===== HYBRID MOD (ÖNERİLEN) =====
                    await self._run_hybrid_cycle()
                    wait_time = 30  # Hybrid modda 30sn kontrol aralığı
                    
                    # Debug: Sonraki tarama zamanını logla (sadece tarama yapıldıktan sonra)
                    if self._last_intraday_scan:
                        next_scan_time = self._calculate_next_intraday_scan_time()
                        if next_scan_time:
                            time_until = (next_scan_time - datetime.now()).total_seconds()
                            if time_until > 0 and time_until < 120:  # 2 dakika kala logla
                                logger.debug(f"⏰ Sonraki tarama: {next_scan_time.strftime('%H:%M')} ({time_until/60:.1f}dk kaldı)")
                    
                elif scan_mode == 'open_close':
                    # ===== AÇILIŞ + KAPANIŞ MODU =====
                    
                    # Açılış taraması
                    if self.should_scan_at_open():
                        logger.info("🌅 Piyasa açılışı - tarama başlatılıyor...")
                        await self.send_market_open_report()
                        await self.scan_all_symbols()
                        self._last_open_scan = now_turkey()
                        logger.info("✅ Açılış taraması tamamlandı")
                    
                    # Kapanış taraması
                    elif self.should_scan_at_close():
                        logger.info("🌇 Piyasa kapanışı - tarama başlatılıyor...")
                        await self.scan_all_symbols()
                        await self.send_market_close_report()
                        self._last_close_scan = now_turkey()
                        logger.info("✅ Kapanış taraması tamamlandı")
                    
                    # Bekleme
                    wait_time = check_interval
                    now = now_turkey()
                    
                    # Sonraki tarama zamanını hesapla ve logla
                    if self.is_market_open():
                        next_scan = "Kapanış (17:55)"
                    elif now.hour < config.MARKET_OPEN_HOUR:
                        next_scan = f"Açılış ({config.MARKET_OPEN_HOUR}:00)"
                    else:
                        next_scan = f"Yarın açılış ({config.MARKET_OPEN_HOUR}:00)"
                    
                    logger.debug(f"⏳ Sonraki tarama: {next_scan}, kontrol {wait_time}s sonra")
                    
                else:
                    # ===== SÜREKLİ TARAMA MODU (ESKİ DAVRANIŞ) =====
                    await self.scan_all_symbols()
                    
                    if self.is_market_open():
                        wait_time = config.SCAN_INTERVAL_SECONDS
                    else:
                        wait_time = 300
                        logger.info(f"📅 Piyasa kapalı, {wait_time}s sonra kontrol")
                
                # Bekleme (her iki mod için ortak)
                if not self._shutdown_requested:
                    for _ in range(wait_time):
                        if self._shutdown_requested:
                            break
                        await asyncio.sleep(1)
                
                # Periyodik temizlik
                if self.stats['total_scans'] % 10 == 0:
                    self.cooldown_manager.cleanup_old_entries()
                
                # Veri kesintisi kontrolü
                self._check_data_outage()
                
            except asyncio.CancelledError:
                logger.info("⏹️  Scheduler iptal edildi")
                break
            except Exception as e:
                logger.error(f"Scheduler hatası: {str(e)}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(60)
    
    # ============================================================
    # HYBRID MOD FONKSİYONLARI
    # ============================================================
    
    async def _run_hybrid_cycle(self):
        """
        Hybrid mod döngüsü - Günlük veri yenileme + İntraday tarama.
        
        İş akışı:
        1. Günlük veri yenileme zamanı mı kontrol et (09:55, 18:05)
        2. İntraday tarama zamanı mı kontrol et (her 15dk, 10:15-18:00)
        3. Piyasa kapalıysa bekle
        """
        now = now_turkey()
        current_time_str = now.strftime("%H:%M")
        
        # ===== GÜNLÜK VERİ YENİLEME =====
        refresh_times = getattr(config, 'DAILY_DATA_REFRESH_TIMES', ["09:55", "18:05"])
        
        if self._should_refresh_daily_data(current_time_str, refresh_times):
            await self.refresh_daily_data()
        
        # ===== PİYASA KONTROLÜ =====
        if not self.is_market_open():
            return
        
        # ===== İNTRADAY TARAMA =====
        should_scan = self._should_run_intraday_scan()
        
        # Sadece dakika başlarında veya tarama zamanı geldiğinde logla
        if self._last_intraday_scan and now.second < 5:
            next_scan_time = self._calculate_next_intraday_scan_time()
            next_scan_str = next_scan_time.strftime('%H:%M') if next_scan_time else "Piyasa kapandı"
            time_until = (next_scan_time - now).total_seconds() / 60 if next_scan_time else 0
            if time_until > 0:
                logger.debug(f"⏳ Sonraki tarama: {next_scan_str} ({time_until:.0f}dk kaldı)")
        
        if should_scan:
            await self.run_intraday_scan()
    
    def _should_refresh_daily_data(self, current_time_str: str, refresh_times: List[str]) -> bool:
        """
        Günlük veri yenileme zamanı mı kontrol eder.
        
        Her refresh time için sadece 1 kez yenileme yapar (aynı dakika içinde).
        """
        today = today_turkey()
        
        # Bugün zaten yenileme yapıldı mı?
        if self._last_daily_refresh and self._last_daily_refresh.date() == today:
            # Son yenilemeden sonra mı?
            last_refresh_time = self._last_daily_refresh.strftime("%H:%M")
            
            # Eğer current_time bir refresh time ise ve henüz bu sefer yapılmadıysa
            for refresh_time in refresh_times:
                if current_time_str == refresh_time and last_refresh_time != refresh_time:
                    return True
            return False
        
        # Bugün henüz hiç yenileme yapılmadı
        if current_time_str in refresh_times:
            return True
        
        # Bot yeni başladıysa ve cache boşsa, hemen yenile
        if not self._last_daily_refresh and len(daily_cache.get_all_symbols()) == 0:
            return True
        
        return False
    
    def _should_run_intraday_scan(self) -> bool:
        """
        İntraday tarama zamanı mı kontrol eder.
        
        Basit mantık:
        - Piyasa açık olmalı
        - Son taramadan INTRADAY_SCAN_INTERVAL geçmiş olmalı
        """
        now = now_turkey()
        first_scan_delay = getattr(config, 'FIRST_SCAN_DELAY_MINUTES', 15)
        intraday_interval = getattr(config, 'INTRADAY_SCAN_INTERVAL', 900)  # 15 dakika
        
        # İlk tarama gecikmesi (10:15'te başla) - Türkiye saati
        market_open_time = now.replace(
            hour=config.MARKET_OPEN_HOUR, 
            minute=first_scan_delay,
            second=0,
            microsecond=0
        )
        
        if now < market_open_time:
            return False
        
        # Piyasa kapanmış mı?
        market_close_time = now.replace(
            hour=config.MARKET_CLOSE_HOUR,
            minute=0,
            second=0,
            microsecond=0
        )
        if now >= market_close_time:
            return False
        
        # İlk tarama henüz yapılmadıysa
        if self._last_intraday_scan is None:
            return True
        
        # Son taramadan yeterli süre geçti mi?
        elapsed = (now - self._last_intraday_scan).total_seconds()
        if elapsed >= intraday_interval:
            return True
        
        return False
    
    def _calculate_next_intraday_scan_time(self) -> Optional[datetime]:
        """
        Son tarama + interval olarak sonraki tarama zamanını hesaplar.
        
        Returns:
            datetime: Sonraki tarama zamanı veya None (piyasa kapalıysa)
        """
        now = now_turkey()
        intraday_interval = getattr(config, 'INTRADAY_SCAN_INTERVAL', 900)  # 15 dakika
        
        # Piyasa kapanış zamanı - Türkiye saati
        market_close = now.replace(
            hour=config.MARKET_CLOSE_HOUR,
            minute=0,
            second=0,
            microsecond=0
        )
        
        # Son tarama yoksa, şu an
        if self._last_intraday_scan is None:
            return now
        
        # Sonraki tarama = son tarama + interval
        next_scan = self._last_intraday_scan + timedelta(seconds=intraday_interval)
        
        # Piyasa kapanışını geçtiyse None dön
        if next_scan >= market_close:
            return None
        
        return next_scan
    
    async def refresh_daily_data(self):
        """
        Günlük veriyi yenile (trend analizi için).
        
        Bu fonksiyon günde sadece 2 kez çalışır:
        - 09:55 - Piyasa açılmadan önce (önceki gün kapanış verisiyle)
        - 18:05 - Piyasa kapandıktan sonra (günün kapanış verisiyle)
        
        Her sembol için:
        1. 100 günlük OHLCV verisi çek
        2. Günlük istatistikleri çek  
        3. Trend indikatörlerini hesapla
        4. Cache'e kaydet
        """
        start_time = now_turkey()
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 GÜNLÜK VERİ YENİLEME BAŞLIYOR")
        logger.info("=" * 60)
        
        symbols = self.get_symbol_list()
        success_count = 0
        error_count = 0
        
        for symbol in symbols:
            if self._shutdown_requested:
                break
            
            try:
                # 1. OHLCV verisi çek
                ohlcv = await self.provider_manager.get_ohlcv_daily(
                    symbol, 
                    limit=config.HISTORICAL_DAYS
                )
                
                if ohlcv is None or ohlcv.empty:
                    logger.warning(f"{symbol}: OHLCV verisi alınamadı")
                    error_count += 1
                    continue
                
                # 2. Günlük istatistikler
                daily_stats = await self.provider_manager.get_daily_stats(symbol)
                if daily_stats is None:
                    daily_stats = {}
                
                # 3. Trend indikatörleri hesapla
                trend_data = calculate_trend_indicators(ohlcv)
                
                # 4. Cache'e kaydet
                daily_cache.set(symbol, ohlcv, daily_stats, trend_data)
                
                success_count += 1
                self._record_successful_data_fetch()
                
            except Exception as e:
                logger.warning(f"{symbol}: Günlük veri hatası: {e}")
                error_count += 1
            
            # Rate limiting
            await asyncio.sleep(0.05)
        
        # Yenileme zamanını kaydet
        self._last_daily_refresh = now_turkey()
        daily_cache.mark_refreshed()
        
        # Günlük intraday sayacını sıfırla (yeni güne geçişte)
        if now_turkey().hour < 10:
            self._intraday_scan_count = 0
        
        elapsed = (now_turkey() - start_time).total_seconds()
        
        logger.info("")
        logger.info(f"✅ Günlük veri yenileme tamamlandı:")
        logger.info(f"   📈 Başarılı: {success_count}/{len(symbols)}")
        logger.info(f"   ❌ Hata: {error_count}")
        logger.info(f"   ⏱️ Süre: {elapsed:.1f} saniye")
        logger.info("=" * 60)
    
    async def run_intraday_scan(self):
        """
        İntraday tarama - Momentum, hacim ve breakout sinyalleri için.
        
        Her 15 dakikada bir çalışır. Cache'teki günlük trend verisini kullanır.
        Sadece momentum, hacim ve price action skorlarını yeniden hesaplar.
        
        Bu sayede:
        - Trend analizi günlük veriden gelir (cache)
        - Momentum/hacim/PA anlık veriden hesaplanır
        - API yükü minimize edilir
        """
        start_time = now_turkey()
        self._intraday_scan_count += 1
        self.stats['total_scans'] += 1
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"🔍 İNTRADAY TARAMA #{self._intraday_scan_count} - {format_timestamp()}")
        logger.info("=" * 60)
        
        # Filtre istatistiklerini sıfırla
        reset_filter_stats()
        
        # Veri gecikmesi uyarısı
        if config.DATA_DELAY_ENABLED:
            logger.info(f"⏱️ Veriler {config.DATA_DELAY_MINUTES} dakika gecikmelidir")
        
        symbols = self.get_symbol_list()
        signals_to_send = []
        all_analyzed_results = []
        analyzed_count = 0
        cache_hits = 0
        cache_misses = 0
        filter_rejected = 0
        data_errors = 0
        signals_blocked_by_cooldown = 0
        high_scorer_debug_count = 0  # Yüksek skorlu semboller için debug sayacı
        
        # Cache durumu
        cached_symbols = daily_cache.get_all_symbols()
        logger.info(f"📦 Cache durumu: {len(cached_symbols)}/{len(symbols)} sembol")
        
        # Error logger'a tarama başlangıcını bildir
        scan_error_logger.log_scan_start("INTRADAY", len(symbols))
        
        for symbol in symbols:
            if self._shutdown_requested:
                break
            
            self.stats['total_symbols_analyzed'] += 1
            is_cache_hit = False
            data_source = "unknown"
            
            try:
                # Cache'ten günlük veri al
                cached_data = daily_cache.get(symbol)
                
                if cached_data is None:
                    cache_misses += 1
                    is_cache_hit = False
                    # Cache'te yoksa, günlük veriyi çek
                    if cache_misses <= 3:
                        logger.info(f"{symbol}: Cache miss, günlük veri çekiliyor...")
                    ohlcv = await self.provider_manager.get_ohlcv_daily(
                        symbol, 
                        limit=config.HISTORICAL_DAYS
                    )
                    if ohlcv is None or ohlcv.empty:
                        data_errors += 1
                        scan_error_logger.log_provider_issue("daily_fetch", symbol, "OHLCV veri yok")
                        continue
                    data_source = "yahoo"  # Daily veri yahoo'dan geliyor
                    trend_data = calculate_trend_indicators(ohlcv)
                    daily_stats = await self.provider_manager.get_daily_stats(symbol) or {}
                    daily_cache.set(symbol, ohlcv, daily_stats, trend_data)
                    cached_data = daily_cache.get(symbol)
                else:
                    cache_hits += 1
                    is_cache_hit = True
                    data_source = "cache"
                
                ohlcv = cached_data["df"]
                trend_indicators = cached_data["trend"]
                
                # Güncel istatistikler (her taramada yenile)
                daily_stats = await self.provider_manager.get_daily_stats(symbol)
                if daily_stats is None:
                    scan_error_logger.log_provider_issue("daily_stats", symbol, "stats alınamadı")
                    continue
                
                # Filtre kontrolü
                if 'daily_volume_tl' not in daily_stats:
                    volume = daily_stats.get('volume', 0)
                    price = daily_stats.get('current_price', daily_stats.get('close', 0))
                    daily_stats['daily_volume_tl'] = volume * price
                
                symbol_data = {
                    'ohlcv': ohlcv,
                    'daily_stats': daily_stats,
                    'fundamentals': await self.provider_manager.get_fundamentals(symbol),
                    'spread': await self.provider_manager.get_bid_ask_spread(symbol)
                }
                
                # GARAN explicit check - debug için
                spread_val = symbol_data.get('spread', 0)
                if symbol == "GARAN":
                    logger.info(f"🔍 GARAN CHECK: spread={spread_val:.2f}%, daily_volume_tl={daily_stats.get('daily_volume_tl', 0)/1e6:.1f}M")
                
                passes_filters, filter_reason = apply_all_filters(symbol_data)
                
                # GARAN explicit result
                if symbol == "GARAN":
                    logger.info(f"🔍 GARAN FILTER: passed={passes_filters}, reason={filter_reason}")
                
                if not passes_filters:
                    filter_rejected += 1
                    if filter_rejected <= 5:
                        logger.info(f"❌ {symbol}: Filtre reddetti - {filter_reason}")
                        scan_error_logger.log_error(f"filter_{symbol}", filter_reason)
                    continue
                
                # Momentum, hacim ve PA indikatörleri (anlık hesapla)
                momentum_indicators = calculate_momentum_indicators(ohlcv)
                volume_indicators = calculate_volume_indicators(ohlcv)
                pa_indicators = calculate_price_action_features(ohlcv)
                
                # Skorlama
                signal = calculate_total_score(
                    symbol=symbol,
                    trend_indicators=trend_indicators,
                    momentum_indicators=momentum_indicators,
                    volume_indicators=volume_indicators,
                    pa_indicators=pa_indicators,
                    fundamentals=symbol_data['fundamentals']
                )
                
                analyzed_count += 1
                self._record_successful_data_fetch()
                
                total_score = signal.get('total_score', 0)
                signal_level = signal.get('signal_level', 'NO_SIGNAL')
                trend_s = signal.get('trend_score', 0)
                mom_s = signal.get('momentum_score', 0)
                vol_s = signal.get('volume_score', 0)
                fund_s = signal.get('fundamental_pa_score', 0)
                
                # Debug: İlk 5 analiz edilen sembolün skorunu logla
                if analyzed_count <= 5:
                    logger.info(f"🔍 DEBUG {symbol}: Skor={total_score}/20 (T:{trend_s} M:{mom_s} V:{vol_s} F:{fund_s})")
                
                # Yüksek skorlu semboller için detaylı debug (ilk 3)
                if total_score >= 10 and high_scorer_debug_count < 3:
                    high_scorer_debug_count += 1
                    should_send = total_score >= config.STRONG_BUY_THRESHOLD
                    logger.info(f"🔍 HIGH_SCORE_DEBUG {symbol}: Score={total_score}, Level={signal_level}")
                    logger.info(f"   Cache: {is_cache_hit}, Data source: {data_source}")
                    logger.info(f"   Threshold: {config.STRONG_BUY_THRESHOLD}, Should send: {should_send}")
                    
                    # Error logger'a yüksek skorlu sembolü kaydet
                    scan_error_logger.log_high_scorer(
                        symbol=symbol,
                        score=total_score,
                        level=signal_level,
                        trend_score=trend_s,
                        momentum_score=mom_s,
                        volume_score=vol_s,
                        fundamental_score=fund_s,
                        triggered_criteria=signal.get('triggered_criteria', [])
                    )
                
                # Debug için tüm sonuçları topla
                if total_score > 0:
                    all_analyzed_results.append({
                        'symbol': symbol,
                        'signal': signal,
                        'daily_stats': daily_stats
                    })
                
                # Sinyal kontrolü
                actual_sent = False
                block_reason = ""
                
                if signal_level in ['STRONG_BUY', 'ULTRA_BUY']:
                    self.stats['total_signals_generated'] += 1
                    
                    if self.cooldown_manager.can_send_signal(symbol, signal_level):
                        signals_to_send.append({
                            'signal': signal,
                            'daily_stats': daily_stats
                        })
                        self.cooldown_manager.register_signal(symbol, signal_level)
                        actual_sent = True
                    else:
                        signals_blocked_by_cooldown += 1
                        block_reason = "COOLDOWN"
                else:
                    block_reason = "BELOW_THRESHOLD"
                
                # Error logger'a sonucu kaydet (sadece score >= 10)
                if total_score >= 10:
                    scan_error_logger.log_scan_result(
                        symbol=symbol,
                        score=total_score,
                        level=signal_level,
                        sent=actual_sent,
                        reason=block_reason,
                        cache_hit=is_cache_hit,
                        data_source=data_source
                    )
                
            except Exception as e:
                logger.warning(f"{symbol}: İntraday tarama hatası: {e}")
                self.stats['errors'] += 1
                scan_error_logger.log_error(f"scan_{symbol}", str(e))
            
            await asyncio.sleep(0.05)
        
        # Sinyalleri gönder
        for item in signals_to_send:
            success = self.telegram_notifier.send_signal_message(
                signal=item['signal'],
                daily_stats=item['daily_stats']
            )
            if success:
                self.stats['total_signals_sent'] += 1
            await asyncio.sleep(1)
        
        # Debug: Top 5 logla
        top_5 = self._get_top_scored_results(all_analyzed_results, limit=5)
        self._log_top_scored_results(top_5)
        
        # Telegram özet
        self.telegram_notifier.send_scan_summary(
            total_scanned=len(symbols),
            signals_generated=len(signals_to_send),
            top_results=top_5
        )
        
        # Tarama zamanını kaydet
        self._last_intraday_scan = now_turkey()
        elapsed = (now_turkey() - start_time).total_seconds()
        
        # Sonraki tarama zamanı
        next_scan_time = self._calculate_next_intraday_scan_time()
        next_scan = next_scan_time.strftime("%H:%M") if next_scan_time else "Yarın"
        
        # Error logger'a özet yaz
        scan_error_logger.log_scan_summary(
            scan_number=self._intraday_scan_count,
            scan_type="INTRADAY",
            total_symbols=len(symbols),
            analyzed=analyzed_count,
            signals_sent=len(signals_to_send),
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            filter_rejected=filter_rejected,
            data_errors=data_errors,
            duration_seconds=elapsed
        )
        
        # Filtre istatistiklerini al
        filter_stats = get_filter_stats()
        
        logger.info("")
        logger.info(f"📊 İNTRADAY TARAMA #{self._intraday_scan_count} ÖZET:")
        logger.info(f"   • Tip: İntraday (15m cache + anlık momentum)")
        logger.info(f"   • Analiz: {analyzed_count}/{len(symbols)} sembol")
        logger.info(f"   • Cache: {cache_hits} hit, {cache_misses} miss")
        logger.info(f"   • Filtre: {filter_rejected} reddedildi, {data_errors} veri hatası")
        logger.info(f"   • Sinyal: {len(signals_to_send)} gönderildi")
        logger.info(f"   • Süre: {elapsed:.1f} saniye")
        logger.info(f"   • Sonraki: {next_scan}")
        logger.info(f"   • Cache: {len(daily_cache.get_all_symbols())} sembol")
        
        # Detaylı filtre istatistikleri
        logger.info(f"📊 Filtre İstatistikleri:")
        logger.info(f"   • Spread reddetti: {filter_stats.get('spread_rejected', 0)}")
        logger.info(f"   • Hacim reddetti: {filter_stats.get('volume_rejected', 0)}")
        logger.info(f"   • Fiyat reddetti: {filter_stats.get('price_rejected', 0)}")
        logger.info(f"   • Kara liste: {filter_stats.get('blacklist_rejected', 0)}")
        logger.info(f"   • Volatilite: {filter_stats.get('volatility_rejected', 0)}")
        logger.info(f"   • Veri hatası: {filter_stats.get('data_error', 0)}")
        logger.info(f"   • Geçti: {filter_stats.get('passed', 0)}")
        logger.info("=" * 60)
    
    def _get_top_scored_results(self, results: List[Dict], limit: int = 5) -> List[Dict]:
        """
        En yüksek skorlu sonuçları döndürür.
        
        Args:
            results: Tüm analiz sonuçları
            limit: Kaç sonuç döndürülsün
            
        Returns:
            list: En yüksek skorlu sonuçlar (sıralı)
        """
        if not results:
            return []
        
        # Toplam skora göre sırala (yüksekten düşüğe)
        sorted_results = sorted(
            results,
            key=lambda x: x['signal'].get('total_score', 0),
            reverse=True
        )
        
        return sorted_results[:limit]
    
    def _log_top_scored_results(self, top_results: List[Dict]):
        """
        En yüksek skorlu hisseleri detaylı olarak loglar.
        
        Args:
            top_results: En yüksek skorlu sonuçlar
        """
        if not top_results:
            logger.info("🔍 DEBUG: Hiç skor alan hisse bulunamadı")
            return
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("🏆 EN YÜKSEK SKORLU 5 HİSSE (sinyal üretmese bile)")
        logger.info("=" * 70)
        
        for i, result in enumerate(top_results, 1):
            symbol = result['symbol']
            signal = result['signal']
            daily_stats = result.get('daily_stats', {})
            
            total_score = signal.get('total_score', 0)
            max_score = signal.get('max_possible_score', 20)
            signal_level = signal.get('signal_level', 'NO_SIGNAL')
            
            # Blok skorları
            trend_score = signal.get('trend_score', 0)
            momentum_score = signal.get('momentum_score', 0)
            volume_score = signal.get('volume_score', 0)
            fundamental_pa_score = signal.get('fundamental_pa_score', 0)
            
            # Fiyat bilgisi
            current_price = daily_stats.get('current_price', 0)
            daily_change = daily_stats.get('daily_change_percent', 0)
            
            # Sinyal seviyesi emoji
            level_emoji = {
                'ULTRA_BUY': '🔥',
                'STRONG_BUY': '📈',
                'WATCHLIST': '👀',
                'NO_SIGNAL': '⚪'
            }.get(signal_level, '❓')
            
            logger.info(f"")
            logger.info(f"#{i} {symbol} - {level_emoji} {signal_level}")
            logger.info(f"   💰 Fiyat: {current_price:.2f} TL | Değişim: {daily_change:+.2f}%")
            logger.info(f"   🎯 TOPLAM SKOR: {total_score}/{max_score}")
            logger.info(f"      ├─ Trend:     {trend_score}/{config.MAX_TREND_SCORE}")
            logger.info(f"      ├─ Momentum:  {momentum_score}/{config.MAX_MOMENTUM_SCORE}")
            logger.info(f"      ├─ Hacim:     {volume_score}/{config.MAX_VOLUME_SCORE}")
            logger.info(f"      └─ Temel/PA:  {fundamental_pa_score}/{config.MAX_FUNDAMENTAL_PA_SCORE}")
            
            # Tetiklenen kriterler (en fazla 5)
            triggered = signal.get('triggered_criteria', [])
            if triggered:
                logger.info(f"   📋 Tetiklenen Kriterler:")
                for j, criterion in enumerate(triggered[:5], 1):
                    logger.info(f"      {j}. {criterion}")
                if len(triggered) > 5:
                    logger.info(f"      ... ve {len(triggered) - 5} kriter daha")
        
        logger.info("")
        logger.info("=" * 70)
    
    def print_stats(self):
        """İstatistikleri yazdırır"""
        print("\n" + "=" * 60)
        print("📊 BOT İSTATİSTİKLERİ")
        print("=" * 60)
        print(f"Toplam tarama: {self.stats['total_scans']}")
        print(f"Analiz edilen sembol: {self.stats['total_symbols_analyzed']}")
        print(f"Üretilen sinyal: {self.stats['total_signals_generated']}")
        print(f"Gönderilen sinyal: {self.stats['total_signals_sent']}")
        print(f"Hata sayısı: {self.stats['errors']}")
        print(f"Provider failover: {self.stats['provider_failovers']}")
        
        print("\nCooldown İstatistikleri:")
        cooldown_stats = self.cooldown_manager.get_stats()
        for key, value in cooldown_stats.items():
            print(f"  {key}: {value}")
        
        print("\nTelegram İstatistikleri:")
        telegram_stats = self.telegram_notifier.get_stats()
        for key, value in telegram_stats.items():
            print(f"  {key}: {value}")
        
        if self.provider_manager:
            print("\nProvider İstatistikleri:")
            provider_stats = self.provider_manager.get_stats()
            print(f"  Toplam istek: {provider_stats.get('total_requests', 0)}")
            print(f"  Başarılı: {provider_stats.get('successful_requests', 0)}")
            print(f"  Failover: {provider_stats.get('failover_count', 0)}")
            print(f"  Sağlık: {provider_stats.get('health', {})}")
        
        # Cache istatistikleri (hybrid mod)
        print("\nCache İstatistikleri:")
        cache_stats = daily_cache.get_stats()
        print(f"  Cache'li sembol: {cache_stats.get('cached_symbols', 0)}")
        print(f"  Son yenileme: {cache_stats.get('last_refresh', 'Never')}")
        print(f"  TTL: {cache_stats.get('ttl_hours', 12)} saat")
        
        if self._intraday_scan_count > 0:
            print(f"\nHybrid Mod İstatistikleri:")
            print(f"  Günlük intraday tarama: {self._intraday_scan_count}")
            print(f"  Son intraday: {self._last_intraday_scan.strftime('%H:%M:%S') if self._last_intraday_scan else 'Never'}")
            print(f"  Son günlük yenileme: {self._last_daily_refresh.strftime('%H:%M:%S') if self._last_daily_refresh else 'Never'}")
        
        print("=" * 60 + "\n")


async def main():
    """Ana async fonksiyon"""
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("🚀 BİST TRADING BOT (MVP)")
    logger.info("=" * 60)
    logger.info("Konfigürasyon:")
    scan_mode = getattr(config, 'SCAN_MODE', 'continuous')
    logger.info(f"  - Tarama modu: {scan_mode}")
    if scan_mode == 'hybrid':
        logger.info(f"  - İntraday aralığı: {getattr(config, 'INTRADAY_SCAN_INTERVAL', 900) // 60} dakika")
        logger.info(f"  - Günlük yenileme: {getattr(config, 'DAILY_DATA_REFRESH_TIMES', [])}")
    else:
        logger.info(f"  - Tarama aralığı: {config.SCAN_INTERVAL_SECONDS}s")
    logger.info(f"  - Min. hacim: {config.MIN_DAILY_TL_VOLUME/1e6:.1f}M TL")
    logger.info(f"  - Fiyat bandı: {config.MIN_PRICE}-{config.MAX_PRICE} TL")
    logger.info(f"  - STRONG_BUY barajı: {config.STRONG_BUY_THRESHOLD}")
    logger.info(f"  - ULTRA_BUY barajı: {config.ULTRA_BUY_THRESHOLD}")
    logger.info(f"  - Cooldown: {config.SIGNAL_COOLDOWN_MINUTES} dakika")
    logger.info(f"  - Dry-run modu: {'AÇIK' if config.DRY_RUN_MODE else 'KAPALI'}")
    
    # Veri gecikmesi uyarısı
    if config.DATA_DELAY_ENABLED:
        logger.warning("=" * 60)
        logger.warning(f"⏱️  VERİ GECİKMESİ MODU: {config.DATA_DELAY_MINUTES} dakika")
        logger.warning(f"   {config.DATA_DELAY_WARNING_TEXT}")
        logger.warning("   Swing trading için uygundur, day trading için DEĞİLDİR.")
        logger.warning("=" * 60)
    
    logger.info("=" * 60)
    
    # Bot instance
    bot = BISTTradingBot()
    
    # Signal handler'ları kur (graceful shutdown)
    def signal_handler(signum, frame):
        logger.info(f"Signal {signum} alındı")
        bot.request_shutdown()
    
    # Windows'ta SIGTERM yok, sadece SIGINT
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Bot'u başlat
        await bot.initialize()
        
        # Provider durumunu logla
        if bot.provider_manager:
            stats = bot.provider_manager.get_stats()
            logger.info(f"📡 Aktif provider sayısı: {stats.get('active_providers', 0)}")
            logger.info(f"📊 İntraday öncelik: {stats.get('priority_intraday', [])}")
            logger.info(f"📊 Günlük öncelik: {stats.get('priority_daily', [])}")
        
        # Telegram bağlantı testi
        if not config.DRY_RUN_MODE:
            logger.info("📱 Telegram bağlantısı test ediliyor...")
            if bot.telegram_notifier.test_connection():
                logger.info("✅ Telegram bağlantısı başarılı")
                
                # Başlangıç mesajı gönder
                logger.info("📤 Başlangıç mesajı gönderiliyor...")
                bot.telegram_notifier.send_startup_message()
            else:
                logger.error("❌ Telegram bağlantısı başarısız!")
                # Kullanıcıya sor (interaktif mod)
                try:
                    if sys.stdin.isatty():
                        if input("Devam edilsin mi? (y/n): ").lower() != 'y':
                            return
                except:
                    pass  # Non-interactive modda devam et
        
        # 🔍 DEBUG: İlk birkaç sembol için detaylı test
        logger.info("🔍 DEBUG: Örnek semboller test ediliyor...")
        await bot.debug_single_symbol_scan("GARAN")
        await bot.debug_single_symbol_scan("THYAO")
        
        # 🆕 Bot başlarken günlük analiz yap ve rapor gönder
        logger.info("📊 Başlangıç analizi yapılıyor...")
        await bot.run_startup_analysis()
        
        # Scheduler'ı başlat
        await bot.run_scheduler()
        
    except asyncio.CancelledError:
        logger.info("Ana görev iptal edildi")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        try:
            bot.telegram_notifier.send_error_alert(f"🚨 Bot crashed: {e}")
        except:
            pass
        raise
    finally:
        # Shutdown mesajı gönder (dry-run değilse)
        if not config.DRY_RUN_MODE:
            try:
                bot.telegram_notifier.send_shutdown_message()
            except:
                pass
        
        # Graceful shutdown
        await bot.shutdown()
        bot.print_stats()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Görüşürüz!")