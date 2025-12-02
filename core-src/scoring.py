"""
BİST Trading Bot - Scoring Engine Module
Skor ve karar motoru - her bloğu puanlayıp sinyal seviyesi belirler
"""

from typing import Dict, List
import logging

import config

logger = logging.getLogger(__name__)


def score_trend(indicators: Dict) -> tuple:
    """
    Trend bloğu puanlaması
    
    Args:
        indicators: Trend indikatörleri dict
        
    Returns:
        tuple: (skor, tetiklenen kriterler listesi)
    """
    score = 0
    triggered = []
    
    try:
        ma_short = indicators.get('ma_short')
        ma_medium = indicators.get('ma_medium')
        ma_long = indicators.get('ma_long')
        current_price = indicators.get('current_price')
        
        # Kriter 1: MA10 > MA20 > MA50 (Golden Cross benzeri)
        if ma_short and ma_medium and ma_long:
            if ma_short > ma_medium > ma_long:
                score += 2
                triggered.append("MA10 > MA20 > MA50 (Güçlü yükseliş trendi)")
        
        # Kriter 2: Fiyat MA20 üstünde
        if current_price and ma_medium:
            if current_price > ma_medium:
                score += 1
                triggered.append(f"Fiyat MA20 üstünde ({current_price:.2f} > {ma_medium:.2f})")
        
        # Kriter 3: MACD pozitif ve histogram pozitif
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_histogram = indicators.get('macd_histogram')
        
        if macd_line and macd_signal and macd_histogram:
            if macd_line > macd_signal and macd_histogram > 0:
                score += 1
                triggered.append("MACD pozitif (alış sinyali)")
        
        # Kriter 4: ADX > 20 ve DI+ > DI-
        adx = indicators.get('adx')
        plus_di = indicators.get('plus_di')
        minus_di = indicators.get('minus_di')
        
        if adx and plus_di and minus_di:
            if adx > config.ADX_TREND_THRESHOLD and plus_di > minus_di:
                score += 1
                triggered.append(f"ADX güçlü ({adx:.1f}) ve DI+ > DI-")
        
        # Kriter 5: Trend yapısı (Higher High & Higher Low)
        if indicators.get('trend_structure_bullish'):
            score += 1
            triggered.append("Yükseliş trend yapısı (HH & HL)")
        
        return min(score, config.MAX_TREND_SCORE), triggered
        
    except Exception as e:
        logger.error(f"Trend skorlama hatası: {str(e)}")
        return 0, []


def score_momentum(indicators: Dict) -> tuple:
    """
    Momentum bloğu puanlaması
    
    Args:
        indicators: Momentum indikatörleri dict
        
    Returns:
        tuple: (skor, tetiklenen kriterler listesi)
    """
    score = 0
    triggered = []
    
    try:
        rsi = indicators.get('rsi')
        
        # Kriter 1: RSI sağlıklı bölgede (50-70)
        if rsi:
            if config.RSI_HEALTHY_MIN <= rsi <= config.RSI_HEALTHY_MAX:
                score += 1
                triggered.append(f"RSI sağlıklı bölgede ({rsi:.1f})")
        
        # Kriter 2: RSI aşırı satımdan dönüyor
        if rsi and indicators.get('rsi_rising'):
            if rsi < config.RSI_OVERSOLD:
                score += 1
                triggered.append(f"RSI aşırı satımdan yükseliyor ({rsi:.1f})")
        
        # Kriter 3: Stochastic yukarı kesiyor
        if indicators.get('stoch_bullish_cross'):
            score += 1
            triggered.append("Stochastic yukarı kesişim")
        
        # Kriter 4: Stochastic aşırı satımda
        if indicators.get('stoch_oversold') and indicators.get('stoch_bullish_cross'):
            score += 1
            triggered.append("Stochastic aşırı satımdan dönüş")
        
        # Kriter 5: Momentum pozitif
        if indicators.get('momentum_positive'):
            momentum = indicators.get('momentum')
            score += 1
            triggered.append(f"Pozitif momentum ({momentum:.2f}%)")
        
        return min(score, config.MAX_MOMENTUM_SCORE), triggered
        
    except Exception as e:
        logger.error(f"Momentum skorlama hatası: {str(e)}")
        return 0, []


def score_volume(indicators: Dict) -> tuple:
    """
    Hacim bloğu puanlaması
    
    Args:
        indicators: Hacim indikatörleri dict
        
    Returns:
        tuple: (skor, tetiklenen kriterler listesi)
    """
    score = 0
    triggered = []
    
    try:
        volume_ratio = indicators.get('volume_ratio', 0)
        
        # Kriter 1: Hacim ortalamanın 1.5x'i
        if volume_ratio >= 1.5:
            score += 2
            triggered.append(f"Hacim spike ({volume_ratio:.2f}x ortalama)")
        elif volume_ratio >= 1.0:
            score += 1
            triggered.append(f"Hacim normal üstü ({volume_ratio:.2f}x)")
        
        # Kriter 2: OBV yükseliş trendinde
        if indicators.get('obv_rising'):
            score += 1
            triggered.append("OBV yükseliş trendinde")
        
        # Kriter 3: Günlük hacim yeterli
        daily_volume_tl = indicators.get('daily_volume_tl', 0)
        if daily_volume_tl > config.MIN_DAILY_TL_VOLUME * 2:
            score += 1
            triggered.append(f"Yüksek günlük hacim ({daily_volume_tl/1e6:.1f}M TL)")
        
        # Kriter 4: Volume spike + pozitif fiyat hareketi
        if indicators.get('volume_spike'):
            score += 1
            triggered.append("Hacim patlaması tespit edildi")
        
        return min(score, config.MAX_VOLUME_SCORE), triggered
        
    except Exception as e:
        logger.error(f"Hacim skorlama hatası: {str(e)}")
        return 0, []


def score_fundamental_pa(pa_indicators: Dict, fundamentals: Dict = None) -> tuple:
    """
    Temel analiz + Price Action bloğu puanlaması
    
    Args:
        pa_indicators: Price action indikatörleri dict
        fundamentals: Temel analiz verileri dict (opsiyonel)
        
    Returns:
        tuple: (skor, tetiklenen kriterler listesi)
    """
    score = 0
    triggered = []
    
    try:
        # === PRICE ACTION PUANLARI ===
        
        # Kriter 1: Güçlü yeşil mum
        if pa_indicators.get('strong_green_candle'):
            score += 1
            close_pos = pa_indicators.get('close_position', 0)
            triggered.append(f"Güçlü yeşil mum (kapanış %{close_pos*100:.0f})")
        
        # Kriter 2: Uzun alt fitil (dip toplama)
        if pa_indicators.get('long_lower_wick'):
            score += 1
            triggered.append("Uzun alt fitil (dip toplama sinyali)")
        
        # Kriter 3: Son günlerde collapse yok
        if not pa_indicators.get('has_collapse'):
            score += 1
            triggered.append("Son günlerde sert düşüş yok")
        
        # Kriter 4: Breakout (direnç kırılımı)
        if pa_indicators.get('breakout'):
            score += 1
            triggered.append("Direnç kırılımı (hacimle)")
        
        # === TEMEL ANALİZ PUANLARI (OPSIYONEL) ===
        
        if fundamentals:
            # Kriter 5: F/K oranı makul
            pe_ratio = fundamentals.get('pe_ratio')
            if pe_ratio:
                if config.MIN_PE_RATIO < pe_ratio < config.MAX_PE_RATIO:
                    score += 1
                    triggered.append(f"F/K oranı makul ({pe_ratio:.1f})")
            
            # Kriter 6: PD/DD oranı iyi
            pb_ratio = fundamentals.get('pb_ratio')
            if pb_ratio:
                if 0 < pb_ratio < config.MAX_PB_RATIO:
                    score += 1
                    triggered.append(f"PD/DD oranı iyi ({pb_ratio:.2f})")
        
        return min(score, config.MAX_FUNDAMENTAL_PA_SCORE), triggered
        
    except Exception as e:
        logger.error(f"Temel/PA skorlama hatası: {str(e)}")
        return 0, []


def calculate_total_score(symbol: str, 
                         trend_indicators: Dict,
                         momentum_indicators: Dict,
                         volume_indicators: Dict,
                         pa_indicators: Dict,
                         fundamentals: Dict = None) -> Dict:
    """
    Tüm blokları hesaplayıp toplam skoru ve sinyal seviyesini belirler
    
    Args:
        symbol: Hisse sembolü
        trend_indicators: Trend indikatörleri
        momentum_indicators: Momentum indikatörleri
        volume_indicators: Hacim indikatörleri
        pa_indicators: Price action indikatörleri
        fundamentals: Temel analiz verileri (opsiyonel)
        
    Returns:
        dict: Toplam skor ve detaylar
    """
    try:
        # Her bloğu puanla
        trend_score, trend_criteria = score_trend(trend_indicators)
        momentum_score, momentum_criteria = score_momentum(momentum_indicators)
        volume_score, volume_criteria = score_volume(volume_indicators)
        fundamental_pa_score, fundamental_pa_criteria = score_fundamental_pa(pa_indicators, fundamentals)
        
        # Toplam skor
        total_score = trend_score + momentum_score + volume_score + fundamental_pa_score
        
        # Sinyal seviyesi belirle
        if total_score >= config.ULTRA_BUY_THRESHOLD:
            signal_level = "ULTRA_BUY"
        elif total_score >= config.STRONG_BUY_THRESHOLD:
            signal_level = "STRONG_BUY"
        elif total_score >= config.WATCHLIST_THRESHOLD:
            signal_level = "WATCHLIST"
        else:
            signal_level = "NO_SIGNAL"
        
        # Tüm tetiklenen kriterleri birleştir
        all_triggered_criteria = (
            trend_criteria + 
            momentum_criteria + 
            volume_criteria + 
            fundamental_pa_criteria
        )
        
        return {
            'symbol': symbol,
            'total_score': total_score,
            'trend_score': trend_score,
            'momentum_score': momentum_score,
            'volume_score': volume_score,
            'fundamental_pa_score': fundamental_pa_score,
            'signal_level': signal_level,
            'triggered_criteria': all_triggered_criteria,
            'max_possible_score': (
                config.MAX_TREND_SCORE + 
                config.MAX_MOMENTUM_SCORE + 
                config.MAX_VOLUME_SCORE + 
                config.MAX_FUNDAMENTAL_PA_SCORE
            )
        }
        
    except Exception as e:
        logger.error(f"Toplam skor hesaplama hatası ({symbol}): {str(e)}")
        return {
            'symbol': symbol,
            'total_score': 0,
            'signal_level': 'ERROR',
            'triggered_criteria': [],
            'error': str(e)
        }