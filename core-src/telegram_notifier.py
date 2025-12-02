"""
BİST Trading Bot - Telegram Notifier Module
Telegram'a formatlanmış sinyal mesajları gönderir

MVP Sprint: Veri gecikmesi uyarısı eklendi.
"""

import requests
from datetime import datetime
from typing import Dict
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
            message = "🚀 *BİST Trading Bot v2.0 (MVP) Başlatıldı!*\n\n"
            message += f"⏰ *Zaman:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += f"📊 *Tarama Aralığı:* {config.SCAN_INTERVAL_SECONDS} saniye\n"
            message += f"💰 *Min. Hacim:* {config.MIN_DAILY_TL_VOLUME/1e6:.1f}M TL\n"
            message += f"📈 *STRONG\\_BUY Barajı:* {config.STRONG_BUY_THRESHOLD}/20\n"
            message += f"🔥 *ULTRA\\_BUY Barajı:* {config.ULTRA_BUY_THRESHOLD}/20\n"
            message += f"⏱ *Cooldown:* {config.SIGNAL_COOLDOWN_MINUTES} dakika\n\n"
            
            # Veri gecikmesi uyarısı
            if getattr(config, 'DATA_DELAY_ENABLED', False):
                delay_text = getattr(config, 'DATA_DELAY_WARNING_TEXT', '')
                message += f"⚠️ {delay_text}\n\n"
            
            message += "_Bot aktif ve taramaya hazır!_ ✅"
            
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