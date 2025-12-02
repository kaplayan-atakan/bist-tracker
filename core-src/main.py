"""
BİST Trading Bot - Main Module
Ana çalıştırma ve zamanlama modülü

MVP Sprint: Provider katmanı entegrasyonu tamamlandı.
- ProviderManager ile veri çekme
- Async-native tarama döngüsü
- Graceful shutdown (SIGINT/SIGTERM)
- 15 dakika veri gecikmesi uyarısı

VERİ GECİKMESİ:
TradingView anonim kullanımda veriler 15 dakika gecikmelidir (delayed_streaming_900).
Bu, swing trading için kabul edilebilir; day trading için uygun DEĞİLDİR.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, time as datetime_time, timedelta
from typing import List, Dict, Optional
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
from filters import apply_all_filters
from cooldown_manager import get_cooldown_manager
from telegram_notifier import get_telegram_notifier


# Logging yapılandırması
def setup_logging():
    """Logging sistemini yapılandırır"""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


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
        Piyasa açık mı kontrol eder
        
        Returns:
            bool: Piyasa açık mı?
        """
        now = datetime.now()
        current_time = now.time()
        
        # Hafta sonu kontrolü
        if now.weekday() >= 5:  # Cumartesi=5, Pazar=6
            return False
        
        # Saat kontrolü
        market_open = datetime_time(config.MARKET_OPEN_HOUR, 0)
        market_close = datetime_time(config.MARKET_CLOSE_HOUR, 0)
        
        return market_open <= current_time <= market_close
    
    def is_market_opening(self) -> bool:
        """
        Piyasa açılış saati mi kontrol eder (10:00-10:05 arası)
        
        Returns:
            bool: Açılış saati mi?
        """
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        
        current_time = now.time()
        market_open_start = datetime_time(config.MARKET_OPEN_HOUR, 0)
        market_open_end = datetime_time(config.MARKET_OPEN_HOUR, 5)  # İlk 5 dakika
        
        return market_open_start <= current_time <= market_open_end
    
    def is_market_closing(self) -> bool:
        """
        Piyasa kapanış saati mi kontrol eder (17:55-18:05 arası)
        
        Returns:
            bool: Kapanış saati mi?
        """
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        
        current_time = now.time()
        # Kapanıştan 5 dakika önce - 5 dakika sonra
        close_start = datetime_time(config.MARKET_CLOSE_HOUR - 1, 55)
        close_end = datetime_time(config.MARKET_CLOSE_HOUR, 5)
        
        return close_start <= current_time <= close_end
    
    def _record_successful_data_fetch(self):
        """Başarılı veri çekme zamanını kaydet"""
        self._last_successful_data_time = datetime.now()
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
        
        time_since_last_data = datetime.now() - self._last_successful_data_time
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
        today = datetime.now().date()
        
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
        
        self._last_market_open_report = datetime.now()
    
    async def send_market_close_report(self):
        """Piyasa kapanışında veri akışı raporu gönder"""
        today = datetime.now().date()
        
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
        
        self._last_market_close_report = datetime.now()
    
    async def scan_all_symbols(self, is_startup: bool = False):
        """
        Tüm sembolleri tarar ve sinyal üretir.
        
        Args:
            is_startup: Bot başlangıcında mı çağrılıyor (piyasa kontrolü atlanır)
        """
        try:
            scan_type = "BAŞLANGIÇ" if is_startup else "YENİ"
            logger.info("=" * 60)
            logger.info(f"🔍 {scan_type} TARAMA BAŞLIYOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
        
        today = datetime.now().date()
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
        
        today = datetime.now().date()
        if self._last_close_scan and self._last_close_scan.date() == today:
            return False
        
        return True
    
    async def run_startup_analysis(self):
        """
        Bot başlarken günlük analiz raporu gönderir.
        Piyasa durumundan bağımsız olarak çalışır.
        """
        if self._startup_scan_done:
            return
        
        logger.info("="*60)
        logger.info("🚀 BAŞLANGIÇ ANALİZİ")
        logger.info("="*60)
        
        # Provider sağlık durumlarını güncelle
        await self.provider_manager.update_all_health()
        
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
        """
        scan_mode = getattr(config, 'SCAN_MODE', 'continuous')
        check_interval = getattr(config, 'MARKET_CHECK_INTERVAL', 60)
        
        logger.info(f"⏰ Zamanlayıcı başlatıldı (mod: {scan_mode})")
        
        if scan_mode == 'open_close':
            logger.info("📅 Açılış + Kapanış modu aktif (günde 2 tarama)")
        else:
            logger.info(f"🔄 Sürekli tarama modu (her {config.SCAN_INTERVAL_SECONDS}s)")
        
        while not self._shutdown_requested:
            try:
                if scan_mode == 'open_close':
                    # ===== AÇILIŞ + KAPANIŞ MODU =====
                    
                    # Açılış taraması
                    if self.should_scan_at_open():
                        logger.info("🌅 Piyasa açılışı - tarama başlatılıyor...")
                        await self.send_market_open_report()
                        await self.scan_all_symbols()
                        self._last_open_scan = datetime.now()
                        logger.info("✅ Açılış taraması tamamlandı")
                    
                    # Kapanış taraması
                    elif self.should_scan_at_close():
                        logger.info("🌇 Piyasa kapanışı - tarama başlatılıyor...")
                        await self.scan_all_symbols()
                        await self.send_market_close_report()
                        self._last_close_scan = datetime.now()
                        logger.info("✅ Kapanış taraması tamamlandı")
                    
                    # Bekleme
                    wait_time = check_interval
                    now = datetime.now()
                    
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
        
        print("=" * 60 + "\n")


async def main():
    """Ana async fonksiyon"""
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("🚀 BİST TRADING BOT v2.0 (MVP)")
    logger.info("=" * 60)
    logger.info("Konfigürasyon:")
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