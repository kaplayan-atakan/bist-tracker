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
from datetime import datetime, time as datetime_time
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
            ohlcv = await self.provider_manager.get_ohlcv_daily(symbol, limit=config.HISTORICAL_DAYS)
            
            if ohlcv is None or ohlcv.empty:
                logger.warning(f"{symbol}: OHLCV verisi alınamadı")
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
    
    async def scan_all_symbols(self):
        """Tüm sembolleri tarar ve sinyal üretir"""
        try:
            logger.info("=" * 60)
            logger.info(f"🔍 YENİ TARAMA BAŞLIYOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)
            
            self.stats['total_scans'] += 1
            
            # Piyasa kontrolü
            if not self.is_market_open():
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
    
    async def run_scheduler(self):
        """Zamanlayıcı - belirli aralıklarla tarama yapar"""
        logger.info(f"⏰ Zamanlayıcı başlatıldı (interval: {config.SCAN_INTERVAL_SECONDS}s)")
        
        while not self._shutdown_requested:
            try:
                await self.scan_all_symbols()
                
                # Sonraki taramaya kadar bekle
                if not self._shutdown_requested:
                    # Piyasa kapalıysa daha uzun bekle
                    if self.is_market_open():
                        wait_time = config.SCAN_INTERVAL_SECONDS
                    else:
                        wait_time = 300  # Piyasa kapalıyken 5 dakikada bir kontrol
                        logger.info(f"📅 Piyasa kapalı, {wait_time}s sonra kontrol edilecek")
                    
                    logger.info(f"😴 {wait_time} saniye bekleniyor...")
                    
                    # Bekleme süresini küçük parçalara böl (shutdown için)
                    for _ in range(wait_time):
                        if self._shutdown_requested:
                            break
                        await asyncio.sleep(1)
                
                # Periyodik temizlik
                if self.stats['total_scans'] % 10 == 0:
                    self.cooldown_manager.cleanup_old_entries()
                
            except asyncio.CancelledError:
                logger.info("⏹️  Scheduler iptal edildi")
                break
            except Exception as e:
                logger.error(f"Scheduler hatası: {str(e)}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(60)  # Hata durumunda 1 dakika bekle
    
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