"""
BİST-100 Symbol Fetcher & Validator

BİST-100 sembol listesini güvenilir kaynaklardan çeker ve doğrular.

Usage:
    python -m utils.symbol_fetcher --list
    python -m utils.symbol_fetcher --fetch
    python -m utils.symbol_fetcher --validate
    python -m utils.symbol_fetcher --update-config
"""

import re
import logging
from typing import List, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Güvenilir BİST-100 sembol listesi (Aralık 2024 güncel)
# Kaynak: Borsa İstanbul resmi BİST-100 endeksi
BIST100_SYMBOLS_DEC2024 = [
    # Bankacılık
    "AKBNK", "GARAN", "HALKB", "ISCTR", "VAKBN", "YKBNK", "SKBNK", "TSKB",
    # Holding
    "SAHOL", "KCHOL", "DOHOL", "AGHOL", "GLYHO", "KLRHO", "KOZAA", "KOZAL",
    # Havacılık & Savunma
    "THYAO", "ASELS", "PGSUS", "TAVHL",
    # Otomotiv
    "FROTO", "TOASO", "OTKAR", "TTRAK", "DOAS", "BRISA",
    # Enerji
    "TUPRS", "AKSEN", "ENJSA", "EUPWR", "GWIND", "ZOREN", "AYGAZ", "AHGAZ",
    # Teknoloji & Telekomünikasyon
    "TCELL", "TTKOM", "NETAS", "LOGO", "INDES", "PAPIL",
    # Perakende
    "BIMAS", "MGROS", "SOKM", "MAVI", "MPARK",
    # Sanayi & Üretim
    "EREGL", "KRDMD", "BRSAN", "SISE", "ARCLK", "VESTL", "VESBE", "TOASO",
    # Kimya & Petrokimya
    "PETKM", "SASA", "GUBRF", "AKSA", "KORDS",
    # Gıda & İçecek
    "ULKER", "AEFES", "CCOLA", "TATGD", "TBORG",
    # İnşaat & GYO
    "ENKAI", "EKGYO", "ISGYO", "SNGYO", "TDGYO", "PEKGY",
    # Madencilik
    "IPEKE",
    # Çimento & Yapı Malzemeleri
    "CIMSA", "AKCNS", "GOLTS", "OYAKC", "ANACM",
    # Diğer Sanayi
    "TKFEN", "ALARK", "GESAN", "HEKTS", "KONTR", "ODAS", "TURSG",
    "KARSN", "KLMSN", "QUAGR", "SELEC", "SILVR", "SMRTG", "TABGD",
    "TGSAS", "TRILC", "YEOTK", "KERVT", "KMPUR", "PRKME",
    # Finans (Sigorta, Faktoring)
    "ISMEN",
    # Tekstil
    "KARSN",
    # Ulaştırma
    "CLEBI", "RYGYO",
    # Cam
    "TRKCM",
]

# yfinance için doğrulanmış ve çalışan semboller (test edilmiş)
VERIFIED_WORKING_SYMBOLS = [
    "THYAO", "ASELS", "KCHOL", "EREGL", "AKBNK", "SISE", "SAHOL", "GARAN",
    "ISCTR", "PETKM", "TUPRS", "HALKB", "BIMAS", "VAKBN", "TAVHL", "YKBNK",
    "TCELL", "PGSUS", "TOASO", "TTKOM", "ARCLK", "EKGYO", "FROTO", "AEFES", 
    "VESBE", "ODAS", "DOHOL", "ENKAI", "BRSAN", "MGROS", "ULKER", "BRISA", 
    "AYGAZ", "OTKAR", "NETAS", "CCOLA", "SOKM", "KRDMD", "AKSA", "LOGO", 
    "GESAN", "ALARK", "INDES", "MAVI", "KARSN", "TURSG", "KONTR", "KLMSN", 
    "EUPWR", "HEKTS", "CIMSA", "VESTL", "SASA", "GUBRF", "KORDS", "AKSEN",
    "ENJSA", "TKFEN", "DOAS", "TSKB", "SKBNK", "MPARK", "IPEKE", "AKCNS",
    "GOLTS", "OYAKC", "AGHOL", "ISMEN", "GLYHO", "ISGYO", "TBORG", "TATGD",
    "SNGYO", "TDGYO", "PEKGY", "ZOREN", "AHGAZ", "GWIND", "TTRAK", "CLEBI",
    "TRKCM",
]


def get_fallback_symbols() -> List[str]:
    """
    Doğrulanmış ve çalışan BİST sembollerini döndürür.
    yfinance ile test edilmiş semboller.
    """
    return sorted(list(set(VERIFIED_WORKING_SYMBOLS)))


def fetch_bist100_symbols(source: str = "hardcoded") -> List[str]:
    """
    BİST-100 sembol listesini çeker.
    
    Args:
        source: Veri kaynağı ("hardcoded", "investing", "tefas")
        
    Returns:
        List[str]: Sembol listesi (.IS uzantısı olmadan)
    """
    if source == "hardcoded":
        return get_fallback_symbols()
    
    elif source == "investing":
        return _fetch_from_investing()
    
    else:
        logger.warning(f"Bilinmeyen kaynak: {source}, fallback kullanılıyor")
        return get_fallback_symbols()


def _fetch_from_investing() -> List[str]:
    """
    investing.com'dan BİST-100 sembol listesini çeker.
    
    NOT: Web scraping, site yapısı değişirse bozulabilir.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("requests veya beautifulsoup4 yüklü değil")
        return get_fallback_symbols()
    
    url = "https://www.investing.com/indices/ise-100-components"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        symbols = []
        
        # investing.com tablo yapısını parse et
        table = soup.find("table", {"id": "cr1"})
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Header'ı atla
                cells = row.find_all("td")
                if len(cells) >= 2:
                    # Sembol genellikle 2. hücrede
                    symbol_text = cells[1].get_text(strip=True)
                    # Temizle
                    symbol = symbol_text.split()[0].upper()
                    if symbol and len(symbol) >= 2 and symbol.isalpha():
                        symbols.append(symbol)
        
        if symbols:
            logger.info(f"investing.com'dan {len(symbols)} sembol çekildi")
            return symbols
        else:
            logger.warning("investing.com'dan sembol çekilemedi, fallback kullanılıyor")
            return get_fallback_symbols()
            
    except Exception as e:
        logger.error(f"investing.com hatası: {e}")
        return get_fallback_symbols()


def validate_symbols_with_yfinance(
    symbols: List[str],
    quick_check: bool = True,
    max_symbols: int = 100
) -> Tuple[List[str], List[str]]:
    """
    Sembolleri yfinance ile doğrular.
    
    Args:
        symbols: Doğrulanacak semboller
        quick_check: Hızlı kontrol (sadece fiyat varlığı)
        max_symbols: Maksimum kontrol edilecek sembol
        
    Returns:
        Tuple[valid, invalid]: Geçerli ve geçersiz semboller
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance yüklü değil")
        return symbols, []
    
    valid = []
    invalid = []
    
    symbols_to_check = symbols[:max_symbols]
    total = len(symbols_to_check)
    
    logger.info(f"{total} sembol doğrulanıyor...")
    
    for i, symbol in enumerate(symbols_to_check, 1):
        yf_symbol = f"{symbol}.IS"
        
        try:
            ticker = yf.Ticker(yf_symbol)
            
            if quick_check:
                # Hızlı kontrol: Son fiyat var mı?
                hist = ticker.history(period="5d")
                if not hist.empty and len(hist) > 0:
                    valid.append(symbol)
                else:
                    invalid.append(symbol)
            else:
                # Detaylı kontrol: Info ve fiyat
                info = ticker.info
                if info and info.get("regularMarketPrice"):
                    valid.append(symbol)
                else:
                    invalid.append(symbol)
                    
        except Exception as e:
            logger.debug(f"{symbol} doğrulama hatası: {e}")
            invalid.append(symbol)
        
        # Progress
        if i % 10 == 0:
            logger.info(f"İlerleme: {i}/{total} ({len(valid)} geçerli, {len(invalid)} geçersiz)")
    
    logger.info(f"Doğrulama tamamlandı: {len(valid)} geçerli, {len(invalid)} geçersiz")
    return valid, invalid


def get_validated_bist100_symbols(validate: bool = False) -> List[str]:
    """
    Doğrulanmış BİST-100 sembol listesini döndürür.
    
    Args:
        validate: yfinance ile doğrulama yapılsın mı
        
    Returns:
        List[str]: Sembol listesi
    """
    symbols = fetch_bist100_symbols("hardcoded")
    
    if validate:
        valid, invalid = validate_symbols_with_yfinance(symbols)
        if invalid:
            logger.warning(f"Geçersiz semboller: {invalid}")
        return valid
    
    return symbols


def update_config_file(symbols: List[str], config_path: Optional[str] = None) -> bool:
    """
    config.py dosyasındaki BIST_SYMBOLS listesini günceller.
    
    Args:
        symbols: Yeni sembol listesi
        config_path: config.py dosya yolu (None ise otomatik bul)
        
    Returns:
        bool: Başarılı mı
    """
    if config_path is None:
        # Otomatik bul
        possible_paths = [
            Path(__file__).parent.parent / "config.py",
            Path("config.py"),
            Path("core-src/config.py"),
        ]
        for p in possible_paths:
            if p.exists():
                config_path = str(p)
                break
    
    if not config_path or not Path(config_path).exists():
        logger.error(f"config.py bulunamadı")
        return False
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Sembolleri formatla (8'li gruplar halinde)
        sorted_symbols = sorted(set(symbols))
        lines = []
        for i in range(0, len(sorted_symbols), 8):
            chunk = sorted_symbols[i:i+8]
            line = ", ".join([f"'{s}'" for s in chunk])
            lines.append(f"    {line},")
        
        symbols_block = "\n".join(lines)
        new_list = f"BIST_SYMBOLS = [\n{symbols_block}\n]"
        
        # Mevcut BIST_SYMBOLS'ı bul ve değiştir
        pattern = r"BIST_SYMBOLS\s*=\s*\[[\s\S]*?\]"
        
        if re.search(pattern, content):
            new_content = re.sub(pattern, new_list, content)
        else:
            logger.error("BIST_SYMBOLS config.py'da bulunamadı")
            return False
        
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        logger.info(f"config.py güncellendi: {len(sorted_symbols)} sembol")
        return True
        
    except Exception as e:
        logger.error(f"config.py güncelleme hatası: {e}")
        return False


def print_symbol_comparison(current: List[str], new: List[str]):
    """Mevcut ve yeni sembol listelerini karşılaştırır."""
    current_set = set(current)
    new_set = set(new)
    
    added = new_set - current_set
    removed = current_set - new_set
    common = current_set & new_set
    
    print(f"\n{'='*60}")
    print(f"SEMBOL KARŞILAŞTIRMASI")
    print(f"{'='*60}")
    print(f"Mevcut: {len(current_set)} sembol")
    print(f"Yeni:   {len(new_set)} sembol")
    print(f"Ortak:  {len(common)} sembol")
    print(f"{'='*60}")
    
    if added:
        print(f"\n➕ Eklenen ({len(added)}):")
        print(f"   {', '.join(sorted(added))}")
    
    if removed:
        print(f"\n➖ Çıkarılan ({len(removed)}):")
        print(f"   {', '.join(sorted(removed))}")
    
    print(f"{'='*60}\n")


# CLI Interface
if __name__ == "__main__":
    import argparse
    import sys
    
    # Logging ayarla
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(
        description="BİST-100 Sembol Fetcher & Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python -m utils.symbol_fetcher --list          # Mevcut sembolleri listele
  python -m utils.symbol_fetcher --fetch         # Web'den çek
  python -m utils.symbol_fetcher --validate      # yfinance ile doğrula
  python -m utils.symbol_fetcher --update-config # config.py'ı güncelle
        """
    )
    
    parser.add_argument("--list", action="store_true", 
                        help="Doğrulanmış sembol listesini göster")
    parser.add_argument("--fetch", action="store_true",
                        help="Web'den sembol listesi çek")
    parser.add_argument("--validate", action="store_true",
                        help="Sembolleri yfinance ile doğrula")
    parser.add_argument("--update-config", action="store_true",
                        help="config.py'daki BIST_SYMBOLS'ı güncelle")
    parser.add_argument("--source", type=str, default="hardcoded",
                        choices=["hardcoded", "investing"],
                        help="Veri kaynağı (varsayılan: hardcoded)")
    
    args = parser.parse_args()
    
    # Hiçbir argüman verilmediyse yardım göster
    if not any([args.list, args.fetch, args.validate, args.update_config]):
        parser.print_help()
        sys.exit(0)
    
    # --list: Sembolleri listele
    if args.list:
        symbols = get_fallback_symbols()
        print(f"\n{'='*60}")
        print(f"DOĞRULANMIŞ BİST SEMBOLLERİ ({len(symbols)} adet)")
        print(f"{'='*60}\n")
        
        for i, symbol in enumerate(symbols, 1):
            print(f"{i:3}. {symbol}")
        
        print(f"\n{'='*60}\n")
    
    # --fetch: Web'den çek
    if args.fetch:
        print(f"\n📥 Semboller çekiliyor (kaynak: {args.source})...")
        symbols = fetch_bist100_symbols(args.source)
        
        print(f"\n{'='*60}")
        print(f"ÇEKİLEN SEMBOLLER ({len(symbols)} adet)")
        print(f"{'='*60}\n")
        
        for i, symbol in enumerate(symbols, 1):
            print(f"{i:3}. {symbol}")
    
    # --validate: Doğrula
    if args.validate:
        print(f"\n🔍 Semboller doğrulanıyor...")
        symbols = fetch_bist100_symbols(args.source)
        valid, invalid = validate_symbols_with_yfinance(symbols)
        
        print(f"\n{'='*60}")
        print(f"DOĞRULAMA SONUÇLARI")
        print(f"{'='*60}")
        print(f"✅ Geçerli: {len(valid)}")
        print(f"❌ Geçersiz: {len(invalid)}")
        
        if invalid:
            print(f"\nGeçersiz semboller:")
            for s in invalid:
                print(f"   - {s}")
        
        print(f"{'='*60}\n")
    
    # --update-config: config.py güncelle
    if args.update_config:
        print(f"\n📝 config.py güncelleniyor...")
        
        # Mevcut sembolleri oku
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            import config
            current_symbols = getattr(config, 'BIST_SYMBOLS', [])
        except:
            current_symbols = []
        
        # Yeni sembolleri al
        new_symbols = get_validated_bist100_symbols(validate=False)
        
        # Karşılaştır
        if current_symbols:
            print_symbol_comparison(current_symbols, new_symbols)
        
        # Güncelle
        if update_config_file(new_symbols):
            print(f"✅ config.py güncellendi ({len(new_symbols)} sembol)")
        else:
            print(f"❌ config.py güncellenemedi")
            sys.exit(1)
