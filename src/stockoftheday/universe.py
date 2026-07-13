"""US stock universe and sector map.

Two tiers:
- load_universe() — the full NYSE/NASDAQ common-stock listing (~7-9k symbols,
  penny stocks included), fetched from the official NASDAQ Trader symbol
  directory and cached for 7 days. Falls back to WATCHLIST offline.
- WATCHLIST — hardcoded ~450 liquid names, used as the fallback and via --core.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
UNIVERSE_CACHE = DATA_DIR / "us_universe.json"
UNIVERSE_TTL = 7 * 86400

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# Plain 1-5 letter symbols only — drops preferreds/units/classes like "AAC.U",
# "BRK.A", "ABC$D" which yfinance can't resolve under these names anyway.
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")
# Non-common-stock instruments identified by security name
_EXCLUDE_NAME_RE = re.compile(
    r"warrant|right(s)? |unit(s)?[ ,]|preferred|preference|depositary|"
    r"% notes|notes due|bond|debenture|trust preferred",
    re.IGNORECASE,
)
# otherlisted.txt exchanges: N = NYSE, A = NYSE American, P = NYSE Arca
_ALLOWED_EXCHANGES = {"N", "A", "P"}


def parse_symbol_directory(nasdaq_text: str, other_text: str) -> list[str]:
    """Parse NASDAQ Trader symbol directory files into a clean common-stock list."""
    symbols: set[str] = set()

    # nasdaqlisted.txt: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot|ETF|NextShares
    for line in nasdaq_text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sym, name, _mkt, test, _fin, _lot, etf = parts[:7]
        if test != "N" or etf == "Y":
            continue
        if not _SYMBOL_RE.match(sym) or _EXCLUDE_NAME_RE.search(name):
            continue
        symbols.add(sym)

    # otherlisted.txt: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot|Test Issue|NASDAQ Symbol
    for line in other_text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sym, name, exchange, _cqs, etf, _lot, test = parts[:7]
        if test != "N" or etf == "Y" or exchange not in _ALLOWED_EXCHANGES:
            continue
        if not _SYMBOL_RE.match(sym) or _EXCLUDE_NAME_RE.search(name):
            continue
        symbols.add(sym)

    return sorted(symbols)


def fetch_us_universe(timeout: float = 30.0) -> list[str]:
    """Download and parse the full US listing. Raises on network failure."""
    def _get(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    return parse_symbol_directory(_get(NASDAQ_LISTED_URL), _get(OTHER_LISTED_URL))


def load_universe(refresh: bool = False) -> list[str]:
    """Full US universe with a 7-day disk cache; falls back to WATCHLIST offline."""
    if not refresh and UNIVERSE_CACHE.exists():
        try:
            if time.time() - UNIVERSE_CACHE.stat().st_mtime < UNIVERSE_TTL:
                raw = json.loads(UNIVERSE_CACHE.read_text(encoding="utf-8"))
                syms = raw.get("symbols", [])
                if len(syms) > 1000:
                    return syms
        except Exception:
            pass

    try:
        symbols = sorted(set(fetch_us_universe()) | set(WATCHLIST))
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UNIVERSE_CACHE.write_text(
            json.dumps({"fetched": time.time(), "symbols": symbols}), encoding="utf-8"
        )
        return symbols
    except Exception:
        # Stale cache beats the small fallback list
        try:
            raw = json.loads(UNIVERSE_CACHE.read_text(encoding="utf-8"))
            syms = raw.get("symbols", [])
            if len(syms) > 1000:
                return syms
        except Exception:
            pass
        return WATCHLIST


WATCHLIST: list[str] = [
    # ── Mega-cap Tech ─────────────────────────────────────────────────────────
    "AAPL", "MSFT", "NVDA", "AMD", "META", "GOOGL", "AMZN", "TSLA",
    # ── Semiconductors ───────────────────────────────────────────────────────
    "AVGO", "QCOM", "MU", "MRVL", "AMAT", "LRCX", "KLAC", "INTC",
    "TXN", "ON", "MCHP", "WOLF", "SMCI", "ARM", "SLAB",
    # ── Cloud / Enterprise SaaS ───────────────────────────────────────────────
    "CRM", "NOW", "SNOW", "PLTR", "ORCL", "ADBE", "WDAY", "TEAM",
    # ── Cybersecurity ────────────────────────────────────────────────────────
    "PANW", "CRWD", "ZS", "FTNT", "DDOG", "NET", "CYBR", "S",
    # ── Fintech / Crypto ─────────────────────────────────────────────────────
    "V", "MA", "PYPL", "SQ", "COIN", "HOOD", "SOFI", "AFRM",
    "MARA", "RIOT", "CLSK", "HUT", "CIFR",
    # ── Banks / Finance ──────────────────────────────────────────────────────
    "JPM", "BAC", "GS", "MS", "C", "WFC", "BX", "BLK", "SCHW",
    "IBKR", "RJF",
    # ── Energy ───────────────────────────────────────────────────────────────
    "XOM", "CVX", "COP", "OXY", "MRO", "DVN", "FANG", "HES", "EOG",
    "SLB", "HAL", "BKR", "NOG", "SM",
    # ── Healthcare / Biotech ─────────────────────────────────────────────────
    "LLY", "NVO", "ABBV", "MRK", "PFE", "BMY", "AMGN", "GILD",
    "REGN", "VRTX", "MRNA", "BNTX", "BIIB", "ALNY", "EXAS",
    "RXRX", "ACHR",
    # ── Consumer / Retail ────────────────────────────────────────────────────
    "WMT", "COST", "TGT", "HD", "LOW", "NKE", "DIS", "NFLX",
    "UBER", "LYFT", "DASH", "BKNG", "ABNB",
    # ── AI / Data / Infra ────────────────────────────────────────────────────
    "DELL", "HPE", "IONQ", "RGTI", "QUBT", "LUNR", "RKLB",
    # ── EVs / Clean Energy ───────────────────────────────────────────────────
    "RIVN", "LCID", "NIO", "LI", "XPEV", "ENPH", "FSLR",
    "F", "GM", "PLUG",
    # ── Industrials / Defense ────────────────────────────────────────────────
    "GE", "CAT", "BA", "RTX", "LMT", "NOC", "DE", "HON",
    # ── Media / Gaming ───────────────────────────────────────────────────────
    "RBLX", "EA", "TTWO", "SPOT",
    # ── High-beta momentum ───────────────────────────────────────────────────
    "GME", "AMC", "UWMC", "CLOV", "SPCE",
    "SNDL", "NKLA", "WKHS",
    # ── S&P 500 high-volume liquid names ─────────────────────────────────────
    "AAON", "ACM", "AES", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN",
    "ALK", "ALL", "ALLE", "ANET", "AON", "APA", "APD", "APH", "APTV",
    "ARE", "ATO", "AVB", "AWK", "AXP", "AZO", "BBY", "BDX",
    "BEN", "BIO", "BK", "BMRN", "BR", "BRO", "BSX", "BXP",
    "CB", "CBOE", "CBRE", "CDW", "CE", "CF", "CHD", "CHRW", "CHTR",
    "CI", "CINF", "CLX", "CMCSA", "CMS", "CNC", "CNP", "COF", "COO",
    "CPRT", "CPT", "CSX", "CTAS", "CTSH", "CTVA", "CVS",
    "D", "DAL", "DFS", "DG", "DHI", "DHR", "DLR", "DLTR",
    "DOV", "DPZ", "DRI", "DTE", "DUK", "DVA", "EFX", "EG", "EIX",
    "EL", "EMN", "EMR", "ES", "ESS", "EW", "EXC", "EXPD",
    "EXPE", "EXR", "FAST", "FDX", "FIS", "FMC",
    "FOX", "FOXA", "FRT", "GD", "GL", "HAS", "HCA", "HII",
    "HLT", "HOLX", "HPQ", "HRL", "HSIC", "HST", "HSY", "HWM",
    "ICE", "IDXX", "IEX", "IFF", "ILMN", "INCY", "IP", "IPG",
    "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ", "J", "JBHT",
    "JCI", "JKHY", "JNJ", "JNPR", "K", "KEY", "KHC", "KIM",
    "KMB", "KMI", "KMX", "KO", "KR", "L", "LDOS", "LEN", "LH",
    "LIN", "LKQ", "LNT", "LUV", "LVS", "LYB", "LYV",
    "MAA", "MAR", "MAS", "MCD", "MCK", "MCO", "MDLZ",
    "MDT", "MET", "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC",
    "MNST", "MO", "MOS", "MPC", "MPWR", "MSCI",
    "MSI", "MTB", "MTCH", "MTD", "NDAQ", "NEE", "NEM",
    "NI", "NRG", "NSC", "NTAP",
    "NTRS", "NUE", "NVAX", "NVR", "NWL", "NWS", "NWSA", "NXPI",
    "O", "OGN", "OKE", "OMC", "OPEN", "OPK", "ORLY", "OTIS",
    "PARA", "PAYC", "PAYX", "PEG", "PEP", "PFG", "PGR", "PH",
    "PHM", "PKG", "PLD", "PM", "PNC", "PNR", "PNW", "POOL",
    "PPG", "PPL", "PRU", "PSA", "PSX", "PTC", "PVH", "PWR",
    "QRVO", "RCL", "REG", "RF", "RHI",
    "RL", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG",
    "SBAC", "SBUX", "SEE", "SHW", "SJM", "SNA", "SNPS",
    "SO", "SPG", "SPGI", "SRE", "STT", "STX", "STZ", "SWK",
    "SWKS", "SYF", "SYK", "SYY", "T", "TAP", "TDG", "TDY", "TEL",
    "TER", "TFC", "TFX", "TJX", "TMO", "TMUS", "TPR",
    "TRMB", "TROW", "TRV", "TSCO", "TT",
    "TXT", "TYL", "UAL", "UDR", "UHS", "ULTA", "UNH", "UNP",
    "UPS", "URI", "USB", "VFC", "VLO", "VMC", "VNO", "VNT",
    "VRSK", "VRSN", "VTR", "VZ", "WAB", "WAT", "WBA",
    "WBD", "WDC", "WEC", "WELL", "WHR", "WM", "WMB", "WRB",
    "WST", "WTW", "WY", "WYNN", "XEL", "XYL", "YUM",
    "ZBH", "ZBRA", "ZION", "ZTS",
]

SECTOR_ETFS = ["XLK", "XLV", "XLE", "XLF", "XLI", "XLY"]

# symbol → sector ETF, used to boost picks sitting in a hot sector
SECTOR_MAP: dict[str, str] = {
    **{s: "XLK" for s in [
        "AAPL", "MSFT", "NVDA", "AMD", "META", "GOOGL", "AMZN", "AVGO", "QCOM",
        "MU", "MRVL", "AMAT", "LRCX", "KLAC", "INTC", "TXN", "ON", "MCHP",
        "SMCI", "ARM", "SLAB", "CRM", "NOW", "SNOW", "PLTR", "ORCL", "ADBE",
        "WDAY", "TEAM", "PANW", "CRWD", "ZS", "FTNT", "DDOG", "NET", "CYBR",
        "S", "DELL", "HPE", "IONQ", "RGTI", "QUBT", "SNPS", "CDNS", "TER",
        "MPWR", "NXPI", "SWKS", "QRVO", "AKAM", "JNPR", "NTAP", "STX", "WDC",
    ]},
    **{s: "XLF" for s in [
        "V", "MA", "PYPL", "SQ", "JPM", "BAC", "GS", "MS", "C", "WFC",
        "BX", "BLK", "SCHW", "IBKR", "RJF", "COIN", "HOOD", "SOFI", "AFRM",
        "MARA", "RIOT", "CLSK", "HUT", "CIFR", "COF", "AXP", "DFS", "SYF",
        "BK", "STT", "NTRS", "TROW", "IVZ", "BEN", "AIG", "MET", "PRU",
        "AFL", "ALL", "TRV", "CB", "PGR", "CINF", "EG", "WRB",
    ]},
    **{s: "XLE" for s in [
        "XOM", "CVX", "COP", "OXY", "MRO", "DVN", "FANG", "HES", "EOG",
        "SLB", "HAL", "BKR", "NOG", "SM", "PLUG", "NRG", "AES", "NEE",
        "DUK", "SO", "D", "EXC", "XEL", "SRE", "ES", "ATO", "LNT",
        "PNW", "CNP", "NI", "EIX", "PPL", "PEG", "WEC", "CMS",
    ]},
    **{s: "XLV" for s in [
        "LLY", "NVO", "ABBV", "MRK", "PFE", "BMY", "AMGN", "GILD", "REGN",
        "VRTX", "MRNA", "BNTX", "BIIB", "ALNY", "EXAS", "RXRX", "ACHR",
        "JNJ", "ABT", "MDT", "BSX", "EW", "SYK", "ISRG", "BDX", "DHR",
        "TMO", "IQV", "CNC", "UNH", "HCA", "CVS", "MCK", "CI",
        "HOLX", "IDXX", "MTD", "BMRN", "INCY",
    ]},
    **{s: "XLI" for s in [
        "GE", "CAT", "BA", "RTX", "LMT", "NOC", "DE", "HON", "MMM",
        "EMR", "ITW", "ROK", "PH", "ETN", "IR", "OTIS", "CARR",
        "LUNR", "RKLB", "F", "GM", "RIVN", "LCID", "NIO", "LI", "XPEV",
        "ENPH", "FSLR", "UPS", "FDX", "CSX", "UNP", "NSC", "WAB",
        "JBHT", "CHRW", "EXPD", "XYL", "ROP", "FAST", "GD", "HII",
        "LDOS", "ACM", "PWR", "VMC", "MLM", "SWK", "TXT", "HWM",
    ]},
    **{s: "XLY" for s in [
        "TSLA", "WMT", "COST", "TGT", "HD", "LOW", "NKE", "DIS",
        "NFLX", "UBER", "LYFT", "DASH", "BKNG", "ABNB", "RBLX", "EA",
        "TTWO", "SPOT", "GME", "AMC", "SPCE", "WKHS",
        "MCD", "SBUX", "YUM", "DPZ", "DRI", "CHTR", "CMCSA",
        "NWS", "FOXA", "PARA", "WBD",
        "RL", "PVH", "TPR", "VFC", "HAS", "MAT",
        "ULTA", "TJX", "ROST", "KMX", "AN", "AZO", "ORLY",
        "LVS", "WYNN", "MGM", "CZR", "RCL", "CCL", "NCLH", "MAR", "HLT",
    ]},
}
