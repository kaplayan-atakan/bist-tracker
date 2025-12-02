"""
BİST Trading Bot - Cooldown Manager Module
Aynı hisse için tekrarlayan sinyal spam'ini önler
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

import config

logger = logging.getLogger(__name__)


class CooldownManager:
    """Sinyal cooldown yönetimi"""
    
    def __init__(self):
        # symbol -> son sinyal zamanı (timestamp)
        self.last_signal_time: Dict[str, float] = {}
        
        # symbol -> son sinyal seviyesi
        self.last_signal_level: Dict[str, str] = {}
        
        # İstatistikler
        self.stats = {
            'total_signals_sent': 0,
            'signals_blocked_by_cooldown': 0
        }
    
    def can_send_signal(self, symbol: str, signal_level: str = None) -> bool:
        """
        Sembol için sinyal gönderilip gönderilemeyeceğini kontrol eder
        
        Args:
            symbol: Hisse sembolü
            signal_level: Sinyal seviyesi (opsiyonel)
            
        Returns:
            bool: Sinyal gönderilebilir mi?
        """
        current_time = time.time()
        
        # İlk kez sinyal gönderiliyorsa
        if symbol not in self.last_signal_time:
            return True
        
        # Son sinyal zamanı
        last_time = self.last_signal_time[symbol]
        time_elapsed = (current_time - last_time) / 60  # dakika cinsine çevir
        
        # Cooldown süresi geçti mi?
        if time_elapsed >= config.SIGNAL_COOLDOWN_MINUTES:
            return True
        
        # Sinyal seviyesi yükseliyorsa izin ver
        # Örn: WATCHLIST'ten STRONG_BUY'a geçiş
        if signal_level:
            last_level = self.last_signal_level.get(symbol)
            if last_level and self._is_upgrade(last_level, signal_level):
                logger.info(f"{symbol} için sinyal yükseltme: {last_level} -> {signal_level}")
                return True
        
        # Cooldown aktif
        remaining = config.SIGNAL_COOLDOWN_MINUTES - time_elapsed
        logger.debug(f"{symbol} cooldown aktif: {remaining:.1f} dakika kaldı")
        self.stats['signals_blocked_by_cooldown'] += 1
        return False
    
    def _is_upgrade(self, old_level: str, new_level: str) -> bool:
        """
        Yeni sinyal seviyesi eskisinden daha güçlü mü?
        
        Args:
            old_level: Eski sinyal seviyesi
            new_level: Yeni sinyal seviyesi
            
        Returns:
            bool: Yükseltme mi?
        """
        level_hierarchy = {
            'NO_SIGNAL': 0,
            'WATCHLIST': 1,
            'STRONG_BUY': 2,
            'ULTRA_BUY': 3
        }
        
        old_rank = level_hierarchy.get(old_level, 0)
        new_rank = level_hierarchy.get(new_level, 0)
        
        return new_rank > old_rank
    
    def register_signal(self, symbol: str, signal_level: str = None):
        """
        Sinyal gönderildiğini kaydet
        
        Args:
            symbol: Hisse sembolü
            signal_level: Sinyal seviyesi
        """
        self.last_signal_time[symbol] = time.time()
        
        if signal_level:
            self.last_signal_level[symbol] = signal_level
        
        self.stats['total_signals_sent'] += 1
        
        logger.info(f"{symbol} için sinyal kaydedildi: {signal_level}")
    
    def get_cooldown_status(self, symbol: str) -> Optional[Dict]:
        """
        Sembol için cooldown durumunu döndürür
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            dict: Cooldown durumu veya None
        """
        if symbol not in self.last_signal_time:
            return None
        
        current_time = time.time()
        last_time = self.last_signal_time[symbol]
        time_elapsed = (current_time - last_time) / 60
        
        remaining = max(0, config.SIGNAL_COOLDOWN_MINUTES - time_elapsed)
        
        return {
            'symbol': symbol,
            'last_signal_time': datetime.fromtimestamp(last_time).strftime('%Y-%m-%d %H:%M:%S'),
            'last_signal_level': self.last_signal_level.get(symbol, 'UNKNOWN'),
            'minutes_elapsed': time_elapsed,
            'minutes_remaining': remaining,
            'can_send': remaining == 0
        }
    
    def reset_cooldown(self, symbol: str = None):
        """
        Cooldown'ı sıfırlar
        
        Args:
            symbol: Belirli bir sembol (None ise tümü)
        """
        if symbol:
            if symbol in self.last_signal_time:
                del self.last_signal_time[symbol]
            if symbol in self.last_signal_level:
                del self.last_signal_level[symbol]
            logger.info(f"{symbol} için cooldown sıfırlandı")
        else:
            self.last_signal_time.clear()
            self.last_signal_level.clear()
            logger.info("Tüm cooldown'lar sıfırlandı")
    
    def get_stats(self) -> Dict:
        """İstatistikleri döndürür"""
        return {
            'total_signals_sent': self.stats['total_signals_sent'],
            'signals_blocked_by_cooldown': self.stats['signals_blocked_by_cooldown'],
            'active_cooldowns': len(self.last_signal_time),
            'cooldown_duration_minutes': config.SIGNAL_COOLDOWN_MINUTES
        }
    
    def cleanup_old_entries(self, max_age_hours: int = 24):
        """
        Eski cooldown kayıtlarını temizler
        
        Args:
            max_age_hours: Kaç saatten eski kayıtlar silinsin
        """
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        to_remove = []
        for symbol, last_time in self.last_signal_time.items():
            if current_time - last_time > max_age_seconds:
                to_remove.append(symbol)
        
        for symbol in to_remove:
            del self.last_signal_time[symbol]
            if symbol in self.last_signal_level:
                del self.last_signal_level[symbol]
        
        if to_remove:
            logger.info(f"{len(to_remove)} eski cooldown kaydı temizlendi")


# Singleton instance
_cooldown_manager_instance = None

def get_cooldown_manager() -> CooldownManager:
    """CooldownManager singleton instance döndürür"""
    global _cooldown_manager_instance
    if _cooldown_manager_instance is None:
        _cooldown_manager_instance = CooldownManager()
    return _cooldown_manager_instance