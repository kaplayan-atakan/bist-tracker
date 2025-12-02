"""
BİST Trading Bot - Technical Indicators Module
Teknik analiz göstergelerini hesaplayan modül
"""

import pandas as pd
import numpy as np
from typing import Dict
import logging

import config

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Teknik indikatörleri hesaplayan sınıf"""
    
    @staticmethod
    def calculate_sma(data: pd.Series, period: int) -> pd.Series:
        """Basit hareketli ortalama"""
        return data.rolling(window=period).mean()
    
    @staticmethod
    def calculate_ema(data: pd.Series, period: int) -> pd.Series:
        """Üssel hareketli ortalama"""
        return data.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """MACD göstergesi"""
        ema_fast = data.ewm(span=fast, adjust=False).mean()
        ema_slow = data.ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    @staticmethod
    def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Dict:
        """Average Directional Index"""
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        # Directional Movement
        up_move = high - high.shift()
        down_move = low.shift() - low
        
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
        
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }
    
    @staticmethod
    def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, 
                            k_period: int = 14, d_period: int = 3) -> Dict:
        """Stochastic Oscillator"""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k_line = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d_line = k_line.rolling(window=d_period).mean()
        
        return {
            'k': k_line,
            'd': d_line
        }
    
    @staticmethod
    def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """On Balance Volume"""
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        return obv
    
    @staticmethod
    def calculate_bollinger_bands(data: pd.Series, period: int = 20, std_dev: int = 2) -> Dict:
        """Bollinger Bands"""
        sma = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        }
    
    @staticmethod
    def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Average True Range"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr


def calculate_trend_indicators(ohlcv: pd.DataFrame) -> Dict:
    """
    Trend bloğu için indikatörleri hesaplar
    
    Args:
        ohlcv: OHLCV DataFrame
        
    Returns:
        dict: Trend indikatörleri
    """
    try:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        
        indicators = TechnicalIndicators()
        
        # Hareketli ortalamalar
        ma_short = indicators.calculate_sma(close, config.MA_SHORT)
        ma_medium = indicators.calculate_sma(close, config.MA_MEDIUM)
        ma_long = indicators.calculate_sma(close, config.MA_LONG)
        
        # MACD
        macd = indicators.calculate_macd(close, config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL)
        
        # ADX
        adx = indicators.calculate_adx(high, low, close, config.ADX_PERIOD)
        
        # Son değerler
        current_price = close.iloc[-1]
        
        # Trend yapısı kontrolü (Higher High, Higher Low)
        recent_highs = high.iloc[-10:].values
        recent_lows = low.iloc[-10:].values
        
        higher_highs = sum(recent_highs[i] > recent_highs[i-1] for i in range(1, len(recent_highs)))
        higher_lows = sum(recent_lows[i] > recent_lows[i-1] for i in range(1, len(recent_lows)))
        
        trend_structure_bullish = (higher_highs >= 5) and (higher_lows >= 5)
        
        return {
            'ma_short': ma_short.iloc[-1] if not ma_short.empty else None,
            'ma_medium': ma_medium.iloc[-1] if not ma_medium.empty else None,
            'ma_long': ma_long.iloc[-1] if not ma_long.empty else None,
            'current_price': current_price,
            'macd_line': macd['macd'].iloc[-1] if not macd['macd'].empty else None,
            'macd_signal': macd['signal'].iloc[-1] if not macd['signal'].empty else None,
            'macd_histogram': macd['histogram'].iloc[-1] if not macd['histogram'].empty else None,
            'adx': adx['adx'].iloc[-1] if not adx['adx'].empty else None,
            'plus_di': adx['plus_di'].iloc[-1] if not adx['plus_di'].empty else None,
            'minus_di': adx['minus_di'].iloc[-1] if not adx['minus_di'].empty else None,
            'trend_structure_bullish': trend_structure_bullish
        }
        
    except Exception as e:
        logger.error(f"Trend indikatör hesaplama hatası: {str(e)}")
        return {}


def calculate_momentum_indicators(ohlcv: pd.DataFrame) -> Dict:
    """
    Momentum bloğu için indikatörleri hesaplar
    
    Args:
        ohlcv: OHLCV DataFrame
        
    Returns:
        dict: Momentum indikatörleri
    """
    try:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        
        indicators = TechnicalIndicators()
        
        # RSI
        rsi = indicators.calculate_rsi(close, config.RSI_PERIOD)
        
        # Stochastic
        stoch = indicators.calculate_stochastic(high, low, close, 
                                                config.STOCH_K_PERIOD, 
                                                config.STOCH_D_PERIOD)
        
        # Momentum (Rate of Change)
        momentum = close.pct_change(periods=10) * 100
        
        # RSI trend
        rsi_values = rsi.iloc[-5:].values
        rsi_rising = sum(rsi_values[i] > rsi_values[i-1] for i in range(1, len(rsi_values))) >= 3
        
        # Stochastic çapraz kontrol
        stoch_k_current = stoch['k'].iloc[-1]
        stoch_d_current = stoch['d'].iloc[-1]
        stoch_k_prev = stoch['k'].iloc[-2]
        stoch_d_prev = stoch['d'].iloc[-2]
        
        stoch_bullish_cross = (stoch_k_prev < stoch_d_prev) and (stoch_k_current > stoch_d_current)
        stoch_oversold = stoch_k_current < config.STOCH_OVERSOLD
        
        return {
            'rsi': rsi.iloc[-1] if not rsi.empty else None,
            'rsi_rising': rsi_rising,
            'stoch_k': stoch_k_current if not pd.isna(stoch_k_current) else None,
            'stoch_d': stoch_d_current if not pd.isna(stoch_d_current) else None,
            'stoch_bullish_cross': stoch_bullish_cross,
            'stoch_oversold': stoch_oversold,
            'momentum': momentum.iloc[-1] if not momentum.empty else None,
            'momentum_positive': momentum.iloc[-1] > 0 if not momentum.empty else False
        }
        
    except Exception as e:
        logger.error(f"Momentum indikatör hesaplama hatası: {str(e)}")
        return {}


def calculate_volume_indicators(ohlcv: pd.DataFrame) -> Dict:
    """
    Hacim bloğu için indikatörleri hesaplar
    
    Args:
        ohlcv: OHLCV DataFrame
        
    Returns:
        dict: Hacim indikatörleri
    """
    try:
        close = ohlcv['close']
        volume = ohlcv['volume']
        
        indicators = TechnicalIndicators()
        
        # Hacim ortalaması
        volume_ma = volume.rolling(window=config.VOLUME_MA_PERIOD).mean()
        
        # Güncel hacim / ortalama hacim
        current_volume = volume.iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # OBV
        obv = indicators.calculate_obv(close, volume)
        
        # OBV trend (son 10 bar)
        obv_values = obv.iloc[-config.OBV_TREND_PERIOD:].values
        obv_rising = sum(obv_values[i] > obv_values[i-1] for i in range(1, len(obv_values))) >= 6
        
        # Günlük hacim (TL)
        daily_volume_tl = current_volume * close.iloc[-1]
        
        return {
            'current_volume': current_volume,
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'daily_volume_tl': daily_volume_tl,
            'obv': obv.iloc[-1] if not obv.empty else None,
            'obv_rising': obv_rising,
            'volume_spike': volume_ratio > config.VOLUME_SPIKE_THRESHOLD
        }
        
    except Exception as e:
        logger.error(f"Hacim indikatör hesaplama hatası: {str(e)}")
        return {}


def calculate_price_action_features(ohlcv: pd.DataFrame) -> Dict:
    """
    Price Action bloğu için özellikleri hesaplar
    
    Args:
        ohlcv: OHLCV DataFrame
        
    Returns:
        dict: Price action özellikleri
    """
    try:
        # Son bar (bugün)
        last_bar = ohlcv.iloc[-1]
        
        open_price = last_bar['open']
        high_price = last_bar['high']
        low_price = last_bar['low']
        close_price = last_bar['close']
        
        # Günlük range
        daily_range = high_price - low_price
        
        # Kapanış pozisyonu (range içinde nerede?)
        if daily_range > 0:
            close_position = (close_price - low_price) / daily_range
        else:
            close_position = 0.5
        
        # Güçlü yeşil mum kontrolü
        strong_green_candle = (close_price > open_price) and (close_position >= config.STRONG_GREEN_THRESHOLD)
        
        # Gövde ve fitiller
        body = abs(close_price - open_price)
        upper_wick = high_price - max(open_price, close_price)
        lower_wick = min(open_price, close_price) - low_price
        
        # Uzun alt fitil kontrolü
        long_lower_wick = False
        if body > 0:
            long_lower_wick = (lower_wick / body) >= config.LOWER_WICK_RATIO
        
        # Collapse kontrolü (son N günde büyük düşüş var mı?)
        recent_changes = ohlcv['close'].pct_change().iloc[-config.COLLAPSE_CHECK_DAYS:] * 100
        has_collapse = any(recent_changes < config.COLLAPSE_THRESHOLD_PERCENT)
        
        # Breakout kontrolü (basit: fiyat MA50'yi hacimle kırmış mı?)
        ma50 = ohlcv['close'].rolling(window=50).mean()
        prev_close = ohlcv['close'].iloc[-2]
        prev_ma50 = ma50.iloc[-2]
        current_ma50 = ma50.iloc[-1]
        
        volume_current = ohlcv['volume'].iloc[-1]
        volume_avg = ohlcv['volume'].rolling(window=20).mean().iloc[-1]
        
        breakout = False
        if not pd.isna(prev_ma50) and not pd.isna(current_ma50):
            if (prev_close < prev_ma50) and (close_price > current_ma50):
                if volume_current > volume_avg * config.BREAKOUT_VOLUME_MULTIPLIER:
                    breakout = True
        
        return {
            'close_position': close_position,
            'strong_green_candle': strong_green_candle,
            'body': body,
            'upper_wick': upper_wick,
            'lower_wick': lower_wick,
            'long_lower_wick': long_lower_wick,
            'has_collapse': has_collapse,
            'breakout': breakout,
            'daily_range': daily_range,
            'candle_type': 'green' if close_price > open_price else 'red'
        }
        
    except Exception as e:
        logger.error(f"Price action hesaplama hatası: {str(e)}")
        return {}