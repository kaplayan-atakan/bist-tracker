#!/usr/bin/env python3
"""
BIST Pre-Manipulation Radar (PMR) v1.0
Ana Çalıştırma Scripti

Kullanım:
    python -m pmr.cli [mod] [opsiyonlar]

Modlar:
    single SYMBOL    - Tek hisse tara
    scan             - Tüm evreni bir kez tara
    continuous       - Sürekli tarama modu (varsayılan)
    report           - Watchlist raporu göster
    
Örnekler:
    python -m pmr.cli single THYAO
    python -m pmr.cli scan
    python -m pmr.cli continuous
    python -m pmr.cli report
"""

import sys
import argparse
from datetime import datetime

from .scanner import PMRScanner
from .config import *


def print_banner():
    """Banner yazdır"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   BIST Pre-Manipulation Radar (PMR) v1.0                    ║
║   Manipülasyon Erken Uyarı Sistemi                          ║
║                                                              ║
║   © 2025 - Yalnızca eğitim amaçlıdır                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Başlangıç: {time}
Veri Kaynağı: {source}
Telegram: {telegram_status}

""".format(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source=DATA_SOURCE.upper(),
        telegram_status="AÇIK ✓" if TELEGRAM_ENABLED else "KAPALI ✗"
    )
    print(banner)


def mode_single(scanner: PMRScanner, symbol: str):
    """Tek hisse tarama modu"""
    print(f"\n{'='*60}")
    print(f"TEK HİSSE TARAMASI: {symbol}")
    print(f"{'='*60}\n")
    
    result = scanner.scan_symbol(symbol)
    
    if result is None:
        print(f"\n❌ {symbol} için sonuç üretilemedi (veri yetersiz veya likidite düşük)\n")
        return
    
    # Detaylı sonuç
    print(f"\n{'='*60}")
    print(f"SONUÇ: {result['symbol']}")
    print(f"{'='*60}")
    print(f"\n📊 PMR Score: {result['score']:.1f} / 100")
    print(f"🏷️  Etiket: {result['label']}")
    print(f"✅ İşlem yapılabilir: {'EVET' if result['tradeable'] else 'HAYIR'}")
    
    print(f"\n📈 Alt Skorlar:")
    print(f"  • Accumulation (A): {result['A']:.1f} / {MAX_ACCUMULATION}")
    print(f"  • Volatility (V): {result['V']:.1f} / {MAX_VOLATILITY}")
    print(f"  • Absorption (O): {result['O']:.1f} / {MAX_ABSORPTION}")
    print(f"  • Flow (F): {result['F']:.1f} / {MAX_FLOW}")
    print(f"  • Context (C): {result['C']:.1f} / {MAX_CONTEXT}")
    
    print(f"\n📝 Nedenler:")
    reasons = result['reasons']
    
    if reasons.get('A_reasons'):
        print(f"\n  Accumulation:")
        for reason in reasons['A_reasons']:
            print(f"    - {reason}")
    
    if reasons.get('V_reasons'):
        print(f"\n  Volatilite:")
        for reason in reasons['V_reasons']:
            print(f"    - {reason}")
    
    if reasons.get('O_reasons'):
        print(f"\n  Order Book:")
        for reason in reasons['O_reasons']:
            print(f"    - {reason}")
    
    if reasons.get('F_reasons'):
        print(f"\n  İşlem Akışı:")
        for reason in reasons['F_reasons']:
            print(f"    - {reason}")
    
    if reasons.get('C_reasons'):
        print(f"\n  Context:")
        for reason in reasons['C_reasons']:
            print(f"    - {reason}")
    
    if result['risk_note']:
        print(f"\n⚠️  Risk Notu:")
        print(f"  {result['risk_note']}")
    
    print("\n" + "="*60 + "\n")


def mode_scan(scanner: PMRScanner):
    """Evren tarama modu (bir kez)"""
    print(f"\n{'='*60}")
    print(f"EVREN TARAMASI")
    print(f"{'='*60}\n")
    
    results = scanner.scan_universe(notify=True)
    
    print(f"\n{'='*60}")
    print(f"TARAMA TAMAMLANDI")
    print(f"{'='*60}")
    
    print(f"\nToplam: {len(results)} hisse işlendi")
    
    # Skor dağılımı
    very_high = [r for r in results if r['score'] >= SCORE_THRESHOLD_VERY_HIGH]
    high = [r for r in results if SCORE_THRESHOLD_HIGH <= r['score'] < SCORE_THRESHOLD_VERY_HIGH]
    medium = [r for r in results if SCORE_THRESHOLD_MEDIUM <= r['score'] < SCORE_THRESHOLD_HIGH]
    low = [r for r in results if r['score'] < SCORE_THRESHOLD_MEDIUM]
    
    print(f"\nSkor Dağılımı:")
    print(f"  🔥 Çok Yüksek (≥75): {len(very_high)}")
    print(f"  🟠 Yüksek (60-74): {len(high)}")
    print(f"  🟡 Orta (45-59): {len(medium)}")
    print(f"  🟢 Düşük (<45): {len(low)}")
    
    # Top 10
    if results:
        print(f"\n🏆 Top 10 Yüksek Skor:")
        sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
        for idx, r in enumerate(sorted_results[:10], 1):
            emoji = "🔥" if r['score'] >= 75 else "🟠" if r['score'] >= 60 else "🟡"
            print(f"  {idx:2d}. {emoji} {r['symbol']:10s} - {r['score']:5.1f} - {r['label']}")
    
    # Watchlist raporu
    print(f"\n{scanner.get_watchlist_report()}")
    
    print("\n" + "="*60 + "\n")


def mode_continuous(scanner: PMRScanner):
    """Sürekli tarama modu"""
    print(f"\n{'='*60}")
    print(f"SÜREKLİ TARAMA MODU")
    print(f"{'='*60}")
    print(f"\nTarama aralığı: {SCAN_INTERVAL_SECONDS} saniye")
    print(f"Durdurmak için: Ctrl+C\n")
    
    try:
        scanner.run_continuous(interval_seconds=SCAN_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n\n[PMR] Tarama durduruldu\n")


def mode_report(scanner: PMRScanner):
    """Watchlist raporu modu"""
    print(f"\n{'='*60}")
    print(f"WATCHLIST RAPORU")
    print(f"{'='*60}\n")
    
    report = scanner.get_watchlist_report()
    print(report)
    
    # Top signals detay
    top_signals = scanner.get_top_signals(10)
    
    if top_signals:
        print("\n" + "="*60)
        print("DETAYLI BİLGİLER (Top 10)")
        print("="*60)
        
        for idx, signal in enumerate(top_signals, 1):
            print(f"\n{idx}. {signal['symbol']} - Score: {signal['score']:.1f}")
            print(f"   Etiket: {signal['label']}")
            print(f"   Zaman: {signal['timestamp']}")
    
    print("\n" + "="*60 + "\n")


def main():
    """Ana fonksiyon"""
    parser = argparse.ArgumentParser(
        description="BIST Pre-Manipulation Radar (PMR) v1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'mode',
        nargs='?',
        default='continuous',
        choices=['single', 'scan', 'continuous', 'report'],
        help='Çalışma modu (varsayılan: continuous)'
    )
    
    parser.add_argument(
        'symbol',
        nargs='?',
        help='Hisse kodu (single modu için)'
    )
    
    parser.add_argument(
        '--source',
        choices=['mock', 'api', 'yfinance'],
        default=DATA_SOURCE,
        help='Veri kaynağı (varsayılan: config dosyasından)'
    )
    
    args = parser.parse_args()
    
    # Banner
    print_banner()
    
    # Scanner oluştur
    scanner = PMRScanner(data_source=args.source)
    
    # Mod çalıştır
    try:
        if args.mode == 'single':
            if not args.symbol:
                print("❌ HATA: 'single' modu için hisse kodu gerekli")
                print("Kullanım: python -m pmr.cli single THYAO\n")
                sys.exit(1)
            mode_single(scanner, args.symbol.upper())
        
        elif args.mode == 'scan':
            mode_scan(scanner)
        
        elif args.mode == 'continuous':
            mode_continuous(scanner)
        
        elif args.mode == 'report':
            mode_report(scanner)
    
    except Exception as e:
        print(f"\n❌ HATA: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
