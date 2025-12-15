"""
BIST PMR v1.0 - Teknik İndikatörler ve Feature Hesaplama
OBV, ADL, ATR, Bollinger Bands, Slope hesaplamaları
"""

import pandas as pd
import numpy as np
from typing import Tuple
from .config import *


class TechnicalIndicators:
    """Teknik indikatörler sınıfı"""
    
    @staticmethod
    def calculate_obv(df: pd.DataFrame) -> pd.Series:
        """
        On Balance Volume (OBV)
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            Series: OBV değerleri
        """
        if df.empty or 'close' not in df.columns or 'volume' not in df.columns:
            return pd.Series()
        
        obv = pd.Series(index=df.index, dtype=float)
        obv.iloc[0] = df['volume'].iloc[0]
        
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['close'].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + df['volume'].iloc[i]
            elif df['close'].iloc[i] < df['close'].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - df['volume'].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        
        return obv
    
    @staticmethod
    def calculate_adl(df: pd.DataFrame) -> pd.Series:
        """
        Accumulation/Distribution Line (ADL)
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            Series: ADL değerleri
        """
        if df.empty:
            return pd.Series()
        
        # Money Flow Multiplier
        clv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        clv = clv.fillna(0)
        
        # Money Flow Volume
        mfv = clv * df['volume']
        
        # ADL = cumulative MFV
        adl = mfv.cumsum()
        
        return adl
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Average True Range (ATR)
        
        Args:
            df: OHLCV DataFrame
            period: Periyod (default: 14)
            
        Returns:
            Series: ATR değerleri
        """
        if df.empty or len(df) < period:
            return pd.Series()
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range hesapla
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR = TR'nin hareketli ortalaması
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, 
                                  std: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands
        
        Args:
            df: OHLCV DataFrame
            period: Periyod (default: 20)
            std: Standart sapma çarpanı (default: 2)
            
        Returns:
            Tuple: (upper, middle, lower) bantlar
        """
        if df.empty or len(df) < period:
            return pd.Series(), pd.Series(), pd.Series()
        
        middle = df['close'].rolling(window=period).mean()
        rolling_std = df['close'].rolling(window=period).std()
        
        upper = middle + (rolling_std * std)
        lower = middle - (rolling_std * std)
        
        return upper, middle, lower
    
    @staticmethod
    def calculate_bb_width(df: pd.DataFrame, period: int = 20, std: float = 2) -> pd.Series:
        """
        Bollinger Band Width (sıkışma ölçütü)
        
        Args:
            df: OHLCV DataFrame
            period: Periyod
            std: Standart sapma çarpanı
            
        Returns:
            Series: BB Width değerleri
        """
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(df, period, std)
        
        if middle.empty:
            return pd.Series()
        
        bbw = (upper - lower) / middle
        return bbw
    
    @staticmethod
    def calculate_slope(series: pd.Series, normalize: bool = True) -> float:
        """
        Linear regression slope hesaplar
        
        Args:
            series: Zaman serisi
            normalize: Slope'u normalize et (son değere böl)
            
        Returns:
            float: Slope değeri
        """
        if series.empty or len(series) < 2:
            return 0.0
        
        # NaN'leri temizle
        clean_series = series.dropna()
        if len(clean_series) < 2:
            return 0.0
        
        x = np.arange(len(clean_series))
        y = clean_series.values
        
        # Linear regression
        if len(x) < 2:
            return 0.0
        
        slope, _ = np.polyfit(x, y, 1)
        
        if normalize and clean_series.iloc[-1] != 0:
            slope = slope / abs(clean_series.iloc[-1])
        
        return float(slope)
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Relative Strength Index (RSI)
        
        Args:
            df: OHLCV DataFrame
            period: Periyod
            
        Returns:
            Series: RSI değerleri
        """
        if df.empty or len(df) < period + 1:
            return pd.Series()
        
        delta = df['close'].diff()
        
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_percentile_rank(series: pd.Series, lookback: int = 20) -> float:
        """
        Son değerin lookback periyodundaki percentile rank'ini hesaplar
        
        Args:
            series: Zaman serisi
            lookback: Kaç bar geriye bakılacak
            
        Returns:
            float: 0-100 arası percentile (50 = median)
        """
        if series.empty or len(series) < lookback:
            return 50.0  # Default median
        
        recent = series.tail(lookback)
        last_value = recent.iloc[-1]
        
        if pd.isna(last_value):
            return 50.0
        
        rank = (recent < last_value).sum() / len(recent) * 100
        
        return float(rank)


class FeatureExtractor:
    """Feature çıkarım sınıfı"""
    
    def __init__(self):
        self.ti = TechnicalIndicators()
    
    def extract_accumulation_features(self, df_5m: pd.DataFrame) -> dict:
        """
        Accumulation divergence feature'ları çıkarır
        
        Args:
            df_5m: 5 dakikalık OHLCV DataFrame
            
        Returns:
            dict: {
                'price_slope': float,
                'obv_slope': float,
                'adl_slope': float,
                'price_flat': bool,
                'obv_rising': bool,
                'adl_rising': bool
            }
        """
        if df_5m.empty:
            return self._empty_accumulation_features()
        
        # İndikatörleri hesapla
        obv = self.ti.calculate_obv(df_5m)
        adl = self.ti.calculate_adl(df_5m)
        
        # Slope'ları hesapla
        price_slope = self.ti.calculate_slope(df_5m['close'])
        obv_slope = self.ti.calculate_slope(obv)
        adl_slope = self.ti.calculate_slope(adl)
        
        # Boolean bayraklar
        price_flat = abs(price_slope) < PRICE_FLAT_THRESHOLD
        obv_rising = obv_slope > 0
        adl_rising = adl_slope > 0
        
        return {
            'price_slope': price_slope,
            'obv_slope': obv_slope,
            'adl_slope': adl_slope,
            'price_flat': price_flat,
            'obv_rising': obv_rising,
            'adl_rising': adl_rising
        }
    
    def extract_volatility_features(self, df_5m: pd.DataFrame, 
                                   df_daily: pd.DataFrame) -> dict:
        """
        Volatilite sıkışması feature'ları çıkarır
        
        Args:
            df_5m: 5 dakikalık OHLCV
            df_daily: Günlük OHLCV
            
        Returns:
            dict: {
                'atr_pct': float,
                'atr_percentile': float,
                'bbw': float,
                'bbw_percentile': float,
                'compressed': bool
            }
        """
        if df_5m.empty or df_daily.empty:
            return self._empty_volatility_features()
        
        # ATR hesapla (5m üzerinden)
        atr = self.ti.calculate_atr(df_5m, ATR_PERIOD)
        if atr.empty or df_5m['close'].iloc[-1] == 0:
            return self._empty_volatility_features()
        
        atr_pct = (atr.iloc[-1] / df_5m['close'].iloc[-1]) * 100
        
        # BB Width hesapla
        bbw = self.ti.calculate_bb_width(df_5m, BB_PERIOD, BB_STD)
        if bbw.empty:
            return self._empty_volatility_features()
        
        current_bbw = bbw.iloc[-1]
        
        # Günlük ATR ile karşılaştırma için
        daily_atr = self.ti.calculate_atr(df_daily, ATR_PERIOD)
        daily_atr_pct = (daily_atr / df_daily['close']) * 100
        
        atr_percentile = self.ti.calculate_percentile_rank(daily_atr_pct, 20)
        
        # BBW percentile
        bbw_percentile = self.ti.calculate_percentile_rank(bbw, 20)
        
        # Sıkışma var mı?
        compressed = (atr_percentile < COMPRESSION_PERCENTILE or 
                     bbw_percentile < COMPRESSION_PERCENTILE)
        
        return {
            'atr_pct': float(atr_pct),
            'atr_percentile': float(atr_percentile),
            'bbw': float(current_bbw) if not pd.isna(current_bbw) else 0.0,
            'bbw_percentile': float(bbw_percentile),
            'compressed': compressed
        }
    
    def extract_absorption_features(self, ob_history: list) -> dict:
        """
        Order book absorption feature'ları çıkarır
        
        Args:
            ob_history: [(timestamp, snapshot), ...] OrderBookTracker'dan
            
        Returns:
            dict: {
                'ask_reduction': float,
                'bid_stability': float,
                'absorption_detected': bool
            }
        """
        if not ob_history or len(ob_history) < 2:
            return {
                'ask_reduction': 0.0,
                'bid_stability': 0.0,
                'absorption_detected': False
            }
        
        # Ask reduction hesapla
        first_asks = sum(size for price, size in ob_history[0][1]['asks'])
        last_asks = sum(size for price, size in ob_history[-1][1]['asks'])
        
        ask_reduction = (last_asks - first_asks) / first_asks if first_asks > 0 else 0.0
        
        # Bid stability hesapla
        bid_prices = [snapshot['bids'][0][0] if snapshot['bids'] else 0 
                     for _, snapshot in ob_history]
        bid_std = np.std(bid_prices)
        bid_mean = np.mean(bid_prices)
        bid_stability = 1 - (bid_std / bid_mean) if bid_mean > 0 else 0
        bid_stability = max(0, min(1, bid_stability))
        
        # Absorption algılandı mı?
        absorption_detected = (ask_reduction < -ASK_REDUCTION_THRESHOLD and 
                              bid_stability > 0.7)
        
        return {
            'ask_reduction': float(ask_reduction),
            'bid_stability': float(bid_stability),
            'absorption_detected': absorption_detected
        }
    
    def extract_flow_features(self, prints_df: pd.DataFrame) -> dict:
        """
        Trade flow (işlem akışı) feature'ları çıkarır
        
        Args:
            prints_df: Trade prints DataFrame
            
        Returns:
            dict: {
                'buy_volume': float,
                'sell_volume': float,
                'net_delta': float,
                'net_delta_zscore': float,
                'aggressive_buying': bool
            }
        """
        if prints_df.empty:
            return {
                'buy_volume': 0.0,
                'sell_volume': 0.0,
                'net_delta': 0.0,
                'net_delta_zscore': 0.0,
                'aggressive_buying': False
            }
        
        # Buy/sell volume'leri topla
        buy_volume = prints_df[prints_df['side'] == 'buy']['size'].sum()
        sell_volume = prints_df[prints_df['side'] == 'sell']['size'].sum()
        
        net_delta = buy_volume - sell_volume
        
        # Z-score hesapla (basit versiyon)
        total_volume = buy_volume + sell_volume
        if total_volume > 0:
            net_delta_pct = net_delta / total_volume
            # Basit z-score proxy (gerçekte rolling std gerekir)
            net_delta_zscore = net_delta_pct * 10  # Scaled
        else:
            net_delta_zscore = 0.0
        
        # Agresif alım var mı?
        aggressive_buying = net_delta_zscore > FLOW_SIGMA_THRESHOLD
        
        return {
            'buy_volume': float(buy_volume),
            'sell_volume': float(sell_volume),
            'net_delta': float(net_delta),
            'net_delta_zscore': float(net_delta_zscore),
            'aggressive_buying': aggressive_buying
        }
    
    def _empty_accumulation_features(self) -> dict:
        return {
            'price_slope': 0.0,
            'obv_slope': 0.0,
            'adl_slope': 0.0,
            'price_flat': False,
            'obv_rising': False,
            'adl_rising': False
        }
    
    def _empty_volatility_features(self) -> dict:
        return {
            'atr_pct': 0.0,
            'atr_percentile': 50.0,
            'bbw': 0.0,
            'bbw_percentile': 50.0,
            'compressed': False
        }
