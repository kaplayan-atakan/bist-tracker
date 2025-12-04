"""
BİST Trading Bot - Telegram Notifier Module
Telegram'a formatlanmış sinyal mesajları gönderir

MVP Sprint: Veri gecikmesi uyarısı eklendi.
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram bildirim sınıfı"""
    
    def __init__(self, dry_run: bool = None):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # dry_run parametresi geçilmişse kullan, yoksa config'den al
        self.dry_run = dry_run if dry_run is not None else config.DRY_RUN_MODE
        
        # İstatistikler
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0
        }
    
    def format_signal_message(self, signal: Dict, daily_stats: Dict) -> str:
        """
        Sinyal mesajını formatlar
        
        Args:
            signal: Sinyal verisi (scoring.py'den dönen)
            daily_stats: Günlük istatistikler
            
        Returns:
            str: Formatlanmış mesaj
        """
        try:
            symbol = signal['symbol']
            signal_level = signal['signal_level']
            total_score = signal['total_score']
            max_score = signal['max_possible_score']
            
            trend_score = signal['trend_score']
            momentum_score = signal['momentum_score']
            volume_score = signal['volume_score']
            fundamental_pa_score = signal['fundamental_pa_score']
            
            current_price = daily_stats.get('current_price', 0)
            daily_change = daily_stats.get('daily_change_percent', 0)
            daily_volume_tl = daily_stats.get('daily_volume_tl', 0)
            
            # Sinyal emoji
            if signal_level == 'ULTRA_BUY':
                emoji = '🔥🚀'
            elif signal_level == 'STRONG_BUY':
                emoji = '📈💪'
            elif signal_level == 'WATCHLIST':
                emoji = '👀📊'
            else:
                emoji = '📌'
            
            # Günlük değişim emoji
            change_emoji = '🟢' if daily_change >= 0 else '🔴'
            
            # Mesaj başlığı
            message = f"{emoji} *{signal_level}* - *{symbol}*\n\n"
            
            # Fiyat ve hacim bilgileri
            message += f"💰 *Fiyat:* {current_price:.2f} TL | {change_emoji} Günlük: {daily_change:+.2f}%\n"
            message += f"📊 *Hacim:* {daily_volume_tl/1e6:.2f} milyon TL\n\n"
            
            # Skorlar
            message += f"🎯 *Skorlar:*\n"
            message += f"├─ Trend: {trend_score}/{config.MAX_TREND_SCORE}\n"
            message += f"├─ Momentum: {momentum_score}/{config.MAX_MOMENTUM_SCORE}\n"
            message += f"├─ Hacim: {volume_score}/{config.MAX_VOLUME_SCORE}\n"
            message += f"├─ Temel/PA: {fundamental_pa_score}/{config.MAX_FUNDAMENTAL_PA_SCORE}\n"
            message += f"└─ *TOPLAM: {total_score}/{max_score}*\n\n"
            
            # Tetiklenen kriterler
            triggered_criteria = signal.get('triggered_criteria', [])
            if triggered_criteria:
                message += f"🔍 *Öne çıkan kriterler:*\n"
                for i, criterion in enumerate(triggered_criteria[:8], 1):  # İlk 8 kriter
                    message += f"{i}. {criterion}\n"
                
                if len(triggered_criteria) > 8:
                    message += f"... ve {len(triggered_criteria) - 8} kriter daha\n"
                message += "\n"
            
            # Zaman damgası
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            message += f"⏱ *Zaman:* {timestamp}\n"
            
            # Veri gecikmesi uyarısı (config'den)
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                delay_text = getattr(config, 'DATA_DELAY_WARNING_TEXT', '')
                if delay_text:
                    message += f"\n{delay_text}\n"
            
            # Uyarı
            message += f"\n⚠️ _Bu bir yatırım tavsiyesi değildir. Kendi analizinizi yapın._"
            
            return message
            
        except Exception as e:
            logger.error(f"Mesaj formatlama hatası: {str(e)}")
            return f"Hata: {symbol} için mesaj formatlanamadı"
    
    def send_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """
        Telegram'a mesaj gönderir
        
        Args:
            message: Gönderilecek mesaj
            parse_mode: Mesaj formatı ('Markdown' veya 'HTML')
            
        Returns:
            bool: Başarılı mı?
        """
        # Dry-run modu kontrolü (instance veya config)
        if self.dry_run:
            logger.info("🔇 DRY-RUN MODE: Mesaj gönderilmedi (sadece log)")
            logger.info(f"Mesaj içeriği:\n{message}")
            return True
        
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                self.stats['messages_sent'] += 1
                logger.info(f"✅ Telegram mesajı gönderildi")
                return True
            else:
                self.stats['messages_failed'] += 1
                logger.error(f"❌ Telegram mesaj hatası: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            self.stats['messages_failed'] += 1
            logger.error("❌ Telegram timeout hatası")
            return False
        except Exception as e:
            self.stats['messages_failed'] += 1
            logger.error(f"❌ Telegram gönderim hatası: {str(e)}")
            return False
    
    def send_signal_message(self, signal: Dict, daily_stats: Dict) -> bool:
        """
        Sinyal mesajı formatlar ve gönderir
        
        Args:
            signal: Sinyal verisi
            daily_stats: Günlük istatistikler
            
        Returns:
            bool: Başarılı mı?
        """
        message = self.format_signal_message(signal, daily_stats)
        return self.send_message(message)
    
    def send_error_alert(self, error_message: str):
        """
        Hata uyarısı gönderir
        
        Args:
            error_message: Hata mesajı
        """
        message = f"⚠️ *BOT HATASI*\n\n{error_message}\n\n_Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        self.send_message(message)
    
    def send_daily_summary(self, summary: Dict):
        """
        Günlük özet raporu gönderir
        
        Args:
            summary: Özet bilgileri
        """
        try:
            message = "📊 *GÜNLÜK ÖZET*\n\n"
            message += f"🔍 Taranan sembol: {summary.get('symbols_scanned', 0)}\n"
            message += f"📈 Sinyal üretilen: {summary.get('signals_generated', 0)}\n"
            message += f"✅ Gönderilen: {summary.get('signals_sent', 0)}\n"
            message += f"🕐 Cooldown'da: {summary.get('signals_blocked', 0)}\n\n"
            
            top_signals = summary.get('top_signals', [])
            if top_signals:
                message += "*En yüksek skorlu hisseler:*\n"
                for i, signal in enumerate(top_signals[:5], 1):
                    message += f"{i}. {signal['symbol']} - {signal['score']} puan\n"
            
            message += f"\n_Tarih: {datetime.now().strftime('%Y-%m-%d')}_"
            
            # Veri gecikmesi uyarısı
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                delay_text = getattr(config, 'DATA_DELAY_WARNING_TEXT', '')
                if delay_text:
                    message += f"\n\n{delay_text}"
            
            self.send_message(message)
            
        except Exception as e:
            logger.error(f"Özet gönderimi hatası: {str(e)}")
    
    def test_connection(self) -> bool:
        """
        Telegram bağlantısını test eder
        
        Returns:
            bool: Bağlantı başarılı mı?
        """
        try:
            message = "🤖 BİST Trading Bot test mesajı\n\nBağlantı başarılı! ✅"
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Telegram test hatası: {str(e)}")
            return False
    
    def send_startup_message(self) -> bool:
        """
        Bot başlatıldığında bildirim gönderir
        
        Returns:
            bool: Başarılı mı?
        """
        try:
            message = "🚀 *BİST Trading Bot (MVP) Başlatıldı!*\n\n"
            message += f"⏰ *Zaman:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # Tarama modu
            scan_mode = getattr(config, 'SCAN_MODE', 'continuous')
            if scan_mode == 'open_close':
                message += f"📅 *Tarama Modu:* Açılış + Kapanış (günde 2x)\n"
            else:
                message += f"🔄 *Tarama Modu:* Sürekli ({config.SCAN_INTERVAL_SECONDS}s aralıklarla)\n"
            
            message += f"💰 *Min. Hacim:* {config.MIN_DAILY_TL_VOLUME/1e6:.1f}M TL\n"
            message += f"📈 *STRONG\\_BUY Barajı:* {config.STRONG_BUY_THRESHOLD}/20\n"
            message += f"🔥 *ULTRA\\_BUY Barajı:* {config.ULTRA_BUY_THRESHOLD}/20\n"
            message += f"⏱ *Cooldown:* {config.SIGNAL_COOLDOWN_MINUTES} dakika\n\n"
            
            # Veri gecikmesi uyarısı
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                delay_text = getattr(config, 'DATA_DELAY_WARNING_TEXT', '')
                message += f"⚠️ {delay_text}\n\n"
            
            message += "_Bot aktif! Başlangıç analizi yapılacak..._"
            
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Startup mesajı gönderme hatası: {str(e)}")
            return False
    
    def send_shutdown_message(self) -> bool:
        """
        Bot kapanırken bildirim gönderir
        
        Returns:
            bool: Başarılı mı?
        """
        try:
            message = "🛑 *BİST Trading Bot Kapatıldı*\n\n"
            message += f"⏰ *Zaman:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += f"📊 *Gönderilen Mesaj:* {self.stats['messages_sent']}\n"
            message += f"❌ *Başarısız:* {self.stats['messages_failed']}\n\n"
            message += "_Bot durduruldu._"
            
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Shutdown mesajı gönderme hatası: {str(e)}")
            return False
    
    def send_data_outage_alert(
        self,
        last_data_time: Optional[datetime],
        outage_duration: timedelta
    ) -> bool:
        """
        Uzun süreli veri kesintisi uyarısı gönderir
        
        Args:
            last_data_time: Son başarılı veri zamanı
            outage_duration: Kesinti süresi
            
        Returns:
            bool: Başarılı mı?
        """
        try:
            days = outage_duration.days
            hours = outage_duration.seconds // 3600
            
            message = "🚨 *KRİTİK: VERİ KESİNTİSİ UYARISI* 🚨\n\n"
            message += f"⚠️ *{days} gün {hours} saattir veri alınamıyor!*\n\n"
            
            if last_data_time:
                message += f"📍 *Son Başarılı Veri:* {last_data_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            else:
                message += "📍 *Son Başarılı Veri:* Hiç alınamadı\n"
            
            message += f"📍 *Şu An:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            message += "*Olası Nedenler:*\n"
            message += "• Provider API kesintisi\n"
            message += "• Internet bağlantı sorunu\n"
            message += "• Rate limit aşımı\n"
            message += "• API anahtarı geçersiz\n\n"
            message += "🔧 _Lütfen server ve provider durumunu kontrol edin._"
            
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Veri kesintisi uyarısı gönderme hatası: {str(e)}")
            return False
    
    def send_market_open_report(
        self,
        provider_health: Dict[str, str],
        last_data_time: Optional[datetime],
        stats: Dict
    ) -> bool:
        """
        Piyasa açılışında veri akışı raporu gönderir
        
        Args:
            provider_health: Provider sağlık durumları
            last_data_time: Son başarılı veri zamanı
            stats: Bot istatistikleri
            
        Returns:
            bool: Başarılı mı?
        """
        try:
            message = "🌅 *PİYASA AÇILIŞ RAPORU*\n\n"
            message += f"⏰ *Tarih:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # Provider sağlık durumları
            message += "📡 *Provider Durumları:*\n"
            health_emojis = {
                'healthy': '✅',
                'degraded': '⚠️',
                'down': '❌',
                'unknown': '❓'
            }
            
            for provider, status in provider_health.items():
                emoji = health_emojis.get(status, '❓')
                # Provider isimlerini formatla
                provider_name = provider.replace('_', ' ').title()
                message += f"  {emoji} {provider_name}: {status.upper()}\n"
            
            message += "\n"
            
            # Son veri zamanı
            if last_data_time:
                time_diff = datetime.now() - last_data_time
                hours_ago = time_diff.total_seconds() / 3600
                
                if hours_ago < 1:
                    time_str = f"{int(time_diff.total_seconds() / 60)} dakika önce"
                elif hours_ago < 24:
                    time_str = f"{int(hours_ago)} saat önce"
                else:
                    time_str = f"{time_diff.days} gün {int(hours_ago % 24)} saat önce"
                
                message += f"📊 *Son Veri:* {time_str}\n"
            else:
                message += "📊 *Son Veri:* Henüz veri çekilmedi\n"
            
            # Bot istatistikleri
            message += f"🔍 *Toplam Tarama:* {stats.get('total_scans', 0)}\n"
            message += f"📨 *Gönderilen Sinyal:* {stats.get('total_signals_sent', 0)}\n\n"
            
            # Veri gecikmesi uyarısı
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                message += f"⏱️ _Veriler {config.DATA_DELAY_MINUTES} dk gecikmelidir_\n\n"
            
            message += "_Bot aktif ve taramaya hazır!_ ✅"
            
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Piyasa açılış raporu gönderme hatası: {str(e)}")
            return False
    
    def send_market_close_report(
        self,
        provider_stats: Dict,
        bot_stats: Dict,
        last_data_time: Optional[datetime]
    ) -> bool:
        """
        Piyasa kapanışında veri akışı raporu gönderir
        
        Args:
            provider_stats: Provider istatistikleri
            bot_stats: Bot istatistikleri
            last_data_time: Son başarılı veri zamanı
            
        Returns:
            bool: Başarılı mı?
        """
        try:
            message = "🌇 *PİYASA KAPANIŞ RAPORU*\n\n"
            message += f"⏰ *Tarih:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # Günün özeti
            message += "📊 *GÜNÜN ÖZETİ:*\n"
            message += f"  🔍 Toplam Tarama: {bot_stats.get('total_scans', 0)}\n"
            message += f"  📈 Analiz Edilen: {bot_stats.get('total_symbols_analyzed', 0)}\n"
            message += f"  📩 Üretilen Sinyal: {bot_stats.get('total_signals_generated', 0)}\n"
            message += f"  ✅ Gönderilen: {bot_stats.get('total_signals_sent', 0)}\n"
            message += f"  ❌ Hatalar: {bot_stats.get('errors', 0)}\n\n"
            
            # Provider istatistikleri
            message += "📡 *PROVIDER İSTATİSTİKLERİ:*\n"
            message += f"  📞 Toplam İstek: {provider_stats.get('total_requests', 0)}\n"
            message += f"  ✅ Başarılı: {provider_stats.get('successful_requests', 0)}\n"
            message += f"  🔄 Failover: {provider_stats.get('failover_count', 0)}\n\n"
            
            # Provider sağlıkları
            health = provider_stats.get('health', {})
            if health:
                message += "🟢 *Provider Durumları:*\n"
                health_emojis = {
                    'healthy': '✅',
                    'degraded': '⚠️',
                    'down': '❌',
                    'unknown': '❓'
                }
                for provider, status in health.items():
                    emoji = health_emojis.get(status, '❓')
                    provider_name = provider.replace('_', ' ').title()
                    message += f"  {emoji} {provider_name}: {status.upper()}\n"
                message += "\n"
            
            # Son veri zamanı
            if last_data_time:
                message += f"📍 *Son Veri:* {last_data_time.strftime('%H:%M:%S')}\n\n"
            
            # Başarı oranı
            total_req = provider_stats.get('total_requests', 0)
            success_req = provider_stats.get('successful_requests', 0)
            if total_req > 0:
                success_rate = (success_req / total_req) * 100
                rate_emoji = '🟢' if success_rate >= 90 else '🟡' if success_rate >= 70 else '🔴'
                message += f"{rate_emoji} *Başarı Oranı:* {success_rate:.1f}%\n\n"
            
            message += "_Görüşmek üzere, yarın sabah açılışta!_ 👋"
            
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Piyasa kapanış raporu gönderme hatası: {str(e)}")
            return False
    
    def send_status_report(
        self,
        market_open: bool,
        next_open_time: str,
        provider_health: Dict[str, str],
        symbol_count: int,
        bot_version: str = "2.0",
        last_data_time: Optional[datetime] = None
    ) -> bool:
        """
        Piyasa kapalıyken durum raporu gönderir.
        
        Bot başlatıldığında piyasa kapalıysa bu rapor gönderilir.
        
        Args:
            market_open: Piyasa açık mı
            next_open_time: Sonraki açılış zamanı (örn: "Pazartesi 10:00")
            provider_health: Provider sağlık durumları
            symbol_count: Takip edilen sembol sayısı
            bot_version: Bot versiyonu
            last_data_time: Son başarılı veri zamanı
            
        Returns:
            bool: Başarılı mı?
        """
        try:
            message = "📊 *BİST Trading Bot - Durum Raporu*\n\n"
            message += f"⏰ *Zaman:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # Piyasa durumu
            if market_open:
                message += "🟢 *Piyasa Durumu:* AÇIK\n"
            else:
                message += "🔴 *Piyasa Durumu:* KAPALI\n"
                message += f"📅 *Sonraki Açılış:* {next_open_time}\n"
            
            message += "\n"
            
            # Provider durumları
            message += "📡 *Veri Kaynakları:*\n"
            health_emojis = {
                'healthy': '✅',
                'degraded': '⚠️',
                'down': '❌',
                'unknown': '❓'
            }
            
            # Provider isimlerini düzenle
            provider_names = {
                'tradingview_http': 'TradingView HTTP',
                'tradingview_ws': 'TradingView WS',
                'yahoo': 'Yahoo Finance',
                'finnhub': 'Finnhub',
            }
            
            for provider, status in provider_health.items():
                emoji = health_emojis.get(status, '❓')
                name = provider_names.get(provider, provider.replace('_', ' ').title())
                status_text = "Aktif" if status == 'healthy' else "Bağlı" if status == 'degraded' else "Kapalı" if status == 'down' else "Bilinmiyor"
                message += f"  • {name}: {emoji} {status_text}\n"
            
            message += "\n"
            
            # Sembol sayısı
            message += f"📈 *Takip:* {symbol_count} sembol\n"
            
            # Veri gecikmesi
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                delay_minutes = getattr(config, 'DATA_DELAY_MINUTES', 15)
                message += f"⏱️ *Veri Gecikmesi:* {delay_minutes} dakika (TradingView free tier)\n"
            
            # Son veri zamanı
            if last_data_time:
                time_diff = datetime.now() - last_data_time
                if time_diff.total_seconds() < 3600:
                    time_str = f"{int(time_diff.total_seconds() / 60)} dakika önce"
                elif time_diff.total_seconds() < 86400:
                    time_str = f"{int(time_diff.total_seconds() / 3600)} saat önce"
                else:
                    time_str = f"{time_diff.days} gün önce"
                message += f"📊 *Son Veri:* {time_str}\n"
            
            message += f"\n_Bot v{bot_version} hazır, piyasa açılışını bekliyor..._ ⏳"
            
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Durum raporu gönderme hatası: {str(e)}")
            return False
    
    def send_scan_summary(
        self,
        total_scanned: int,
        signals_generated: int,
        top_results: list
    ) -> bool:
        """
        Tarama özeti mesajı gönderir.
        Her taramadan sonra en iyi 5 hisse ve skorlarını gösterir.
        
        Args:
            total_scanned: Toplam taranan sembol sayısı
            signals_generated: Üretilen sinyal sayısı
            top_results: En yüksek skorlu sonuçlar listesi
            
        Returns:
            bool: Başarılı mı?
        """
        try:
            message = "📊 *TARAMA ÖZETİ*\n\n"
            message += f"⏰ *Zaman:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += f"🔍 *Taranan:* {total_scanned} sembol\n"
            message += f"📈 *Sinyal:* {signals_generated} hisse\n\n"
            
            if not top_results:
                message += "_Skor alan hisse bulunamadı._"
            else:
                message += "🏆 *En Yüksek Skorlu 5 Hisse:*\n"
                message += "```\n"
                message += f"{'#':<3} {'Sembol':<8} {'Skor':>6} {'T':>3} {'M':>3} {'H':>3} {'P':>3}\n"
                message += "-" * 35 + "\n"
                
                for i, result in enumerate(top_results, 1):
                    symbol = result['symbol']
                    signal = result['signal']
                    
                    total_score = signal.get('total_score', 0)
                    max_score = signal.get('max_possible_score', 20)
                    trend_score = signal.get('trend_score', 0)
                    momentum_score = signal.get('momentum_score', 0)
                    volume_score = signal.get('volume_score', 0)
                    fundamental_pa_score = signal.get('fundamental_pa_score', 0)
                    signal_level = signal.get('signal_level', '')
                    
                    # Sinyal seviyesi işareti
                    level_mark = '🔥' if signal_level == 'ULTRA_BUY' else '📈' if signal_level == 'STRONG_BUY' else '👀' if signal_level == 'WATCHLIST' else ''
                    
                    message += f"{i:<3} {symbol:<8} {total_score:>2}/{max_score:<2}  {trend_score:>2}  {momentum_score:>2}  {volume_score:>2}  {fundamental_pa_score:>2}\n"
                
                message += "```\n"
                message += "_T=Trend, M=Momentum, H=Hacim, P=Temel/PA_\n\n"
                
                # En yüksek skorlu hissenin detayları
                top_result = top_results[0]
                top_signal = top_result['signal']
                top_symbol = top_result['symbol']
                top_daily = top_result.get('daily_stats', {})
                
                top_level = top_signal.get('signal_level', 'NO_SIGNAL')
                level_emoji = '🔥' if top_level == 'ULTRA_BUY' else '📈' if top_level == 'STRONG_BUY' else '👀' if top_level == 'WATCHLIST' else '⚪'
                
                message += f"{level_emoji} *En Yüksek: {top_symbol}*\n"
                
                current_price = top_daily.get('current_price', 0)
                daily_change = top_daily.get('daily_change_percent', 0)
                change_emoji = '🟢' if daily_change >= 0 else '🔴'
                
                message += f"💰 Fiyat: {current_price:.2f} TL | {change_emoji} {daily_change:+.2f}%\n\n"
                
                # Tetiklenen kriterler (ilk 3)
                triggered = top_signal.get('triggered_criteria', [])
                if triggered:
                    message += "*Öne Çıkan Kriterler:*\n"
                    for j, criterion in enumerate(triggered[:3], 1):
                        message += f"{j}. {criterion}\n"
                    if len(triggered) > 3:
                        message += f"_... ve {len(triggered) - 3} kriter daha_\n"
            
            # Veri gecikmesi uyarısı
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                message += f"\n⏱️ _Veriler {config.DATA_DELAY_MINUTES} dk gecikmelidir_"
            
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Tarama özeti gönderme hatası: {str(e)}")
            return False
    
    def get_stats(self) -> Dict:
        """İstatistikleri döndürür"""
        return {
            'messages_sent': self.stats['messages_sent'],
            'messages_failed': self.stats['messages_failed'],
            'success_rate': (
                self.stats['messages_sent'] / (self.stats['messages_sent'] + self.stats['messages_failed'])
                if (self.stats['messages_sent'] + self.stats['messages_failed']) > 0
                else 0
            ) * 100
        }


# Singleton instance
_telegram_notifier_instance = None

def get_telegram_notifier() -> TelegramNotifier:
    """TelegramNotifier singleton instance döndürür"""
    global _telegram_notifier_instance
    if _telegram_notifier_instance is None:
        _telegram_notifier_instance = TelegramNotifier()
    return _telegram_notifier_instance