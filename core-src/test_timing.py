"""
Tarama zamanlama testleri
"""
from datetime import datetime, timedelta
import config

def test_tarama_zamanlari():
    # İlk tarama 13:16'da (gerçek senaryo)
    first_scan = datetime.now().replace(hour=13, minute=16, second=0, microsecond=0)
    
    print("=== MEVCUT DURUM ANALİZİ ===")
    print(f"İlk tarama: {first_scan.strftime('%H:%M')}")
    print(f"Interval: {config.INTRADAY_SCAN_INTERVAL // 60} dakika")
    print()
    
    # Beklenen tarama zamanlarını hesapla
    print("Beklenen tarama zamanları (13:16'dan itibaren):")
    current = first_scan
    scan_times = []
    while current.hour < 18:
        scan_times.append(current.strftime('%H:%M'))
        current += timedelta(seconds=config.INTRADAY_SCAN_INTERVAL)
    
    for i, t in enumerate(scan_times[:10], 1):
        print(f"  {i}. {t}")
    
    print()
    print("=== ŞU ANKİ DURUM ===")
    now = datetime.now()
    print(f"Şu an: {now.strftime('%H:%M:%S')}")
    
    interval = timedelta(seconds=config.INTRADAY_SCAN_INTERVAL)
    elapsed = now - first_scan
    periods_passed = int(elapsed.total_seconds() // interval.total_seconds())
    next_scan = first_scan + (interval * (periods_passed + 1))
    
    print(f"Geçen süre: {elapsed.total_seconds() / 60:.1f} dakika")
    print(f"Geçen interval: {periods_passed}")
    print(f"Sonraki tarama: {next_scan.strftime('%H:%M')}")
    print(f"Kalan süre: {(next_scan - now).total_seconds() / 60:.1f} dakika")
    
    # _should_run_intraday_scan() simülasyonu
    print()
    print("=== _should_run_intraday_scan() KONTROLÜ ===")
    market_close = now.replace(hour=18, minute=0)
    
    if next_scan >= market_close:
        print("Sonuç: False (piyasa kapanmış)")
    elif now >= next_scan:
        print("Sonuç: True (tarama zamanı geldi!)")
    else:
        print(f"Sonuç: False (henüz {next_scan.strftime('%H:%M')} olmadı)")

if __name__ == "__main__":
    test_tarama_zamanlari()
