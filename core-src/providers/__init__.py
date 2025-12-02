"""
BİST Trading Bot - Providers Package
Veri kaynakları soyutlama katmanı

Sprint 2 Güncellemesi:
- TradingViewWebSocketProvider: Gerçek zamanlı streaming (get_realtime_stream())
- TradingViewHTTPProvider: HTTP screener API ile anlık snapshot (get_ohlcv(), get_snapshots())
- YahooProvider: Günlük veriler + fundamentals
- FinnhubProvider: Alternatif intraday kaynak (API key gerekli)

VERİ GECİKMESİ UYARISI:
Anonim kullanımda TradingView verileri 15 dakika gecikmelidir (delayed_streaming_900).
Gerçek zamanlı veri için TradingView authentication gerekir (gelecek sprint).
"""

from .base import BaseDataProvider, Timeframe, ProviderHealthStatus, ProviderConfig
from .manager import ProviderManager, get_provider_manager
from .yahoo import YahooProvider
from .finnhub import FinnhubProvider
from .tradingview_ws import TradingViewWebSocketProvider, QuoteData, get_tradingview_ws_provider
from .tradingview_http import TradingViewHTTPProvider, OHLCVSnapshot, get_tradingview_http_provider

__all__ = [
    # Base
    'BaseDataProvider',
    'Timeframe',
    'ProviderHealthStatus',
    'ProviderConfig',
    
    # Manager
    'ProviderManager',
    'get_provider_manager',
    
    # Providers
    'YahooProvider',
    'FinnhubProvider',
    'TradingViewWebSocketProvider',
    'TradingViewHTTPProvider',
    
    # Data classes
    'QuoteData',
    'OHLCVSnapshot',
    
    # Factory functions
    'get_tradingview_ws_provider',
    'get_tradingview_http_provider',
]
