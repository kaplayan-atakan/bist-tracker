"""
BİST Trading Bot - Filters Module
Ön filtreler ve risk filtreleri
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

import config

logger = logging.getLogger(__name__)

# Filtre istatistikleri (her tarama için sıfırlanır)
_filter_stats = {
    'spread_rejected': 0,
    'volume_rejected': 0,
    'price_rejected': 0,
    'blacklist_rejected': 0,
    'volatility_rejected': 0,
    'data_error': 0,
    'passed': 0
}


def reset_filter_stats():
    """Filtre istatistiklerini sıfırla (her tarama başında çağır)"""
    global _filter_stats
    _filter_stats = {
        'spread_rejected': 0,
        'volume_rejected': 0,
        'price_rejected': 0,
        'blacklist_rejected': 0,
        'volatility_rejected': 0,
        'data_error': 0,
        'passed': 0
    }


def get_filter_stats() -> Dict:
    """Filtre istatistiklerini döndür"""
    return _filter_stats.copy()


def get_current_spread_limit() -> float:
    """
    Gunun saatine gore uygun spread limitini dondur.
    Kapanisa yakin (17:30+) spreadler dogal olarak genisler.
    """
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    
    # 17:30 ve sonrasi - kapanis saati, spreadler genisler
    if hour >= 17 and minute >= 30:
        return getattr(config, 'MAX_SPREAD_PERCENT_CLOSE', 5.0)
    # 18:00 ve sonrasi - borsa kapali
    if hour >= 18:
        return getattr(config, 'MAX_SPREAD_PERCENT_CLOSE', 5.0)
    
    # Normal market saatleri
    return config.MAX_SPREAD_PERCENT


def passes_pre_filters(symbol_data: Dict) -> tuple:
    """
    Sembol verilerini ön filtrelerden geçirir
    
    Args:
        symbol_data: Sembol için toplanan tüm veriler
        
    Returns:
        tuple: (geçti_mi: bool, red_nedeni: str)
    """
    global _filter_stats
    
    try:
        daily_stats = symbol_data.get('daily_stats')
        if not daily_stats:
            _filter_stats['data_error'] += 1
            return False, "Günlük veriler alınamadı"
        
        # Filtre 1: Kara liste kontrolü
        symbol = daily_stats.get('symbol')
        if symbol in config.BLACKLIST_SYMBOLS:
            _filter_stats['blacklist_rejected'] += 1
            return False, f"{symbol} kara listede"
        
        # Filtre 2: Fiyat bandı kontrolü
        current_price = daily_stats.get('current_price', 0)
        if current_price < config.MIN_PRICE:
            _filter_stats['price_rejected'] += 1
            return False, f"Fiyat çok düşük ({current_price:.2f} < {config.MIN_PRICE})"
        
        if current_price > config.MAX_PRICE:
            _filter_stats['price_rejected'] += 1
            return False, f"Fiyat çok yüksek ({current_price:.2f} > {config.MAX_PRICE})"
        
        # Filtre 3: Minimum günlük hacim (TL)
        daily_volume_tl = daily_stats.get('daily_volume_tl', 0)
        if daily_volume_tl < config.MIN_DAILY_TL_VOLUME:
            _filter_stats['volume_rejected'] += 1
            return False, f"Yetersiz hacim ({daily_volume_tl/1e6:.2f}M < {config.MIN_DAILY_TL_VOLUME/1e6:.2f}M TL)"
        
        # Filtre 4: Spread kontrolü (zaman duyarlı)
        # Kapanışa yakın spread'ler doğal olarak genişler
        spread = symbol_data.get('spread')
        if spread is not None and spread > 0:
            max_spread = get_current_spread_limit()
            if spread > max_spread:
                _filter_stats['spread_rejected'] += 1
                return False, f"Spread çok geniş ({spread:.2f}% > {max_spread:.1f}%)"
        
        # Filtre 5: Günlük hareket kontrolü (aşırı gap)
        daily_change = daily_stats.get('daily_change_percent', 0)
        if abs(daily_change) > 15:  # %15'ten fazla hareket şüpheli olabilir
            logger.warning(f"{symbol} için aşırı günlük hareket: {daily_change:.2f}%")
            # Bu durumda elenmesin ama uyarı ver
        
        # Tüm filtreleri geçti
        _filter_stats['passed'] += 1
        return True, "OK"
        
    except Exception as e:
        logger.error(f"Filtre hatası: {str(e)}")
        return False, f"Filtre hatası: {str(e)}"


def check_liquidity(symbol_data: Dict) -> bool:
    """
    Likidite kontrolü yapar
    
    Args:
        symbol_data: Sembol verileri
        
    Returns:
        bool: Likidite yeterli mi?
    """
    try:
        # Önce daily_stats'tan dene (doğru yol)
        daily_stats = symbol_data.get('daily_stats', {})
        daily_volume_tl = daily_stats.get('daily_volume_tl', 0)
        
        # volume_indicators'tan da bak (eski kod uyumluluğu)
        if daily_volume_tl == 0:
            volume_indicators = symbol_data.get('volume_indicators', {})
            daily_volume_tl = volume_indicators.get('daily_volume_tl', 0)
        
        # Minimum likidite eşiği
        min_liquidity = config.MIN_DAILY_TL_VOLUME
        
        return daily_volume_tl >= min_liquidity
        
    except Exception as e:
        logger.error(f"Likidite kontrolü hatası: {str(e)}")
        return False


def check_volatility_risk(symbol_data: Dict) -> tuple:
    """
    Aşırı volatilite riski kontrolü
    
    Args:
        symbol_data: Sembol verileri
        
    Returns:
        tuple: (güvenli_mi: bool, uyarı_mesajı: str)
    """
    try:
        daily_stats = symbol_data.get('daily_stats')
        if not daily_stats:
            return True, ""
        
        daily_change = daily_stats.get('daily_change_percent', 0)
        
        # Aşırı günlük hareket
        if abs(daily_change) > 20:
            return False, f"Aşırı volatilite: {daily_change:.2f}%"
        
        # Price action kontrolü
        pa_indicators = symbol_data.get('pa_indicators', {})
        has_collapse = pa_indicators.get('has_collapse', False)
        
        if has_collapse:
            return False, "Son günlerde sert düşüş tespit edildi"
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Volatilite kontrolü hatası: {str(e)}")
        return True, ""


def apply_all_filters(symbol_data: Dict) -> tuple:
    """
    Tüm filtreleri uygular
    
    Args:
        symbol_data: Sembol verileri
        
    Returns:
        tuple: (geçti_mi: bool, mesaj: str)
    """
    global _filter_stats
    
    # Ön filtreler (spread, fiyat, hacim, kara liste)
    passes, reason = passes_pre_filters(symbol_data)
    if not passes:
        return False, f"Ön filtre: {reason}"
    
    # Likidite kontrolü (passes_pre_filters'da zaten kontrol ediliyor)
    # Ama ek bir kontrol olarak kalabilir
    if not check_liquidity(symbol_data):
        _filter_stats['volume_rejected'] += 1
        return False, "Likidite yetersiz"
    
    # Volatilite riski
    safe, warning = check_volatility_risk(symbol_data)
    if not safe:
        _filter_stats['volatility_rejected'] += 1
        return False, f"Risk: {warning}"
    
    return True, "Tüm filtreleri geçti"
