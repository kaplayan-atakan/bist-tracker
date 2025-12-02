"""
MVP Integration Smoke Test
Run this before deployment to verify end-to-end flow.

Tests:
1. Provider initialization
2. Intraday OHLCV data
3. Daily OHLCV data
4. Daily stats
5. Fundamentals (optional)
6. Config check (data delay)
7. Telegram notifier (dry run)
8. Indicators calculation
9. Scoring engine
10. Filters

Usage:
    python test_mvp_integration.py
"""

import asyncio
import sys
import traceback
from datetime import datetime

# Test sonuçları
test_results = []


def log_test(name: str, passed: bool, details: str = ""):
    """Test sonucunu logla"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"\n{status}: {name}")
    if details:
        print(f"   {details}")
    test_results.append((name, passed, details))


async def test_mvp():
    """MVP Integration Test Suite"""
    print("=" * 70)
    print("  BİST Trading Bot - MVP Integration Smoke Test")
    print("=" * 70)
    print(f"  Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # =========================================================================
    # TEST 1: Provider Initialization
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 1: Provider Initialization")
    print("-" * 70)
    
    try:
        from providers import get_provider_manager
        manager = get_provider_manager()
        
        provider_names = list(manager.providers.keys())
        log_test(
            "Provider Manager başlatıldı",
            len(provider_names) > 0,
            f"Aktif provider'lar: {provider_names}"
        )
        
        # Provider'ları initialize et
        await manager.initialize_providers()
        health = manager.get_health_summary()
        log_test(
            "Provider'lar initialize edildi",
            True,
            f"Sağlık durumu: {health}"
        )
        
    except Exception as e:
        log_test("Provider Initialization", False, str(e))
        traceback.print_exc()
        return False
    
    # =========================================================================
    # TEST 2: Intraday OHLCV Data
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 2: Intraday OHLCV Data (15m)")
    print("-" * 70)
    
    try:
        df_intraday = await manager.get_ohlcv_intraday("GARAN", "15m", 50)
        
        if df_intraday is not None and not df_intraday.empty:
            log_test(
                "Intraday OHLCV çekildi (GARAN, 15m)",
                True,
                f"Rows: {len(df_intraday)}, Columns: {list(df_intraday.columns)}"
            )
        else:
            log_test(
                "Intraday OHLCV çekildi (GARAN, 15m)",
                False,
                "DataFrame boş veya None"
            )
    except Exception as e:
        log_test("Intraday OHLCV", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 3: Daily OHLCV Data
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 3: Daily OHLCV Data")
    print("-" * 70)
    
    try:
        df_daily = await manager.get_ohlcv_daily("THYAO", 100)
        
        if df_daily is not None and not df_daily.empty:
            log_test(
                "Daily OHLCV çekildi (THYAO, 100 bar)",
                True,
                f"Rows: {len(df_daily)}, Columns: {list(df_daily.columns)}"
            )
            
            # Schema kontrolü
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [c for c in required_cols if c not in df_daily.columns]
            
            log_test(
                "DataFrame schema uyumlu",
                len(missing_cols) == 0,
                f"Eksik kolonlar: {missing_cols}" if missing_cols else "Tüm kolonlar mevcut"
            )
        else:
            log_test("Daily OHLCV", False, "DataFrame boş veya None")
    except Exception as e:
        log_test("Daily OHLCV", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 4: Daily Stats
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 4: Daily Stats")
    print("-" * 70)
    
    try:
        stats = await manager.get_daily_stats("ASELS")
        
        if stats:
            price = stats.get('current_price', stats.get('close', 'N/A'))
            log_test(
                "Daily stats çekildi (ASELS)",
                True,
                f"Fiyat: {price}, Keys: {list(stats.keys())}"
            )
        else:
            log_test("Daily Stats", False, "Stats boş veya None")
    except Exception as e:
        log_test("Daily Stats", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 5: Fundamentals
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 5: Fundamentals (opsiyonel)")
    print("-" * 70)
    
    try:
        fundamentals = await manager.get_fundamentals("KCHOL")
        
        if fundamentals:
            log_test(
                "Fundamentals çekildi (KCHOL)",
                True,
                f"Keys: {list(fundamentals.keys())}"
            )
        else:
            log_test("Fundamentals", True, "Fundamentals boş (opsiyonel alan)")
    except Exception as e:
        log_test("Fundamentals", True, f"Opsiyonel: {str(e)}")
    
    # =========================================================================
    # TEST 6: Config Check (Data Delay)
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 6: Config Check (Data Delay)")
    print("-" * 70)
    
    try:
        import config
        
        delay_enabled = getattr(config, 'DATA_DELAY_ENABLED', False)
        delay_minutes = getattr(config, 'DATA_DELAY_MINUTES', 0)
        delay_text = getattr(config, 'DATA_DELAY_WARNING_TEXT', '')
        
        log_test(
            "Data delay config mevcut",
            delay_enabled and delay_minutes > 0,
            f"Enabled: {delay_enabled}, Minutes: {delay_minutes}"
        )
        
        log_test(
            "Data delay warning text",
            len(delay_text) > 0,
            f"Text: {delay_text[:50]}..." if len(delay_text) > 50 else f"Text: {delay_text}"
        )
    except Exception as e:
        log_test("Config Check", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 7: Telegram Notifier (Dry Run)
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 7: Telegram Notifier (Dry Run)")
    print("-" * 70)
    
    try:
        from telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier(dry_run=True)
        
        log_test(
            "TelegramNotifier initialized (dry_run=True)",
            True,
            "Notifier başarıyla oluşturuldu"
        )
        
        # Test mesajı format kontrolü
        test_signal = {
            'symbol': 'TEST',
            'signal_level': 'STRONG_BUY',
            'total_score': 15,
            'max_possible_score': 20,
            'trend_score': 4,
            'momentum_score': 4,
            'volume_score': 4,
            'fundamental_pa_score': 3,
            'triggered_criteria': ['Test kriter 1', 'Test kriter 2']
        }
        test_daily_stats = {
            'current_price': 100.0,
            'daily_change_percent': 2.5,
            'daily_volume_tl': 50_000_000
        }
        
        message = notifier.format_signal_message(test_signal, test_daily_stats)
        
        # Veri gecikmesi uyarısı mesajda var mı?
        has_delay_warning = config.DATA_DELAY_WARNING_TEXT in message if delay_enabled else True
        
        log_test(
            "Sinyal mesajı formatlandı",
            len(message) > 100 and has_delay_warning,
            f"Mesaj uzunluğu: {len(message)} karakter, Delay uyarısı: {'Var' if has_delay_warning else 'Yok'}"
        )
        
    except Exception as e:
        log_test("Telegram Notifier", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 8: Indicators Calculation
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 8: Indicators Calculation")
    print("-" * 70)
    
    try:
        from indicators import (
            calculate_trend_indicators,
            calculate_momentum_indicators,
            calculate_volume_indicators,
            calculate_price_action_features
        )
        
        # Daily OHLCV'yi kullan
        if df_daily is not None and not df_daily.empty:
            trend = calculate_trend_indicators(df_daily)
            momentum = calculate_momentum_indicators(df_daily)
            volume = calculate_volume_indicators(df_daily)
            pa = calculate_price_action_features(df_daily)
            
            log_test(
                "Trend indicators hesaplandı",
                len(trend) > 0,
                f"Keys: {list(trend.keys())[:5]}..."
            )
            
            log_test(
                "Momentum indicators hesaplandı",
                len(momentum) > 0,
                f"RSI: {momentum.get('rsi', 'N/A')}"
            )
            
            log_test(
                "Volume indicators hesaplandı",
                len(volume) > 0,
                f"Volume ratio: {volume.get('volume_ratio', 'N/A')}"
            )
            
            log_test(
                "Price action features hesaplandı",
                len(pa) > 0,
                f"Close position: {pa.get('close_position', 'N/A')}"
            )
        else:
            log_test("Indicators", False, "Daily OHLCV verisi yok")
            
    except Exception as e:
        log_test("Indicators", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 9: Scoring Engine
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 9: Scoring Engine")
    print("-" * 70)
    
    try:
        from scoring import calculate_total_score
        
        if df_daily is not None and not df_daily.empty:
            signal = calculate_total_score(
                symbol="THYAO",
                trend_indicators=trend,
                momentum_indicators=momentum,
                volume_indicators=volume,
                pa_indicators=pa,
                fundamentals=None
            )
            
            log_test(
                "Scoring engine çalışıyor",
                'total_score' in signal and 'signal_level' in signal,
                f"Score: {signal.get('total_score')}/{signal.get('max_possible_score')}, Level: {signal.get('signal_level')}"
            )
        else:
            log_test("Scoring", False, "Indicator verisi yok")
            
    except Exception as e:
        log_test("Scoring", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # TEST 10: Filters
    # =========================================================================
    print("\n" + "-" * 70)
    print("TEST 10: Filters")
    print("-" * 70)
    
    try:
        from filters import apply_all_filters
        
        # Test symbol data
        test_symbol_data = {
            'daily_stats': {
                'symbol': 'TEST',
                'current_price': 50.0,
                'daily_volume_tl': 5_000_000,
                'daily_change_percent': 2.0
            },
            'spread': 0.2,
            'volume_indicators': {'daily_volume_tl': 5_000_000},
            'pa_indicators': {'has_collapse': False}
        }
        
        passed, reason = apply_all_filters(test_symbol_data)
        
        log_test(
            "Filters çalışıyor",
            True,  # Filter çalışması yeterli
            f"Passed: {passed}, Reason: {reason}"
        )
        
    except Exception as e:
        log_test("Filters", False, str(e))
        traceback.print_exc()
    
    # =========================================================================
    # SONUÇ ÖZETİ
    # =========================================================================
    print("\n" + "=" * 70)
    print("  TEST SONUÇ ÖZETİ")
    print("=" * 70)
    
    passed_count = sum(1 for _, p, _ in test_results if p)
    failed_count = sum(1 for _, p, _ in test_results if not p)
    total_count = len(test_results)
    
    print(f"\n  ✅ Passed: {passed_count}/{total_count}")
    print(f"  ❌ Failed: {failed_count}/{total_count}")
    
    if failed_count > 0:
        print("\n  Failed tests:")
        for name, passed, details in test_results:
            if not passed:
                print(f"    - {name}: {details}")
    
    print("\n" + "=" * 70)
    
    # Provider'ları kapat
    try:
        await manager.shutdown_providers()
        print("  Provider'lar kapatıldı ✅")
    except:
        pass
    
    if failed_count == 0:
        print("\n  🎉 MVP Integration Test PASSED! 🎉")
        print("=" * 70)
        return True
    else:
        print("\n  ⚠️ MVP Integration Test FAILED!")
        print("  Bazı testler başarısız oldu. Lütfen kontrol edin.")
        print("=" * 70)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_mvp())
    sys.exit(0 if success else 1)
