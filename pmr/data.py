"""
BIST PMR v1.0 - Veri Yönetim Modülü
OHLCV, L2 Order Book, Trade Prints verilerini çeker
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
import yfinance as yf
from .config import *


class DataProvider:
    """Veri sağlayıcı - gerçek API'lerle değiştirilebilir"""
    
    def __init__(self, source: str = None):
        self.source = source or DATA_SOURCE
        
    def get_ohlcv(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        """
        OHLCV verisi çeker
        
        Args:
            symbol: Hisse kodu (ör: "THYAO")
            timeframe: "1m", "5m", "1d"
            bars: Kaç bar geriye gidilecek
            
        Returns:
            DataFrame: columns=[timestamp, open, high, low, close, volume]
        """
        if self.source == "mock":
            return self._mock_ohlcv(symbol, timeframe, bars)
        elif self.source == "api":
            return self._api_ohlcv(symbol, timeframe, bars)
        elif self.source == "yfinance":
            return self._yfinance_ohlcv(symbol, timeframe, bars)
        else:
            raise ValueError(f"Unknown source: {self.source}")
    
    def get_orderbook_snapshot(self, symbol: str, depth: int = 5) -> Dict:
        """
        L2 Order Book snapshot çeker
        
        Args:
            symbol: Hisse kodu
            depth: Kaç kademe (bid/ask)
            
        Returns:
            dict: {
                'bids': [(price, size), ...],
                'asks': [(price, size), ...],
                'timestamp': datetime
            }
        """
        if self.source == "mock":
            return self._mock_orderbook(symbol, depth)
        elif self.source == "api":
            return self._api_orderbook(symbol, depth)
        else:
            return None
    
    def get_trade_prints(self, symbol: str, minutes: int = 10) -> pd.DataFrame:
        """
        Trade prints (işlem akışı) çeker
        
        Args:
            symbol: Hisse kodu
            minutes: Son kaç dakika
            
        Returns:
            DataFrame: columns=[timestamp, price, size, side (buy/sell estimate)]
        """
        if self.source == "mock":
            return self._mock_prints(symbol, minutes)
        elif self.source == "api":
            return self._api_prints(symbol, minutes)
        else:
            return pd.DataFrame()
    
    def get_universe(self) -> List[str]:
        """Taranacak hisse listesini döner (likidite filtreli)"""
        if self.source == "mock":
            # Mock evren - gerçekte tüm BIST hisseleri
            return ["THYAO", "GARAN", "ISCTR", "SISE", "PETKM", 
                    "EREGL", "AKBNK", "KCHOL", "SAHOL", "TUPRS",
                    "SMALLCAP1", "SMALLCAP2"]  # Son ikisi küçük tahta simülasyonu
        elif self.source == "api":
            return self._api_universe()
        elif self.source == "yfinance":
            # Try to load from bist_symbols_validated.json
            # Proje kök dizininde ara
            possible_paths = [
                "bist_symbols_validated.json",
                "../bist_symbols_validated.json",
                os.path.join(os.getcwd(), "bist_symbols_validated.json")
            ]
            
            for json_path in possible_paths:
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if "stocks" in data:
                                print(f"[PMR] Evren yüklendi: {len(data['stocks'])} hisse ({json_path})")
                                return data["stocks"]
                    except Exception as e:
                        print(f"[PMR] JSON yükleme hatası ({json_path}): {e}")
            
            # Fallback to hardcoded list
            print("[PMR] Uyarı: JSON bulunamadı, varsayılan liste kullanılıyor.")
            return ["THYAO", "GARAN", "ISCTR", "SISE", "PETKM", 
                    "EREGL", "AKBNK", "KCHOL", "SAHOL", "TUPRS",
                    "ASELS", "BIMAS", "EKGYO", "FROTO", "HEKTS",
                    "KOZAL", "KOZAA", "KRDMD", "ODAS", "PGSUS",
                    "SASA", "TCELL", "TKFEN", "TOASO", "TTKOM",
                    "VESTL", "YKBNK"]
        else:
            return []
    
    def get_daily_stats(self, symbol: str) -> Dict:
        """Günlük istatistikler (hacim, spread, vb.)"""
        # 20 günlük veri çek (ortalama hacim için)
        daily = self.get_ohlcv(symbol, "1d", 20)
        if daily.empty:
            return {}
        
        # Son gün verisi
        last_bar = daily.iloc[-1]
        
        # Ortalama hacim (TL)
        daily_vol_tl = daily['volume'] * daily['close']
        avg_vol_20d = daily_vol_tl.mean()
        
        stats = {
            'volume_tl': last_bar['volume'] * last_bar['close'],
            'avg_volume_20d': avg_vol_20d,
            'last_price': last_bar['close'],
            'spread_pct': 0.0
        }
        
        if self.source == "mock":
            stats['spread_pct'] = 0.5
            
        return stats
    
    # ==================== MOCK IMPLEMENTATIONS ====================
    
    def _mock_ohlcv(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        """Mock OHLCV data generator"""
        np.random.seed(hash(symbol) % 10000)
        
        # Timeframe'e göre başlangıç
        if timeframe == "1m":
            freq = "1min"
            end = datetime.now()
        elif timeframe == "5m":
            freq = "5min"
            end = datetime.now()
        elif timeframe == "1d":
            freq = "1D"
            end = datetime.now()
        else:
            raise ValueError(f"Unknown timeframe: {timeframe}")
        
        # Tarih aralığı
        dates = pd.date_range(end=end, periods=bars, freq=freq)
        
        # Base fiyat
        base_price = np.random.uniform(10, 100)
        
        # Fiyat hareketi oluştur
        returns = np.random.randn(bars) * 0.002  # %0.2 volatilite
        prices = base_price * np.exp(np.cumsum(returns))
        
        # OHLC oluştur
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices * (1 + np.random.randn(bars) * 0.001),
            'high': prices * (1 + abs(np.random.randn(bars)) * 0.002),
            'low': prices * (1 - abs(np.random.randn(bars)) * 0.002),
            'close': prices,
            'volume': np.random.randint(100000, 1000000, bars).astype('int64')
        })
        
        # Son barlarda "sıkışma" simülasyonu (bazı semboller için)
        if "SMALLCAP" in symbol:
            # Fiyatları yataya bağla (son 20 barın ortalaması)
            target_idx = df.index[-20:]
            
            # Fiyatları yataya bağla
            means = df.loc[target_idx, ['open', 'high', 'low', 'close']].mean()
            for col in ['open', 'high', 'low', 'close']:
                df.loc[target_idx, col] = means[col]
            
            # Hacmi düşür
            # .values kullanarak index/dtype uyarılarını önle
            df.loc[target_idx, 'volume'] = (df.loc[target_idx, 'volume'] * 0.3).astype(int).values
        
        return df
    
    def _mock_orderbook(self, symbol: str, depth: int) -> Dict:
        """Mock order book"""
        np.random.seed(hash(symbol + str(datetime.now().second)) % 10000)
        
        mid_price = np.random.uniform(10, 100)
        tick = mid_price * 0.001
        
        bids = [(mid_price - tick * (i + 1), np.random.randint(1000, 50000)) 
                for i in range(depth)]
        asks = [(mid_price + tick * (i + 1), np.random.randint(1000, 50000)) 
                for i in range(depth)]
        
        return {
            'bids': bids,
            'asks': asks,
            'timestamp': datetime.now()
        }
    
    def _mock_prints(self, symbol: str, minutes: int) -> pd.DataFrame:
        """Mock trade prints"""
        np.random.seed(hash(symbol) % 10000)
        
        n_trades = np.random.randint(50, 200)
        now = datetime.now()
        
        times = [now - timedelta(minutes=minutes) + timedelta(seconds=np.random.randint(0, minutes * 60))
                 for _ in range(n_trades)]
        times.sort()
        
        mid_price = np.random.uniform(10, 100)
        
        df = pd.DataFrame({
            'timestamp': times,
            'price': mid_price * (1 + np.random.randn(n_trades) * 0.001),
            'size': np.random.randint(100, 5000, n_trades),
            'side': np.random.choice(['buy', 'sell'], n_trades)
        })
        
        return df
    
    # ==================== API IMPLEMENTATIONS (Placeholder) ====================
    
    def _yfinance_ohlcv(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        """yfinance üzerinden veri çeker"""
        # yfinance interval mapping
        tf_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "1d": "1d"
        }
        
        interval = tf_map.get(timeframe, "1d")
        
        # BIST sembolü düzeltme (sonuna .IS ekle)
        yf_symbol = f"{symbol}.IS" if not symbol.endswith(".IS") else symbol
        
        # Period belirleme (bars sayısına göre yaklaşık)
        period = "1mo"
        if timeframe == "1m":
            period = "5d"  # 1m verisi genelde son 7 gün verilir
        elif timeframe == "5m":
            period = "1mo" # Son 1 ay
        elif timeframe == "1d":
            period = "1y"
            
        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                return pd.DataFrame()
            
            # Formatlama
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            
            # Datetime/Date kolonunu timestamp yap
            date_col = 'date' if 'date' in df.columns else 'datetime'
            if date_col in df.columns:
                df = df.rename(columns={date_col: 'timestamp'})
            
            # Timezone aware ise naive yap
            if pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            
            # İstenen bar sayısı kadar al
            if len(df) > bars:
                df = df.tail(bars)
            
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].reset_index(drop=True)
            
        except Exception as e:
            print(f"[yfinance] Error fetching {symbol}: {e}")
            return pd.DataFrame()

    def _api_ohlcv(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        """
        Gerçek API implementasyonu
        Örnek: https://api.example.com/ohlcv?symbol=THYAO&tf=1m&bars=120
        """
        try:
            response = requests.get(
                f"{API_BASE_URL}/ohlcv",
                params={
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'bars': bars,
                    'api_key': API_KEY
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return pd.DataFrame(data)
        except Exception as e:
            print(f"API error for {symbol}: {e}")
            return pd.DataFrame()
    
    def _api_orderbook(self, symbol: str, depth: int) -> Dict:
        """Gerçek L2 API implementasyonu"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/orderbook",
                params={'symbol': symbol, 'depth': depth, 'api_key': API_KEY},
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Orderbook API error for {symbol}: {e}")
            return None
    
    def _api_prints(self, symbol: str, minutes: int) -> pd.DataFrame:
        """Gerçek trade prints API implementasyonu"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/trades",
                params={'symbol': symbol, 'minutes': minutes, 'api_key': API_KEY},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return pd.DataFrame(data)
        except Exception as e:
            print(f"Trades API error for {symbol}: {e}")
            return pd.DataFrame()
    
    def _api_universe(self) -> List[str]:
        """Gerçek hisse listesi API'si"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/universe",
                params={'min_volume': MIN_DAILY_VOLUME_TL, 'api_key': API_KEY},
                timeout=10
            )
            response.raise_for_status()
            return response.json()['symbols']
        except Exception as e:
            print(f"Universe API error: {e}")
            return []


class OrderBookTracker:
    """Order book geçmişini takip eder (absorption için)"""
    
    def __init__(self, window_minutes: int = 15):
        self.window_minutes = window_minutes
        self.history = {}  # symbol -> [(timestamp, snapshot), ...]
    
    def add_snapshot(self, symbol: str, snapshot: Dict):
        """Yeni snapshot ekle"""
        if symbol not in self.history:
            self.history[symbol] = []
        
        self.history[symbol].append((datetime.now(), snapshot))
        
        # Eski snapshot'ları temizle
        cutoff = datetime.now() - timedelta(minutes=self.window_minutes)
        self.history[symbol] = [(t, s) for t, s in self.history[symbol] if t > cutoff]
    
    def get_history(self, symbol: str) -> List[Tuple[datetime, Dict]]:
        """Son X dakikanın geçmişini döner"""
        return self.history.get(symbol, [])
    
    def calculate_ask_reduction(self, symbol: str) -> float:
        """
        Ask tarafındaki toplam lot azalmasını hesaplar
        Returns: -1.0 ile 1.0 arası (negatif = azalma)
        """
        hist = self.get_history(symbol)
        if len(hist) < 2:
            return 0.0
        
        first_asks = sum(size for price, size in hist[0][1]['asks'])
        last_asks = sum(size for price, size in hist[-1][1]['asks'])
        
        if first_asks == 0:
            return 0.0
        
        return (last_asks - first_asks) / first_asks
    
    def calculate_bid_stability(self, symbol: str, level: int = 0) -> float:
        """
        Bid tarafındaki stabilitesini ölçer (aynı seviyede kalma)
        Returns: 0-1 arası (1 = çok stabil)
        """
        hist = self.get_history(symbol)
        if len(hist) < 3:
            return 0.0
        
        prices = [snapshot['bids'][level][0] if len(snapshot['bids']) > level else 0 
                  for _, snapshot in hist]
        
        if len(set(prices)) == 1 and prices[0] != 0:
            return 1.0  # Tam stabil
        
        # Fiyat değişim oranı
        std = np.std(prices)
        mean = np.mean(prices)
        if mean == 0:
            return 0.0
        
        cv = std / mean  # Coefficient of variation
        stability = max(0, 1 - cv * 10)  # Normalize
        
        return stability
