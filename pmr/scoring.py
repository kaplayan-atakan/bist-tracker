"""
BIST PMR v1.0 - Skorlama Motoru
A: Accumulation, V: Volatility, O: Order Book, F: Flow, C: Context
"""

import numpy as np
from typing import Dict, Tuple
from .config import *


class ScoringEngine:
    """PMR Skorlama Motoru"""
    
    def __init__(self):
        pass
    
    def score_accumulation(self, features: dict) -> Tuple[float, list]:
        """
        A: Accumulation Divergence Skorlama (0-30)
        
        Mantık:
        - Fiyat yatay ama OBV/ADL yükseliyor → sessiz toplama
        
        Args:
            features: extract_accumulation_features() çıktısı
            
        Returns:
            (score, reasons): Score ve nedenleri
        """
        score = 0.0
        reasons = []
        
        price_flat = features['price_flat']
        obv_rising = features['obv_rising']
        adl_rising = features['adl_rising']
        
        # Fiyat yatay + OBV yükseliyor
        if price_flat and obv_rising:
            score += 15
            reasons.append(f"OBV↑ fiyat yatay (slope: {features['obv_slope']:.4f})")
        
        # Fiyat yatay + ADL yükseliyor
        if price_flat and adl_rising:
            score += 10
            reasons.append(f"ADL↑ fiyat yatay (slope: {features['adl_slope']:.4f})")
        
        # Bonus: Her ikisi de yükseliyor
        if obv_rising and adl_rising and price_flat:
            score += 5
            reasons.append("OBV ve ADL aynı anda↑")
        
        # Normalize edilmiş slope büyüklüğüne göre ek puan
        obv_magnitude = abs(features['obv_slope'])
        adl_magnitude = abs(features['adl_slope'])
        
        if obv_rising and obv_magnitude > 0.01:  # Güçlü OBV artışı
            extra = min(3, obv_magnitude * 100)
            score += extra
        
        if adl_rising and adl_magnitude > 0.01:  # Güçlü ADL artışı
            extra = min(2, adl_magnitude * 100)
            score += extra
        
        return min(score, MAX_ACCUMULATION), reasons
    
    def score_volatility(self, features: dict) -> Tuple[float, list]:
        """
        V: Volatility Compression Skorlama (0-20)
        
        Mantık:
        - ATR ve BB Width düşük → sıkışma
        
        Args:
            features: extract_volatility_features() çıktısı
            
        Returns:
            (score, reasons): Score ve nedenleri
        """
        score = 0.0
        reasons = []
        
        atr_percentile = features['atr_percentile']
        bbw_percentile = features['bbw_percentile']
        
        # ATR düşük (alt %25)
        if atr_percentile <= COMPRESSION_PERCENTILE:
            score += 10
            reasons.append(f"ATR düşük (percentile: {atr_percentile:.1f})")
        
        # BB Width düşük
        if bbw_percentile <= COMPRESSION_PERCENTILE:
            score += 10
            reasons.append(f"BB Width düşük (percentile: {bbw_percentile:.1f})")
        
        # Çok düşük volatilite (alt %10)
        if atr_percentile <= 10 or bbw_percentile <= 10:
            score += 3
            reasons.append("Ekstrem sıkışma")
        
        return min(score, MAX_VOLATILITY), reasons
    
    def score_absorption(self, features: dict, price_change: float) -> Tuple[float, list]:
        """
        O: Order Book Absorption Skorlama (0-25)
        
        Mantık:
        - Ask tarafında lot azalıyor ama fiyat yükselmiyor → emilim
        - Bid tarafında stabil duruş
        
        Args:
            features: extract_absorption_features() çıktısı
            price_change: Son N dakikadaki fiyat değişimi (%)
            
        Returns:
            (score, reasons): Score ve nedenleri
        """
        score = 0.0
        reasons = []
        
        if not features:
            return 0.0, []
        
        ask_reduction = features['ask_reduction']
        bid_stability = features['bid_stability']
        
        # Ask azalıyor + fiyat stabil → absorption
        if ask_reduction < -ASK_REDUCTION_THRESHOLD:
            ask_score = min(15, abs(ask_reduction) * 50)  # Scale
            score += ask_score
            reasons.append(f"Ask lot azalması: {ask_reduction:.1%}")
            
            # Fiyat çok az hareket ettiyse ekstra puan
            if abs(price_change) < PRICE_STABILITY_THRESHOLD:
                score += 5
                reasons.append(f"Fiyat stabil: {price_change:.2%}")
        
        # Bid stability yüksek
        if bid_stability > 0.7:
            bid_score = min(10, bid_stability * 10)
            score += bid_score
            reasons.append(f"Bid stabilite: {bid_stability:.2f}")
        
        return min(score, MAX_ABSORPTION), reasons
    
    def score_flow(self, features: dict, price_change: float) -> Tuple[float, list]:
        """
        F: Flow Footprint Skorlama (0-15)
        
        Mantık:
        - Agresif alımlar var ama fiyat bastırılıyor
        
        Args:
            features: extract_flow_features() çıktısı
            price_change: Son N dakikadaki fiyat değişimi (%)
            
        Returns:
            (score, reasons): Score ve nedenleri
        """
        score = 0.0
        reasons = []
        
        if not features or features['buy_volume'] == 0:
            return 0.0, []
        
        net_delta_zscore = features['net_delta_zscore']
        aggressive_buying = features['aggressive_buying']
        
        # Agresif alım var
        if aggressive_buying:
            flow_score = min(10, abs(net_delta_zscore) * 2)
            score += flow_score
            reasons.append(f"Agresif alım: z-score {net_delta_zscore:.2f}")
            
            # Fiyat yatay/düşüyor → bastırılıyor
            if price_change < 0.005:  # %0.5'ten az artış
                score += 5
                reasons.append(f"Fiyat bastırılıyor: {price_change:.2%}")
        
        return min(score, MAX_FLOW), reasons
    
    def score_context(self, symbol: str, daily_stats: dict, 
                     kap_count: int = 0, social_ratio: float = 1.0) -> Tuple[float, list]:
        """
        C: Context Skorlama (0-10)
        
        Mantık:
        - Sosyal sessizlik
        - KAP yok
        - Küçük tahta / düşük likidite
        
        Args:
            symbol: Hisse kodu
            daily_stats: Günlük istatistikler
            kap_count: Son X gündeki KAP sayısı
            social_ratio: Sosyal medya konuşulma oranı (1.0 = normal)
            
        Returns:
            (score, reasons): Score ve nedenleri
        """
        score = 0.0
        reasons = []
        
        # Sosyal sessizlik
        if social_ratio < SOCIAL_SILENCE_THRESHOLD:
            score += 3
            reasons.append(f"Sosyal sessizlik: {social_ratio:.2f}")
        
        # KAP yok
        if kap_count == 0:
            score += 2
            reasons.append("Son günlerde KAP yok")
        
        # Küçük tahta / düşük likidite (proxy)
        volume_tl = daily_stats.get('volume_tl', 0)
        spread_pct = daily_stats.get('spread_pct', 0)
        
        if volume_tl < 50_000_000:  # 50M TL altı
            score += 3
            reasons.append(f"Düşük hacim: {volume_tl/1e6:.1f}M TL")
        
        if spread_pct > 1.0:  # Spread yüksek
            score += 2
            reasons.append(f"Geniş spread: {spread_pct:.2f}%")
        
        return min(score, MAX_CONTEXT), reasons
    
    def calculate_total_score(self, A: float, V: float, O: float, 
                            F: float, C: float) -> Tuple[float, str]:
        """
        Toplam PMR skorunu hesaplar ve etiket döner
        
        Args:
            A, V, O, F, C: Alt skorlar
            
        Returns:
            (total_score, label): Toplam skor ve risk etiketi
        """
        total = A + V + O + F + C
        
        if total >= SCORE_THRESHOLD_VERY_HIGH:
            label = "🔥 Hazırlık Çok Yüksek"
        elif total >= SCORE_THRESHOLD_HIGH:
            label = "🟠 Hazırlık Yüksek"
        elif total >= SCORE_THRESHOLD_MEDIUM:
            label = "🟡 Hazırlık Orta"
        else:
            label = "🟢 Düşük Risk"
        
        return total, label
    
    def check_false_positives(self, features_acc: dict, features_vol: dict,
                             features_abs: dict, features_flow: dict,
                             daily_stats: dict, kap_count: int) -> Tuple[bool, str]:
        """
        False Positive kontrolleri
        
        Returns:
            (is_fp, reason): False positive ise True ve nedeni
        """
        
        # FP-1: Normal sıkışma (divergence yok)
        if (features_vol['compressed'] and 
            not features_acc['obv_rising'] and 
            not features_acc['adl_rising'] and
            features_flow.get('net_delta_zscore', 0) < 1.0):
            return True, "Normal sıkışma (divergence yok)"
        
        # FP-2: Haber öncesi
        if kap_count > 2:  # Çok fazla KAP
            return True, "Yakın zamanda çok KAP (event-driven olabilir)"
        
        # FP-3: Likidite tuzağı
        volume_tl = daily_stats.get('volume_tl', 0)
        spread_pct = daily_stats.get('spread_pct', 0)
        
        if volume_tl < ILLIQUID_VOLUME_THRESHOLD or spread_pct > ILLIQUID_SPREAD_THRESHOLD:
            return True, f"İşlem yapılamaz likidite (vol: {volume_tl/1e6:.1f}M, spread: {spread_pct:.2f}%)"
        
        return False, ""


class RiskGuard:
    """Risk koruma ve filtreleme"""
    
    @staticmethod
    def check_liquidity(daily_stats: dict) -> Tuple[bool, str]:
        """
        Likidite kontrolü
        
        Returns:
            (tradeable, risk_note): İşlem yapılabilir mi, risk notu
        """
        volume_tl = daily_stats.get('volume_tl', 0)
        spread_pct = daily_stats.get('spread_pct', 0)
        
        if volume_tl < ILLIQUID_VOLUME_THRESHOLD:
            return False, f"⚫ ÇOK DÜŞÜK LİKİDİTE (işlem yasak)"
        
        if spread_pct > ILLIQUID_SPREAD_THRESHOLD:
            return False, f"⚫ GENİŞ SPREAD (işlem riskli)"
        
        if volume_tl < MIN_DAILY_VOLUME_TL:
            return True, "⚠️ Orta likidite (dikkatli ol)"
        
        return True, "✅ Likidite normal"
    
    @staticmethod
    def check_manipulation_started(bars_1m: 'pd.DataFrame', 
                                   avg_volume_1m: float) -> Tuple[bool, str]:
        """
        Manipülasyon başladı mı kontrolü
        
        Returns:
            (started, message): Başladıysa True ve mesaj
        """
        if bars_1m.empty or len(bars_1m) < 2:
            return False, ""
        
        # Son bar'ın hacmi
        last_volume = bars_1m.iloc[-1]['volume']
        
        # Fiyat değişimi
        price_change = (bars_1m.iloc[-1]['close'] - bars_1m.iloc[-2]['close']) / bars_1m.iloc[-2]['close']
        
        # Hacim spike
        if last_volume > avg_volume_1m * START_VOLUME_MULTIPLIER:
            if price_change > START_PRICE_CHANGE:
                return True, "⚠️ PATLAMA BAŞLADI! Hacim spike + fiyat +%1"
        
        return False, ""
