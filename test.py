# fetch_tradingview_bist_symbols.py
# TradingView Scanner API kullanarak tüm BİST sembollerini çeker
# Selenium gerektirmez - sadece requests kullanır
# 
# Çalıştırmak için: pip install requests
# python test.py

import requests
import json
from typing import List, Dict


def fetch_all_bist_symbols() -> List[str]:
    """
    TradingView Scanner API kullanarak tüm BİST sembollerini çeker.
    
    Returns:
        List[str]: Sembol listesi (örn: ['THYAO', 'AKBNK', ...])
    """
    url = "https://scanner.tradingview.com/turkey/scan"
    
    # TradingView scanner payload - tüm Türk hisselerini çek
    payload = {
        "filter": [
            {"left": "type", "operation": "in_range", "right": ["stock", "dr", "fund"]}
        ],
        "options": {"lang": "tr"},
        "markets": ["turkey"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": [
            "name",
            "close",
            "change",
            "change_abs",
            "volume",
            "market_cap_basic",
            "sector",
            "description"
        ],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, 1000]  # İlk 1000 sembol (BİST'te ~550 var)
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        symbols = []
        for item in data.get("data", []):
            # item["s"] = "BIST:THYAO" formatında
            full_symbol = item.get("s", "")
            if ":" in full_symbol:
                symbol = full_symbol.split(":")[1]
                symbols.append(symbol)
        
        return symbols
        
    except Exception as e:
        print(f"Hata: {e}")
        return []


def categorize_symbols(symbols: List[str]) -> Dict[str, List[str]]:
    """
    Sembolleri kategorilere ayırır.
    
    Bazı semboller yfinance ile çalışmaz:
    - Varantlar (genelde sembol + W veya uzun isimli)
    - Yabancı DR'ler
    - ETF'ler (farklı işlenir)
    """
    stocks = []
    etfs = []
    warrants = []
    others = []
    
    for s in symbols:
        # Varant kontrolü (genelde uzun isimler veya özel karakterler)
        if len(s) > 6 or any(c in s for c in ['-', 'W', 'P', 'C']):
            warrants.append(s)
        # ETF kontrolü
        elif s.endswith('E') and len(s) <= 5:
            etfs.append(s)
        # Normal hisse
        else:
            stocks.append(s)
    
    return {
        "stocks": stocks,
        "etfs": etfs,
        "warrants": warrants,
        "others": others
    }


def validate_with_yfinance(symbols: List[str], batch_size: int = 10) -> tuple:
    """
    Tüm sembolleri yfinance ile doğrular.
    
    Returns:
        tuple: (valid_symbols, invalid_symbols)
    """
    try:
        import yfinance as yf
        from tqdm import tqdm
        
        valid = []
        invalid = []
        
        print(f"\n🔍 {len(symbols)} sembol yfinance ile doğrulanıyor...")
        print("   (Bu işlem birkaç dakika sürebilir)\n")
        
        for i, symbol in enumerate(tqdm(symbols, desc="Doğrulama")):
            ticker = f"{symbol}.IS"
            try:
                stock = yf.Ticker(ticker)
                # Fast info kontrolü
                hist = stock.history(period="5d")
                if hist is not None and not hist.empty and len(hist) > 0:
                    valid.append(symbol)
                else:
                    invalid.append(symbol)
            except Exception as e:
                invalid.append(symbol)
        
        return valid, invalid
    except ImportError:
        print("❌ yfinance veya tqdm yüklü değil!")
        print("   pip install yfinance tqdm")
        return symbols, []


def main():
    print("=" * 60)
    print("🔍 TradingView BİST Sembol Tarayıcı")
    print("=" * 60)
    
    # Sembolleri çek
    print("\n📡 TradingView API'den semboller çekiliyor...")
    symbols = fetch_all_bist_symbols()
    
    if not symbols:
        print("❌ Sembol çekilemedi!")
        return
    
    print(f"✅ {len(symbols)} sembol bulundu")
    
    # Kategorize et
    print("\n📊 Semboller kategorize ediliyor...")
    categories = categorize_symbols(symbols)
    
    print(f"   • Hisse senetleri: {len(categories['stocks'])}")
    print(f"   • ETF'ler: {len(categories['etfs'])}")
    print(f"   • Varantlar: {len(categories['warrants'])}")
    
    # Sadece hisseleri al
    stocks = categories['stocks']
    
    # ===== YFINANCE DOĞRULAMA =====
    print("\n" + "=" * 60)
    print("🔬 YFINANCE DOĞRULAMA")
    print("=" * 60)
    
    valid_stocks, invalid_stocks = validate_with_yfinance(stocks)
    
    print(f"\n✅ Geçerli semboller: {len(valid_stocks)}")
    print(f"❌ Geçersiz semboller: {len(invalid_stocks)}")
    
    if invalid_stocks:
        print(f"\n⚠️ Geçersiz semboller ({len(invalid_stocks)}):")
        for i, s in enumerate(sorted(invalid_stocks)[:30], 1):
            print(f"   {i:3}. {s}")
        if len(invalid_stocks) > 30:
            print(f"   ... ve {len(invalid_stocks) - 30} sembol daha")
    
    # Mevcut config.py ile karşılaştır
    print("\n🔄 Mevcut config.py ile karşılaştırılıyor...")
    try:
        import sys
        sys.path.insert(0, 'core-src')
        import config
        existing = set(config.BIST_SYMBOLS)
        new_symbols = [s for s in valid_stocks if s not in existing]
        
        print(f"   • Mevcut: {len(existing)} sembol")
        print(f"   • Doğrulanmış yeni: {len(new_symbols)} sembol")
        
        if new_symbols:
            print(f"\n📝 Yeni doğrulanmış semboller ({len(new_symbols)}):")
            for i, s in enumerate(sorted(new_symbols)[:50], 1):
                print(f"   {i:3}. {s}")
            if len(new_symbols) > 50:
                print(f"   ... ve {len(new_symbols) - 50} sembol daha")
    except ImportError:
        print("   config.py bulunamadı, karşılaştırma atlanıyor")
        new_symbols = valid_stocks
    
    # JSON'a kaydet
    output = {
        "source": "TradingView Scanner API",
        "total_count": len(symbols),
        "validated_stock_count": len(valid_stocks),
        "invalid_count": len(invalid_stocks),
        "stocks": sorted(valid_stocks),
        "invalid_stocks": sorted(invalid_stocks),
        "etfs": sorted(categories['etfs']),
    }
    
    with open("bist_symbols_validated.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Doğrulanmış JSON kaydedildi: bist_symbols_validated.json")
    
    # Python formatında çıktı (config.py için)
    print("\n" + "=" * 60)
    print("📋 CONFIG.PY İÇİN DOĞRULANMIŞ PYTHON LİSTESİ:")
    print("=" * 60)
    print(f"\n# {len(valid_stocks)} doğrulanmış BİST sembolü")
    print("BIST_SYMBOLS = [")
    for i, s in enumerate(sorted(valid_stocks)):
        comma = "," if i < len(valid_stocks) - 1 else ""
        print(f"    '{s}'{comma}")
    print("]")


if __name__ == "__main__":
    main()
