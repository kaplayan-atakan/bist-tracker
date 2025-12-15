"""
BİST Trading Bot - Scan Error Logger
Tarama hatalarını ve sonuçlarını izlemek için minimal logger.

Bu modül, ana log dosyasından bağımsız olarak tarama sonuçlarını
kompakt bir formatta kaydeder. Hata ayıklama ve analiz için kullanılır.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class ScanErrorLogger:
    """
    Tarama sonuçlarını ve hatalarını kompakt formatta loglar.
    
    Log formatı:
    - Her sembol için tek satır (sadece score >= 10 olanlar)
    - Gönderilme durumu ve sebebi
    - Provider hataları ayrı loglanır
    - Tarama özeti her tarama sonunda
    """
    
    def __init__(self, log_dir: str = "logs", log_file: str = "scan_errors.log"):
        """
        Args:
            log_dir: Log dizini
            log_file: Log dosya adı
        """
        # Log dizinini oluştur
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.log_file = self.log_dir / log_file
        
        # Başlangıç marker'ı
        self._write_line(f"\n{'='*70}")
        self._write_line(f"🚀 BOT BAŞLATILDI - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_line(f"{'='*70}\n")
    
    def _write_line(self, line: str):
        """Dosyaya satır yazar."""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    
    def log_scan_result(
        self, 
        symbol: str, 
        score: int, 
        level: str, 
        sent: bool, 
        reason: str = "",
        cache_hit: bool = True,
        data_source: str = ""
    ):
        """
        Sembol tarama sonucunu loglar.
        
        Args:
            symbol: Sembol kodu
            score: Toplam skor (0-20)
            level: Sinyal seviyesi (ULTRA_BUY, STRONG_BUY, WATCHLIST, NO_SIGNAL)
            sent: Sinyal gönderildi mi?
            reason: Gönderilmeme sebebi (opsiyonel)
            cache_hit: Cache'ten mi geldi?
            data_source: Veri kaynağı (provider adı)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        status = "✅ SENT" if sent else "❌ NOT_SENT"
        cache_str = "C" if cache_hit else "F"  # Cache/Fetch
        
        # Format: HH:MM:SS | SYMBOL   | Score: XX/20 | LEVEL        | STATUS     | REASON
        line = f"{timestamp} | {symbol:8} | Score: {score:2}/20 | {level:12} | {status:12} | {cache_str} | {reason}"
        self._write_line(line)
    
    def log_scan_start(self, scan_type: str, symbol_count: int):
        """
        Tarama başlangıcını loglar.
        
        Args:
            scan_type: Tarama tipi (INTRADAY, STARTUP, DAILY)
            symbol_count: Taranacak sembol sayısı
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._write_line(f"\n--- {timestamp} | {scan_type} TARAMA BAŞLADI | {symbol_count} sembol ---")
    
    def log_scan_summary(
        self, 
        scan_number: int = 0,
        scan_type: str = "INTRADAY",
        total_symbols: int = 0,
        analyzed: int = 0, 
        signals_sent: int = 0,
        cache_hits: int = 0,
        cache_misses: int = 0,
        filter_rejected: int = 0,
        data_errors: int = 0,
        duration_seconds: float = 0.0
    ):
        """
        Tarama özetini loglar.
        
        Args:
            scan_number: Tarama numarası
            scan_type: Tarama tipi (INTRADAY, STARTUP, DAILY)
            total_symbols: Toplam sembol sayısı
            analyzed: Analiz edilen sembol sayısı
            signals_sent: Gönderilen sinyal sayısı
            cache_hits: Cache hit sayısı
            cache_misses: Cache miss sayısı
            filter_rejected: Filtre tarafından reddedilen sayısı
            data_errors: Veri hatası sayısı
            duration_seconds: Tarama süresi (saniye)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self._write_line(f"\n{'='*70}")
        self._write_line(f"{timestamp} | {scan_type} TARAMA #{scan_number} ÖZETİ")
        self._write_line(f"   Toplam: {total_symbols} | Analiz: {analyzed} | Sinyal Gönderildi: {signals_sent}")
        self._write_line(f"   Cache: {cache_hits} hit / {cache_misses} miss | Filtre Red: {filter_rejected} | Veri Hatası: {data_errors}")
        self._write_line(f"   Süre: {duration_seconds:.1f}s")
        self._write_line(f"{'='*70}\n")
    
    def log_error(self, context: str, error: str):
        """
        Hata loglar.
        
        Args:
            context: Hatanın oluştuğu bağlam (örn: "scan_GARAN", "filter")
            error: Hata mesajı
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp} | 🔴 ERROR | {context:20} | {error}"
        self._write_line(line)

    def log_filter_rejection(self, symbol: str, reason: str):
        """
        Filtre reddini loglar (Hata değildir).
        
        Args:
            symbol: Sembol kodu
            reason: Red sebebi
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp} | 🟡 FILTER | {symbol:20} | {reason}"
        self._write_line(line)
    
    def log_provider_issue(self, provider: str, symbol: str, issue: str):
        """
        Provider sorununu loglar.
        
        Args:
            provider: Provider adı
            symbol: Etkilenen sembol
            issue: Sorun açıklaması
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp} | ⚠️ PROVIDER | {provider:15} | {symbol:8} | {issue}"
        self._write_line(line)
    
    def log_debug_comparison(
        self, 
        symbol: str, 
        score: int, 
        level: str,
        cache_hit: bool,
        data_source: str,
        should_send: bool,
        actual_sent: bool,
        block_reason: str = ""
    ):
        """
        Debug ve gerçek tarama karşılaştırması loglar.
        
        Args:
            symbol: Sembol kodu
            score: Skor
            level: Sinyal seviyesi
            cache_hit: Cache'ten mi geldi
            data_source: Veri kaynağı
            should_send: Teorik olarak gönderilmeli mi
            actual_sent: Gerçekte gönderildi mi
            block_reason: Engellenme sebebi
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        cache_str = "CACHE" if cache_hit else "FETCH"
        should_str = "SHOULD_SEND" if should_send else "SHOULD_NOT_SEND"
        actual_str = "SENT" if actual_sent else "NOT_SENT"
        
        self._write_line(
            f"{timestamp} | 🔍 DEBUG | {symbol:8} | {score:2}/20 | {level:12} | "
            f"{cache_str} | {data_source:10} | {should_str} | {actual_str} | {block_reason}"
        )
    
    def log_high_scorer(
        self,
        symbol: str,
        score: int,
        level: str,
        trend_score: int,
        momentum_score: int,
        volume_score: int,
        fundamental_score: int,
        triggered_criteria: list
    ):
        """
        Yüksek skorlu sembolleri detaylı loglar.
        
        Args:
            symbol: Sembol kodu
            score: Toplam skor
            level: Sinyal seviyesi
            trend_score: Trend skoru
            momentum_score: Momentum skoru
            volume_score: Hacim skoru
            fundamental_score: Temel analiz skoru
            triggered_criteria: Tetiklenen kriterler listesi
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self._write_line(f"{timestamp} | 🏆 HIGH_SCORE | {symbol:8} | {score:2}/20 | {level}")
        self._write_line(f"           | Skorlar: T:{trend_score} M:{momentum_score} V:{volume_score} F:{fundamental_score}")
        
        if triggered_criteria:
            criteria_str = " | ".join(triggered_criteria[:3])  # İlk 3 kriter
            self._write_line(f"           | Kriterler: {criteria_str}")


# Global instance
scan_error_logger = ScanErrorLogger()


def get_scan_error_logger() -> ScanErrorLogger:
    """Global scan error logger instance'ını döndürür."""
    return scan_error_logger
