"""
BIST PMR v1.0 - Bildirim ve Watchlist Yönetimi
Telegram bildirimleri, watchlist tutma, raporlama
"""

import json
import numpy as np
from datetime import datetime
from typing import Dict, List
import requests
from .config import *

class PMRJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating, np.bool_)):
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class TelegramNotifier:
    """Telegram bildirici"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.enabled = TELEGRAM_ENABLED and self.bot_token != "YOUR_BOT_TOKEN_HERE"
    
    def send_alert(self, symbol: str, score: float, label: str, 
                   reasons: dict, risk_note: str = "") -> bool:
        """
        PMR alerti gönder
        
        Args:
            symbol: Hisse kodu
            score: PMR skoru
            label: Risk etiketi
            reasons: Alt skor nedenleri dict
            risk_note: Ek risk notu
            
        Returns:
            bool: Başarılı gönderim
        """
        if not self.enabled:
            print(f"[Telegram] DISABLED - {symbol}: {score:.1f} {label}")
            return False
        
        message = self._format_alert_message(symbol, score, label, reasons, risk_note)
        
        return self._send_message(message)
    
    def send_start_alert(self, symbol: str, message: str) -> bool:
        """Manipülasyon başlama alerti"""
        if not self.enabled:
            print(f"[Telegram] START ALERT - {symbol}: {message}")
            return False
        
        alert = f"🚨 BAŞLAMA ALARMI 🚨\n\n"
        alert += f"Hisse: {symbol}\n"
        alert += f"{message}\n\n"
        alert += "⚠️ Hazırlık evresi bitti; risk yükseldi!"
        
        return self._send_message(alert)
    
    def _format_alert_message(self, symbol: str, score: float, label: str,
                             reasons: dict, risk_note: str) -> str:
        """Alert mesajını formatla"""
        msg = "🧠 PMR ERKEN UYARI (Hazırlık Tespiti)\n\n"
        msg += f"Hisse: {symbol}\n"
        msg += f"PMR Score: {score:.1f} / 100 {label.split()[0]}\n"
        msg += f"Etiket: {label}\n\n"
        
        msg += "📊 Nedenler:\n"
        
        # Accumulation
        if reasons.get('A_reasons'):
            msg += f"• Accumulation ({reasons['A']:.0f}p): "
            msg += ", ".join(reasons['A_reasons']) + "\n"
        
        # Volatility
        if reasons.get('V_reasons'):
            msg += f"• Volatilite sıkışması ({reasons['V']:.0f}p): "
            msg += ", ".join(reasons['V_reasons']) + "\n"
        
        # Absorption
        if reasons.get('O_reasons'):
            msg += f"• Orderbook emilim ({reasons['O']:.0f}p): "
            msg += ", ".join(reasons['O_reasons']) + "\n"
        
        # Flow
        if reasons.get('F_reasons'):
            msg += f"• İşlem akışı ({reasons['F']:.0f}p): "
            msg += ", ".join(reasons['F_reasons']) + "\n"
        
        # Context
        if reasons.get('C_reasons'):
            msg += f"• Context ({reasons['C']:.0f}p): "
            msg += ", ".join(reasons['C_reasons']) + "\n"
        
        msg += f"\n{risk_note}\n"
        
        # Eylem notu
        if score >= SCORE_THRESHOLD_VERY_HIGH:
            msg += "\n✅ Watchlist öncelik 1"
            msg += "\n⚠️ Patlama başladığında 'erken' biter; risk artar."
        elif score >= SCORE_THRESHOLD_HIGH:
            msg += "\n🔍 Yakından takip et"
        
        msg += f"\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return msg
    
    def _send_message(self, text: str) -> bool:
        """Telegram API ile mesaj gönder"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            print(f"[Telegram] Mesaj gönderildi: {text[:50]}...")
            return True
            
        except Exception as e:
            print(f"[Telegram] Hata: {e}")
            return False


class Watchlist:
    """Watchlist yönetimi"""
    
    def __init__(self, filepath: str = "pmr_watchlist.json"):
        self.filepath = filepath
        self.items = self._load()
    
    def add(self, symbol: str, score: float, label: str, 
            reasons: dict, timestamp: datetime = None):
        """Watchlist'e ekle"""
        timestamp = timestamp or datetime.now()
        
        item = {
            'symbol': symbol,
            'score': score,
            'label': label,
            'reasons': reasons,
            'timestamp': timestamp.isoformat(),
            'active': True
        }
        
        # Aynı sembol varsa güncelle
        existing_idx = None
        for idx, existing in enumerate(self.items):
            if existing['symbol'] == symbol and existing['active']:
                existing_idx = idx
                break
        
        if existing_idx is not None:
            # Skor artmışsa güncelle
            if score > self.items[existing_idx]['score']:
                self.items[existing_idx] = item
                print(f"[Watchlist] {symbol} güncellendi: {score:.1f}")
        else:
            # Yeni ekle
            self.items.append(item)
            print(f"[Watchlist] {symbol} eklendi: {score:.1f}")
        
        self._save()
    
    def remove(self, symbol: str):
        """Watchlist'ten çıkar (passive yap)"""
        for item in self.items:
            if item['symbol'] == symbol and item['active']:
                item['active'] = False
                print(f"[Watchlist] {symbol} pasif edildi")
        
        self._save()
    
    def get_active(self, min_score: float = 0) -> List[Dict]:
        """Aktif watchlist itemlarını döner"""
        return [item for item in self.items 
                if item['active'] and item['score'] >= min_score]
    
    def get_top(self, n: int = 10) -> List[Dict]:
        """En yüksek skorlu N hisseyi döner"""
        active = self.get_active()
        sorted_items = sorted(active, key=lambda x: x['score'], reverse=True)
        return sorted_items[:n]
    
    def clear_old(self, hours: int = 24):
        """Eski kayıtları temizle"""
        cutoff = datetime.now().timestamp() - (hours * 3600)
        
        for item in self.items:
            item_time = datetime.fromisoformat(item['timestamp']).timestamp()
            if item_time < cutoff:
                item['active'] = False
        
        self._save()
        print(f"[Watchlist] {hours} saatten eski kayıtlar temizlendi")
    
    def _load(self) -> List[Dict]:
        """Dosyadan yükle"""
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"[Watchlist] Yükleme hatası: {e}")
            return []
    
    def _save(self):
        """Dosyaya kaydet"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Watchlist] Kayıt hatası: {e}")
    
    def generate_report(self) -> str:
        """Watchlist raporu oluştur"""
        active = self.get_active(min_score=SCORE_THRESHOLD_MEDIUM)
        
        if not active:
            return "📋 Watchlist boş (minimum skor: 45)\n"
        
        report = f"📋 PMR WATCHLIST RAPORU\n"
        report += f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"Aktif hisse sayısı: {len(active)}\n\n"
        
        # Skor grupları
        very_high = [x for x in active if x['score'] >= SCORE_THRESHOLD_VERY_HIGH]
        high = [x for x in active if SCORE_THRESHOLD_HIGH <= x['score'] < SCORE_THRESHOLD_VERY_HIGH]
        medium = [x for x in active if SCORE_THRESHOLD_MEDIUM <= x['score'] < SCORE_THRESHOLD_HIGH]
        
        if very_high:
            report += "🔥 ÇOK YÜKSEK HAZIRLIK:\n"
            for item in sorted(very_high, key=lambda x: x['score'], reverse=True):
                report += f"  • {item['symbol']}: {item['score']:.1f}\n"
            report += "\n"
        
        if high:
            report += "🟠 YÜKSEK HAZIRLIK:\n"
            for item in sorted(high, key=lambda x: x['score'], reverse=True):
                report += f"  • {item['symbol']}: {item['score']:.1f}\n"
            report += "\n"
        
        if medium:
            report += "🟡 ORTA HAZIRLIK:\n"
            for item in sorted(medium, key=lambda x: x['score'], reverse=True):
                report += f"  • {item['symbol']}: {item['score']:.1f}\n"
        
        return report


class Logger:
    """Detaylı loglama"""
    
    def __init__(self, filepath: str = "pmr_detailed.log"):
        self.filepath = filepath
    
    def log_scan(self, symbol: str, score: float, features: dict, 
                 reasons: dict, timestamp: datetime = None):
        """Tarama detayını logla"""
        timestamp = timestamp or datetime.now()
        
        entry = {
            'timestamp': timestamp.isoformat(),
            'symbol': symbol,
            'score': score,
            'features': features,
            'reasons': reasons
        }
        
        try:
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, cls=PMRJSONEncoder, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Logger] Hata: {e}")
