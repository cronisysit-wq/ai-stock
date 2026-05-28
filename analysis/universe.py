"""
Stock Universe — curated lists of tradeable symbols.

Sources represented (hardcoded for reliability / offline use):
  - S&P 500 large-caps (top 400 by weight)
  - NASDAQ-100 non-S&P constituents
  - High-volume day-trading favorites
  - Popular ETFs for market breadth reference

Usage:
    from analysis.universe import get_universe
    tickers = get_universe("sp500")          # ~400 S&P 500 stocks
    tickers = get_universe("nasdaq100")      # NASDAQ-100
    tickers = get_universe("day_trading")    # high-vol momentum names
    tickers = get_universe("all")            # full combined universe
    tickers = get_universe("etf")            # major ETFs
"""

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# ── S&P 500 top components (by index weight / liquidity) ──────────────────────
SP500: List[str] = [
    # Mega-cap tech
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AVGO","ORCL",
    # Financials
    "BRK.B","JPM","V","MA","BAC","WFC","GS","MS","AXP","BLK","SCHW","COF","USB","PNC","TFC","MTB","CFG","FITB","HBAN","KEY",
    # Healthcare
    "UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN","ISRG","GILD","CI","CVS","HCA","SYK","BDX","MDT","ZTS","VRTX","REGN","BSX","A","IQV",
    # Consumer
    "WMT","HD","MCD","NKE","SBUX","TJX","LOW","TGT","COST","PG","KO","PEP","PM","MO","CL","GIS","KHC","K","HSY","SJM","CAG",
    # Energy
    "XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","PXD","OXY","DVN","FANG","HES","BKR","HAL","APA","MRO","CTRA",
    # Industrials
    "CAT","DE","GE","HON","UPS","RTX","LMT","NOC","BA","GD","MMM","EMR","ETN","PH","ROK","CMI","PCAR","ITW","IEX","IR","XYL",
    # Technology (mid)
    "CRM","ADBE","AMD","INTC","QCOM","TXN","MU","AMAT","LRCX","KLAC","ADI","MRVL","CDNS","SNPS","KEYS","ANSS","FLIR",
    # Communication
    "NFLX","DIS","CMCSA","T","VZ","TMUS","CHTR","PARA","FOX","FOXA","WBD","LYV","OMC","IPG","NWS",
    # Utilities
    "NEE","DUK","SO","AEP","EXC","SRE","D","PCG","ES","ETR","FE","PPL","CMS","AES","NI","LNT","EVRG",
    # Real Estate
    "AMT","PLD","CCI","EQIX","PSA","SPG","O","WELL","DLR","AVB","EQR","VTR","ARE","MAA","CPT","AIR",
    # Materials
    "LIN","APD","SHW","FCX","NEM","DOW","DD","NUE","CF","MOS","ALB","FMC","PPG","EMN","IFF","CE",
    # More large-caps
    "UBER","LYFT","ABNB","SNAP","PINS","ETSY","EBAY","PYPL","SQ","COIN","HOOD","SOFI","AFRM","UPST",
    "ZM","DOCU","OKTA","CRWD","PANW","FTNT","ZS","NET","DDOG","SNOW","PLTR","PATH","AI","C3AI",
    "SHOP","SE","MELI","BABA","JD","PDD","BIDU","NIO","XPEV","LI","DIDI","GRAB",
    "SPOT","ROKU","TTD","PUBM","MGNI","APPS","RBLX","U","UNITY",
    "ABNB","BKNG","EXPE","TRIP","WYNN","MGM","CZR","PENN","DKNG","LVS","MTN","MAR","HLT","H","IHG",
]

# ── NASDAQ-100 non-overlap additions ──────────────────────────────────────────
NASDAQ100_EXTRA: List[str] = [
    "ASML","AZN","MCHP","NXPI","SWKS","QRVO","MPWR","ENTG","LAM","AMAT","XLNX",
    "IDXX","ALGN","ILMN","SGEN","BMRN","EXAS","HOLX","PODD","DXCM","GEHC",
    "CSGP","FAST","ODFL","CPRT","PAYX","ADP","VRSK","ANSS","CDNS","SNPS",
    "SIRI","LOGI","WDC","STX","NTAP","PSTG","DELL","HPQ","HPE","CSCO","JNPR",
    "AKAM","AKAMAI","FFIV","NLOK","CHKP","CYBR","QLYS","TENB","MIME","VRNS",
    "CEG","VST","EXE","NRG","AEE","CNP","OGE","CLECO","ATO","WEC","LNT",
    "ORLY","AZO","AAP","SNA","GPC","LKQ","DG","DLTR","FIVE","OLLI","BIG",
]

# ── High-volume day-trading favorites ─────────────────────────────────────────
DAY_TRADING: List[str] = [
    # Mega momentum / frequently traded
    "TSLA","NVDA","AMD","AAPL","AMZN","META","GOOGL","MSFT","NFLX","SPY","QQQ",
    # High-beta tech
    "MSTR","RIOT","MARA","CIFR","BITF","HUT","CLSK","IREN","WULF",
    "SMCI","AEHR","LSCC","WOLF","ON","ENPH","FSLR","SEDG","ARRY","CSIQ","MAXN",
    # Biotech / high-vol
    "MRNA","BNTX","SGEN","INCY","EXAS","ARKG","XBI","IBB",
    "LABU","SRPT","IONS","REGN","VRTX","BMRN","RARE","FOLD","ARDX",
    # EV / clean energy
    "RIVN","LCID","FSR","NKLA","GOEV","FFIE","MULN","BLNK","CHPT","EVGO",
    "STEM","NOVA","RUN","SPWR","PLUG","BE","FCEL","BLDP","HYLN",
    # Financial / fintech momentum
    "COIN","HOOD","SOFI","AFRM","UPST","LC","OPFI","DAVE","CURO","WU",
    "PYPL","SQ","V","MA","AXP","DFS","COF","SYF","ALLY","CACC",
    # Options-popular / meme stocks
    "GME","AMC","BB","BBBY","EXPR","KOSS","NAKD","SNDL","CLOV","WISH",
    "SPCE","PAYO","OPEN","OFFERPAD","RDFN","Z","ZG","OPENDOOR",
    # Sector ETFs (day-trading breadth)
    "XLK","XLF","XLE","XLV","XLI","XLC","XLP","XLU","XLRE","XLB","XLY",
    "SOXS","SOXL","TQQQ","SQQQ","SPXU","UPRO","UDOW","SDOW","LABD","LABU",
    # Popular swing + day
    "BABA","JD","PDD","KWEB","FXI","EEM","EFA","VWO","GLD","SLV","USO","UNG",
    "TLT","HYG","LQD","IEF","SHY","TIPS","DXY","UUP","FXE","EWJ","EWZ",
]

# ── Major ETFs ─────────────────────────────────────────────────────────────────
ETFS: List[str] = [
    "SPY","QQQ","IWM","DIA","VTI","VOO","VEA","VWO","EEM","EFA",
    "GLD","SLV","IAU","PDBC","USO","UNG","BNO",
    "TLT","IEF","SHY","HYG","LQD","TIPS","MUB",
    "XLK","XLF","XLE","XLV","XLI","XLC","XLP","XLU","XLRE","XLB","XLY",
    "SOXL","SOXS","TQQQ","SQQQ","UPRO","SPXU","UDOW","SDOW","LABU","LABD",
    "ARKK","ARKW","ARKG","ARKF","ARKQ","ARKX",
    "IBB","XBI","HACK","CIBR","BOTZ","ROBO","AIQ","UFO","MOON",
    "KWEB","FXI","MCHI","EWJ","EWZ","INDA","VGK","EWU","EWC","EWA",
    "VNQ","IYR","XLRE","REZ","REM","MORT",
]

# ── Sector-categorized fast-access lists ──────────────────────────────────────
SECTORS = {
    "technology": ["AAPL","MSFT","NVDA","AMD","INTC","QCOM","AVGO","TXN","MU","AMAT",
                   "LRCX","KLAC","ADI","MRVL","CDNS","SNPS","CRM","ADBE","ORCL","SAP",
                   "NOW","WDAY","TEAM","ZM","DOCU","OKTA","CRWD","PANW","FTNT","ZS",
                   "NET","DDOG","SNOW","PLTR","PATH","SMCI","DELL","HPQ","CSCO","JNPR"],
    "financials": ["JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","COF",
                   "USB","PNC","TFC","COIN","SQ","PYPL","HOOD","SOFI","AFRM","UPST"],
    "healthcare": ["UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","AMGN","ISRG","GILD",
                   "VRTX","REGN","MRNA","BNTX","BMRN","INCY","SGEN","IONS","EXAS"],
    "energy":     ["XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","OXY","DVN",
                   "FANG","HES","BKR","HAL","APA","MRO","PLUG","BE","FCEL","ENPH","FSLR"],
    "consumer":   ["AMZN","WMT","HD","MCD","NKE","SBUX","TJX","COST","TGT","LOW",
                   "TSLA","RIVN","LCID","SHOP","ETSY","EBAY","BKNG","ABNB","EXPE"],
    "ev_clean":   ["TSLA","RIVN","LCID","NIO","XPEV","LI","FSR","NKLA","BLNK","CHPT",
                   "EVGO","ENPH","FSLR","SEDG","ARRY","RUN","SPWR","STEM","NOVA","PLUG"],
    "biotech":    ["MRNA","BNTX","SGEN","REGN","VRTX","BMRN","INCY","IONS","SRPT",
                   "EXAS","RARE","FOLD","ARDX","ARKG","XBI","IBB","LABU"],
    "crypto_adj": ["COIN","MSTR","RIOT","MARA","CIFR","BITF","HUT","CLSK","IREN","WULF","HOOD"],
}

# Robinhood-popular: high retail interest names beyond index lists
ROBINHOOD_POPULAR: List[str] = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AMD","INTC","NFLX","DIS",
    "HOOD","SOFI","PLTR","GME","AMC","COIN","MSTR","RIVN","LCID","NIO","XPEV","SNAP",
    "PINS","UBER","LYFT","ABNB","DASH","DKNG","PENN","WYNN","MGM","SPCE","OPEN",
    "PYPL","SQ","V","MA","AFRM","UPST","LC","NU","BABA","JD","PDD","NIO","GRAB",
    "SMCI","ARM","IONQ","RGTI","QUBT","SOUN","BBAI","AI","PATH","SNOW","DDOG","NET",
    "CRWD","PANW","ZS","OKTA","DOCU","ZM","ROKU","SPOT","RBLX","U","TTD","SHOP",
    "ETSY","W","CHWY","CVNA","CARVANA","BYND","WISH","CLOV","SNDL","TLRY","ACB",
    "MRNA","BNTX","NVAX","SGEN","XBI","LABU","ARKK","ARKG","SOXL","TQQQ","SQQQ",
    "SPY","QQQ","IWM","DIA","GLD","SLV","USO","BITO","GBTC","ETHE",
    "F","GM","TM","STLA","RACE","LI","FSR","GOEV","CHPT","PLUG","ENPH","FSLR",
    "JPM","BAC","GS","MS","SCHW","BLK","V","MA","AXP","COF","DFS","SYF",
    "WMT","TGT","COST","HD","LOW","NKE","SBUX","MCD","KO","PEP","PG","CL",
    "XOM","CVX","OXY","DVN","MPC","VLO","HAL","SLB",
    "UNH","JNJ","PFE","ABBV","LLY","MRK","BMY","GILD",
    "BRK.B","BRK-B","BRK.A","BRK-A",
]


def fetch_sp500_full() -> List[str]:
    """Fetch full S&P 500 ticker list from Wikipedia (~503 stocks). Merges with curated fallback."""
    fetched: List[str] = []
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        )
        for df in tables:
            for col in ("Symbol", "Ticker symbol", "Ticker"):
                if col in df.columns:
                    fetched = (
                        df[col].astype(str).str.replace(".", "-", regex=False).tolist()
                    )
                    break
            if fetched:
                break
        fetched = [t.upper() for t in fetched if t and t.lower() != "nan"]
    except Exception:
        fetched = []

    # Merge with curated list so offline/partial fetches still cover the index
    combined = fetched + SP500 + NASDAQ100_EXTRA
    seen: set = set()
    out: List[str] = []
    for t in combined:
        tu = t.upper().replace(".", "-")
        if tu not in seen:
            seen.add(tu)
            out.append(tu)
    return out


def get_robinhood_universe(include_etfs: bool = True) -> List[str]:
    """
    Robinhood-scale US universe: full NASDAQ/NYSE/AMEX directory (~8,000–11,000 symbols).

    Falls back to curated ~500 list if directory download fails.
    """
    try:
        from analysis.us_symbol_directory import fetch_all_us_symbols
        symbols = fetch_all_us_symbols(include_etfs=include_etfs, use_cache=True)
        if len(symbols) >= 1000:
            return symbols
    except Exception as exc:
        logger.warning("Full US symbol directory unavailable: %s", exc)

    # Fallback: curated merge
    sp500 = fetch_sp500_full()
    combined = sp500 + NASDAQ100_EXTRA + ROBINHOOD_POPULAR + DAY_TRADING
    seen: set = set()
    out: List[str] = []
    for t in combined:
        tu = t.upper().replace(".", "-")
        if tu not in seen:
            seen.add(tu)
            out.append(tu)
    return out


# Price-filtered presets scan Robinhood-scale US stocks and keep names in range at scan time.
PRICE_FILTER_PRESETS = {
    "penny_under_1": (0.01, 1.0),
    "penny_under_5": (0.01, 5.0),
    "price_1_10": (1.0, 10.0),
    "under_10": (0.01, 10.0),
}


def get_price_bounds(preset: str) -> tuple[Optional[float], Optional[float]]:
    """Return (min_price, max_price) for price-filter presets, else (None, None)."""
    bounds = PRICE_FILTER_PRESETS.get(preset.lower().strip())
    if not bounds:
        return None, None
    return bounds


def price_in_range(price: float, min_price: Optional[float], max_price: Optional[float]) -> bool:
    """True if price is within optional min/max bounds."""
    if price <= 0:
        return False
    if min_price is not None and price < min_price:
        return False
    if max_price is not None and price > max_price:
        return False
    return True


def resolve_scan_universe(
    preset: str,
    result_limit: Optional[int] = None,
) -> tuple[List[str], Optional[float], Optional[float]]:
    """
    Tickers to scan plus optional price bounds.

    Price-filter presets scan a large US candidate pool and filter by live price.
    """
    min_price, max_price = get_price_bounds(preset)
    tickers = get_universe(preset)
    if min_price is not None or max_price is not None:
        cap = result_limit or 250
        candidate_cap = min(len(tickers), max(cap * 25, 3000))
        tickers = tickers[:candidate_cap]
    elif result_limit and result_limit > 0:
        tickers = tickers[:result_limit]
    return tickers, min_price, max_price


def get_universe(preset: str = "all", min_price: float = 0.0, dedupe: bool = True) -> List[str]:
    """
    Return a list of tickers for the chosen preset.

    Parameters
    ----------
    preset : str
        "sp500"       — S&P 500 large-caps (curated)
        "sp500_full"  — Full S&P 500 from Wikipedia (~503)
        "robinhood"   — Full US listings via NASDAQ Trader (~8,000–11,000, Robinhood-scale)
        "robinhood_stocks" — US stocks only (no ETFs)
        "penny_under_1"  — US stocks; scan filters to price < $1
        "penny_under_5"  — US stocks; scan filters to price < $5 (penny / micro-cap)
        "price_1_10"     — US stocks; scan filters to $1–$10
        "under_10"       — US stocks; scan filters to price < $10
        "nasdaq100"   — NASDAQ-100 additions
        "day_trading" — High-vol day-trading favorites
        "etf"         — Major ETFs
        "sector:<name>"  — e.g. "sector:technology"
        "all"         — Full combined universe (default)
    min_price : float
        Filter placeholder (price filtering done at scan time)
    dedupe : bool
        Remove duplicates while preserving order.

    Returns
    -------
    List of uppercase ticker strings.
    """
    preset = preset.lower().strip()

    if preset.startswith("sector:"):
        name = preset.split(":", 1)[1]
        tickers = SECTORS.get(name, [])
    elif preset == "sp500":
        tickers = SP500
    elif preset == "sp500_full":
        tickers = fetch_sp500_full()
    elif preset == "robinhood":
        tickers = get_robinhood_universe(include_etfs=True)
    elif preset == "robinhood_stocks":
        tickers = get_robinhood_universe(include_etfs=False)
    elif preset in PRICE_FILTER_PRESETS:
        tickers = get_robinhood_universe(include_etfs=False)
    elif preset == "nasdaq100":
        tickers = NASDAQ100_EXTRA
    elif preset == "day_trading":
        tickers = DAY_TRADING
    elif preset == "etf":
        tickers = ETFS
    elif preset == "all":
        tickers = SP500 + NASDAQ100_EXTRA + DAY_TRADING + ETFS
    else:
        tickers = SP500 + NASDAQ100_EXTRA + DAY_TRADING

    result = [t.upper() for t in tickers]
    if dedupe:
        seen = set()
        deduped = []
        for t in result:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        result = deduped

    return result


def get_sector_for(ticker: str) -> str:
    """Return the sector label for a ticker, or 'unknown'."""
    ticker = ticker.upper()
    for sector, tickers in SECTORS.items():
        if ticker in [t.upper() for t in tickers]:
            return sector
    return "unknown"


def get_day_trading_universe() -> List[str]:
    """Short-list of ~150 tickers best suited for day trading (high liquidity + volatility)."""
    return get_universe("day_trading")


def get_full_universe() -> List[str]:
    """Full Robinhood-scale US universe (8,000+ symbols with ETFs)."""
    return get_universe("robinhood")
