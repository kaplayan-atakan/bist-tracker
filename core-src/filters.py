"""
BİST Trading Bot - Filters Module
Ön filtreler ve risk filtreleri
"""

import logging
from typing import Dict, Optional

import config

logger = logging.getLogger(__name__)


def passes_pre_filters(symbol_data: Dict) -> tuple:
    """
    Sembol verilerini ön filtrelerden geçirir
    
    Args:
        symbol_data: Sembol için toplanan tüm veriler
        
    Returns:
        tuple: (geçti_mi: bool, red_nedeni: str)
    """
    try:
        daily_stats = symbol_data.get('daily_stats')
        if not daily_stats:
            return False, "Günlük veriler alınamadı"
        
        # Filtre 1: Kara liste kontrolü
        symbol = daily_stats.get('symbol')
        if symbol in config.BLACKLIST_SYMBOLS:
            return False, f"{symbol} kara listede"
        
        # Filtre 2: Fiyat bandı kontrolü
        current_price = daily_stats.get('current_price', 0)
        if current_price < config.MIN_PRICE:
            return False, f"Fiyat çok düşük ({current_price:.2f} < {config.MIN_PRICE})"
        
        if current_price > config.MAX_PRICE:
            return False, f"Fiyat çok yüksek ({current_price:.2f} > {config.MAX_PRICE})"
        
        # Filtre 3: Minimum günlük hacim (TL)
        daily_volume_tl = daily_stats.get('daily_volume_tl', 0)
        if daily_volume_tl < config.MIN_DAILY_TL_VOLUME:
            return False, f"Yetersiz hacim ({daily_volume_tl/1e6:.2f}M < {config.MIN_DAILY_TL_VOLUME/1e6:.2f}M TL)"
        
        # Filtre 4: Spread kontrolü (opsiyonel)
        # Bu bilgi her zaman mevcut olmayabilir
        spread = symbol_data.get('spread')
        if spread and spread > config.MAX_SPREAD_PERCENT:
            return False, f"Spread çok geniş ({spread:.2f}% > {config.MAX_SPREAD_PERCENT}%)"
        
        # Filtre 5: Günlük hareket kontrolü (aşırı gap)
        daily_change = daily_stats.get('daily_change_percent', 0)
        if abs(daily_change) > 15:  # %15'ten fazla hareket şüpheli olabilir
            logger.warning(f"{symbol} için aşırı günlük hareket: {daily_change:.2f}%")
            # Bu durumda elenmesin ama uyarı ver
        
        # Tüm filtreleri geçti
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
    # Ön filtreler
    passes, reason = passes_pre_filters(symbol_data)
    if not passes:
        return False, f"Ön filtre: {reason}"
    
    # Likidite kontrolü
    if not check_liquidity(symbol_data):
        return False, "Likidite yetersiz"
    
    # Volatilite riski
    safe, warning = check_volatility_risk(symbol_data)
    if not safe:
        return False, f"Risk: {warning}"
    
    return True, "Tüm filtreleri geçti"