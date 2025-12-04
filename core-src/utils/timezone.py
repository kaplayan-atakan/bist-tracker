"""
BİST Trading Bot - Timezone Utilities
Türkiye saat dilimi ile tüm zaman işlemleri.

TÜM piyasa zamanı hesaplamaları bu modül üzerinden yapılmalıdır.
VPS lokasyonundan bağımsız olarak doğru Türkiye saati kullanılır.
"""
from datetime import datetime, time as datetime_time, timedelta
from typing import Optional
import pytz

# Turkey timezone - tüm bot bu timezone'u kullanır
TURKEY_TZ = pytz.timezone('Europe/Istanbul')


def now_turkey() -> datetime:
    """
    Türkiye saat diliminde şu anki zamanı döndürür.
    
    Returns:
        datetime: Türkiye saatine göre şu anki zaman
    """
    return datetime.now(TURKEY_TZ)


def today_turkey() -> datetime:
    """
    Türkiye saat diliminde bugünün tarihini döndürür.
    
    Returns:
        date: Türkiye saatine göre bugünün tarihi
    """
    return now_turkey().date()


def current_time_str() -> str:
    """
    Türkiye saatini HH:MM formatında string olarak döndürür.
    
    Returns:
        str: "HH:MM" formatında saat (örn: "14:30")
    """
    return now_turkey().strftime("%H:%M")


def is_weekday() -> bool:
    """
    Bugün hafta içi mi kontrol eder.
    
    Returns:
        bool: Pazartesi-Cuma ise True
    """
    return now_turkey().weekday() < 5


def is_market_hours(open_hour: int = 10, close_hour: int = 18) -> bool:
    """
    Şu anki zamanın BİST piyasa saatleri içinde olup olmadığını kontrol eder.
    
    Varsayılan: 10:00 - 18:00 Türkiye saati, hafta içi.
    
    Args:
        open_hour: Piyasa açılış saati (varsayılan: 10)
        close_hour: Piyasa kapanış saati (varsayılan: 18)
        
    Returns:
        bool: Piyasa açıksa True
    """
    now = now_turkey()
    
    # Hafta sonu kontrolü (Cumartesi=5, Pazar=6)
    if now.weekday() >= 5:
        return False
    
    current_time = now.time()
    market_open = datetime_time(open_hour, 0)
    market_close = datetime_time(close_hour, 0)
    
    return market_open <= current_time <= market_close


def is_near_market_close(minutes_before: int = 30) -> bool:
    """
    Piyasa kapanışına yakın mı kontrol eder.
    
    Args:
        minutes_before: Kapanışa kaç dakika kala True dönecek
        
    Returns:
        bool: Kapanışa yakınsa True
    """
    now = now_turkey()
    
    if now.weekday() >= 5:
        return False
    
    current_time = now.time()
    close_warning_time = datetime_time(17, 60 - minutes_before)
    market_close = datetime_time(18, 0)
    
    return close_warning_time <= current_time <= market_close


def get_next_market_open() -> str:
    """
    Sonraki piyasa açılış zamanını insan okunabilir string olarak döndürür.
    
    Returns:
        str: "Bugün 10:00", "Yarın 10:00", veya "Pazartesi 10:00"
    """
    now = now_turkey()
    current_time = now.time()
    market_open = datetime_time(10, 0)
    market_close = datetime_time(18, 0)
    weekday = now.weekday()
    
    # Hafta içi, piyasa açılmadan önce
    if weekday < 5 and current_time < market_open:
        return "Bugün 10:00"
    
    # Hafta içi, piyasa saatlerinde
    if weekday < 5 and market_open <= current_time <= market_close:
        return "Şu an açık"
    
    # Cuma kapanıştan sonra
    if weekday == 4 and current_time > market_close:
        return "Pazartesi 10:00"
    
    # Cumartesi
    if weekday == 5:
        return "Pazartesi 10:00"
    
    # Pazar
    if weekday == 6:
        return "Yarın 10:00"
    
    # Hafta içi kapanıştan sonra (Pazartesi-Perşembe)
    if weekday < 4 and current_time > market_close:
        return "Yarın 10:00"
    
    return "Yarın 10:00"


def parse_time_str(time_str: str) -> datetime_time:
    """
    HH:MM formatındaki string'i time objesine çevirir.
    
    Args:
        time_str: "HH:MM" formatında string (örn: "09:55")
        
    Returns:
        time: datetime.time objesi
    """
    parts = time_str.split(":")
    return datetime_time(int(parts[0]), int(parts[1]))


def get_turkey_datetime(dt: Optional[datetime] = None) -> datetime:
    """
    Verilen datetime'ı Türkiye timezone'una çevirir.
    None ise şu anki Türkiye saatini döndürür.
    
    Args:
        dt: Çevrilecek datetime (None ise now_turkey())
        
    Returns:
        datetime: Türkiye timezone'lu datetime
    """
    if dt is None:
        return now_turkey()
    
    if dt.tzinfo is None:
        # Naive datetime - Türkiye olarak kabul et
        return TURKEY_TZ.localize(dt)
    else:
        # Aware datetime - Türkiye'ye çevir
        return dt.astimezone(TURKEY_TZ)


def format_timestamp(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Datetime'ı formatlanmış string olarak döndürür (Türkiye saati).
    
    Args:
        dt: Formatlanacak datetime (None ise şu an)
        fmt: strftime formatı
        
    Returns:
        str: Formatlanmış tarih/saat string'i
    """
    if dt is None:
        dt = now_turkey()
    return get_turkey_datetime(dt).strftime(fmt)
