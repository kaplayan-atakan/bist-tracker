"""
BIST PMR v1.0 - Ana Tarayıcı (Scanner)
Tüm modülleri birleştirerek hisse taraması yapar
"""

import pandas as pd
from datetime import datetime
from typing import Dict, Optional
import time

from .config import *
from .data import DataProvider, OrderBookTracker
from .features import FeatureExtractor
from .scoring import ScoringEngine, RiskGuard
from .notifier import TelegramNotifier, Watchlist, Logger


class PMRScanner:
    """Pre-Manipulation Radar Scanner"""
    
    def __init__(self, data_source: str = DATA_SOURCE):
        """
        Args:
            data_source: "mock" veya "api"
        """
        self.data_provider = DataProvider(source=data_source)
        self.feature_extractor = FeatureExtractor()
        self.scoring_engine = ScoringEngine()
        self.risk_guard = RiskGuard()
        self.telegram = TelegramNotifier()
        self.watchlist = Watchlist()
        self.logger = Logger()
        
        # Order book tracker (L2 için)
        self.ob_tracker = OrderBookTracker(window_minutes=ABSORPTION_WINDOW_MINUTES)
        
        print(f"[PMR] Scanner başlatıldı (data_source: {data_source})")
    
    def scan_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Tek hisseyi tarar ve PMR skorunu hesaplar
        
        Args:
            symbol: Hisse kodu
            
        Returns:
            dict: {
                'symbol': str,
                'score': float,
                'label': str,
                'A': float, 'V': float, 'O': float, 'F': float, 'C': float,
                'reasons': dict,
                'risk_note': str,
                'tradeable': bool
            }
            veya None (eğer veri yetersizse)
        """
        try:
            # === 1. VERİ TOPLAMA ===
            bars_1m = self.data_provider.get_ohlcv(symbol, "1m", ACC_LOOKBACK_BARS_1M)
            bars_5m = self.data_provider.get_ohlcv(symbol, "5m", ACC_LOOKBACK_BARS_5M)
            bars_daily = self.data_provider.get_ohlcv(symbol, "1d", 30)
            
            if bars_1m.empty or bars_5m.empty or bars_daily.empty:
                print(f"[PMR] {symbol}: Veri yetersiz, atlanıyor")
                return None
            
            daily_stats = self.data_provider.get_daily_stats(symbol)
            
            # === 2. LİKİDİTE KONTROLÜ (Erken exit) ===
            tradeable, risk_note = self.risk_guard.check_liquidity(daily_stats)
            
            if not tradeable:
                print(f"[PMR] {symbol}: {risk_note}")
                # Çok kötü likidite, daha fazla hesaplama yapmaya gerek yok
                return None
            
            # === 3. FEATURE ÇIKARIMI ===
            features_acc = self.feature_extractor.extract_accumulation_features(bars_5m)
            features_vol = self.feature_extractor.extract_volatility_features(bars_5m, bars_daily)
            
            # Order Book (L2 varsa)
            ob_snapshot = self.data_provider.get_orderbook_snapshot(symbol, depth=5)
            if ob_snapshot:
                self.ob_tracker.add_snapshot(symbol, ob_snapshot)
                ob_history = self.ob_tracker.get_history(symbol)
                features_abs = self.feature_extractor.extract_absorption_features(ob_history)
            else:
                features_abs = {}
            
            # Trade Prints (varsa)
            prints_df = self.data_provider.get_trade_prints(symbol, FLOW_WINDOW_MINUTES)
            if not prints_df.empty:
                features_flow = self.feature_extractor.extract_flow_features(prints_df)
            else:
                features_flow = {}
            
            # Fiyat değişimi (absorption/flow için)
            price_change = 0.0
            if len(bars_5m) >= 2:
                price_change = (bars_5m.iloc[-1]['close'] - bars_5m.iloc[-2]['close']) / bars_5m.iloc[-2]['close']
            
            # === 4. SKORLAMA ===
            A, A_reasons = self.scoring_engine.score_accumulation(features_acc)
            V, V_reasons = self.scoring_engine.score_volatility(features_vol)
            O, O_reasons = self.scoring_engine.score_absorption(features_abs, price_change)
            F, F_reasons = self.scoring_engine.score_flow(features_flow, price_change)
            
            # Context (mock için basit - gerçekte KAP/sosyal medya entegrasyonu gerekir)
            C, C_reasons = self.scoring_engine.score_context(
                symbol, daily_stats, kap_count=0, social_ratio=1.0
            )
            
            total_score, label = self.scoring_engine.calculate_total_score(A, V, O, F, C)
            
            # === 5. FALSE POSITIVE KONTROLÜ ===
            is_fp, fp_reason = self.scoring_engine.check_false_positives(
                features_acc, features_vol, features_abs, features_flow, 
                daily_stats, kap_count=0
            )
            
            if is_fp:
                print(f"[PMR] {symbol}: FP algılandı - {fp_reason}")
                risk_note += f"\n⚠️ {fp_reason}"
                # FP ise skoru düşür
                total_score *= 0.5
                label = "🟡 FP Risk"
            
            # === 6. BAŞLAMA KONTROLÜ ===
            avg_vol_1m = bars_1m['volume'].mean()
            started, start_msg = self.risk_guard.check_manipulation_started(bars_1m, avg_vol_1m)
            
            if started:
                risk_note += f"\n{start_msg}"
                self.telegram.send_start_alert(symbol, start_msg)
            
            # === 7. SONUÇ PAKETI ===
            result = {
                'symbol': symbol,
                'score': total_score,
                'label': label,
                'A': A,
                'V': V,
                'O': O,
                'F': F,
                'C': C,
                'reasons': {
                    'A': A, 'A_reasons': A_reasons,
                    'V': V, 'V_reasons': V_reasons,
                    'O': O, 'O_reasons': O_reasons,
                    'F': F, 'F_reasons': F_reasons,
                    'C': C, 'C_reasons': C_reasons
                },
                'risk_note': risk_note,
                'tradeable': tradeable,
                'timestamp': datetime.now().isoformat()
            }
            
            # Log detayı
            self.logger.log_scan(
                symbol, total_score,
                {
                    'accumulation': features_acc,
                    'volatility': features_vol,
                    'absorption': features_abs,
                    'flow': features_flow
                },
                result['reasons']
            )
            
            return result
            
        except Exception as e:
            print(f"[PMR] {symbol} tarama hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def scan_universe(self, notify: bool = True) -> list:
        """
        Tüm evreni tarar
        
        Args:
            notify: Telegram bildirimi gönderilsin mi
            
        Returns:
            list: Tüm sonuçlar
        """
        universe = self.data_provider.get_universe()
        print(f"[PMR] Evren taraması başlıyor: {len(universe)} hisse")
        
        results = []
        
        for idx, symbol in enumerate(universe):
            print(f"[PMR] [{idx+1}/{len(universe)}] Taranıyor: {symbol}")
            
            result = self.scan_symbol(symbol)
            
            if result is None:
                continue
            
            results.append(result)
            
            # Yüksek skorlu hisseler için watchlist ve bildirim
            if result['score'] >= SCORE_THRESHOLD_HIGH:
                self.watchlist.add(
                    result['symbol'],
                    result['score'],
                    result['label'],
                    result['reasons']
                )
                
                if notify:
                    self.telegram.send_alert(
                        result['symbol'],
                        result['score'],
                        result['label'],
                        result['reasons'],
                        result['risk_note']
                    )
            
            # Rate limiting (API koruması)
            time.sleep(0.5)
        
        print(f"[PMR] Tarama tamamlandı: {len(results)} hisse işlendi")
        
        return results
    
    def run_continuous(self, interval_seconds: int = SCAN_INTERVAL_SECONDS):
        """
        Sürekli tarama modu
        
        Args:
            interval_seconds: Tarama aralığı (saniye)
        """
        print(f"[PMR] Sürekli tarama başlatılıyor (interval: {interval_seconds}s)")
        
        iteration = 0
        
        while True:
            try:
                iteration += 1
                print(f"\n{'='*60}")
                print(f"[PMR] İterasyon #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*60}\n")
                
                # Tam tarama
                results = self.scan_universe(notify=True)
                
                # Watchlist raporu
                if iteration % 10 == 0:  # Her 10 iterasyonda bir
                    report = self.watchlist.generate_report()
                    print(f"\n{report}")
                    
                    # Eski kayıtları temizle
                    self.watchlist.clear_old(hours=24)
                
                # Sleep
                print(f"\n[PMR] {interval_seconds} saniye bekleniyor...")
                time.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                print("\n[PMR] Kullanıcı tarafından durduruldu")
                break
            except Exception as e:
                print(f"[PMR] Ana döngü hatası: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)  # Hata durumunda 1 dk bekle
    
    def get_watchlist_report(self) -> str:
        """Mevcut watchlist raporunu döner"""
        return self.watchlist.generate_report()
    
    def get_top_signals(self, n: int = 10) -> list:
        """En yüksek skorlu N hisseyi döner"""
        return self.watchlist.get_top(n)
