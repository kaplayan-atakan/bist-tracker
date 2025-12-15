#!/usr/bin/env python3
"""
PMR Quick Test Script
Botun temel fonksiyonlarını test eder
"""

import sys
import os

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from pmr.scanner import PMRScanner
from pmr.config import *


def test_single_symbol():
    """Tek hisse testi"""
    print("\n" + "="*60)
    print("TEST 1: Tek Hisse Tarama")
    print("="*60)
    
    scanner = PMRScanner(data_source="mock")
    result = scanner.scan_symbol("THYAO")
    
    if result:
        print(f"✅ {result['symbol']}: Score={result['score']:.1f}, Label={result['label']}")
        return True
    else:
        print("❌ Test başarısız")
        return False


def test_universe_scan():
    """Evren tarama testi"""
    print("\n" + "="*60)
    print("TEST 2: Evren Tarama")
    print("="*60)
    
    scanner = PMRScanner(data_source="mock")
    results = scanner.scan_universe(notify=False)
    
    if results:
        print(f"✅ {len(results)} hisse tarandı")
        high_scores = [r for r in results if r['score'] >= 60]
        print(f"   Yüksek skor (≥60): {len(high_scores)}")
        return True
    else:
        print("❌ Test başarısız")
        return False


def test_features():
    """Feature extraction testi"""
    print("\n" + "="*60)
    print("TEST 3: Feature Extraction")
    print("="*60)
    
    from pmr.data import DataProvider
    from pmr.features import FeatureExtractor
    
    provider = DataProvider(source="mock")
    extractor = FeatureExtractor()
    
    df_5m = provider.get_ohlcv("THYAO", "5m", 60)
    df_daily = provider.get_ohlcv("THYAO", "1d", 30)
    
    if df_5m.empty or df_daily.empty:
        print("❌ Veri çekilemedi")
        return False
    
    features_acc = extractor.extract_accumulation_features(df_5m)
    features_vol = extractor.extract_volatility_features(df_5m, df_daily)
    
    print(f"✅ Accumulation features: {len(features_acc)} adet")
    print(f"✅ Volatility features: {len(features_vol)} adet")
    
    print(f"\n   OBV slope: {features_acc['obv_slope']:.6f}")
    print(f"   ADL slope: {features_acc['adl_slope']:.6f}")
    print(f"   ATR percentile: {features_vol['atr_percentile']:.1f}")
    
    return True


def test_scoring():
    """Skorlama testi"""
    print("\n" + "="*60)
    print("TEST 4: Skorlama Motoru")
    print("="*60)
    
    from pmr.scoring import ScoringEngine
    
    engine = ScoringEngine()
    
    # Mock features
    features_acc = {
        'price_flat': True,
        'obv_rising': True,
        'adl_rising': True,
        'price_slope': 0.0001,
        'obv_slope': 0.05,
        'adl_slope': 0.03
    }
    
    features_vol = {
        'atr_percentile': 15.0,
        'bbw_percentile': 12.0,
        'compressed': True,
        'atr_pct': 0.5,
        'bbw': 0.02
    }
    
    A, A_reasons = engine.score_accumulation(features_acc)
    V, V_reasons = engine.score_volatility(features_vol)
    
    print(f"✅ Accumulation Score: {A:.1f} / {MAX_ACCUMULATION}")
    print(f"   Reasons: {', '.join(A_reasons) if A_reasons else 'None'}")
    
    print(f"✅ Volatility Score: {V:.1f} / {MAX_VOLATILITY}")
    print(f"   Reasons: {', '.join(V_reasons) if V_reasons else 'None'}")
    
    total, label = engine.calculate_total_score(A, V, 0, 0, 0)
    print(f"\n✅ Total Score: {total:.1f} / 100")
    print(f"   Label: {label}")
    
    return True


def test_watchlist():
    """Watchlist testi"""
    print("\n" + "="*60)
    print("TEST 5: Watchlist Yönetimi")
    print("="*60)
    
    from pmr.notifier import Watchlist
    
    watchlist = Watchlist(filepath="test_watchlist.json")
    
    # Test ekle
    watchlist.add("TEST1", 75.0, "🔥 Çok Yüksek", {'A': 30, 'V': 20})
    watchlist.add("TEST2", 62.0, "🟠 Yüksek", {'A': 25, 'V': 15})
    
    active = watchlist.get_active()
    print(f"✅ Watchlist'e eklendi: {len(active)} item")
    
    top = watchlist.get_top(5)
    print(f"✅ Top items: {[x['symbol'] for x in top]}")
    
    # Temizle
    import os
    if os.path.exists("test_watchlist.json"):
        os.remove("test_watchlist.json")
    
    return True


def run_all_tests():
    """Tüm testleri çalıştır"""
    print("\n" + "="*70)
    print(" "*15 + "PMR BOT TEST SÜİTİ")
    print("="*70)
    
    tests = [
        ("Tek Hisse Tarama", test_single_symbol),
        ("Evren Tarama", test_universe_scan),
        ("Feature Extraction", test_features),
        ("Skorlama Motoru", test_scoring),
        ("Watchlist Yönetimi", test_watchlist)
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} - HATA: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Özet
    print("\n" + "="*70)
    print("TEST ÖZETİ")
    print("="*70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ BAŞARILI" if success else "❌ BAŞARISIZ"
        print(f"  {name:25s} ... {status}")
    
    print(f"\n  Toplam: {passed}/{total} test başarılı")
    
    if passed == total:
        print("\n  🎉 TÜM TESTLER BAŞARILI! Bot hazır.")
        return 0
    else:
        print(f"\n  ⚠️  {total - passed} test başarısız. Lütfen kontrol edin.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
