"""
Universe of tradeable stocks.

Contains the 200 stock tickers used for trading and backtesting.
"""

from typing import List

UNIVERSE: List[str] = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "ORCL",
    "CRM", "ADBE", "NFLX", "AMD", "INTC", "QCOM", "TXN", "AMAT", "MU", "LRCX",
    "KLAC", "ADI", "NXPI", "TSM", "ASML", "IBM", "NOW", "INTU", "CSCO", "PANW",
    "CRWD", "ZS", "NET", "DDOG", "SNOW", "PLTR", "SHOP", "UBER", "ABNB", "PYPL",
    "SQ", "T", "VZ", "TMUS", "CMCSA", "DIS",
    
    # Financials
    "BRK.B", "JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "BLK", "AXP",
    "V", "MA", "SPGI", "CME", "ICE", "CB", "PGR", "ALL", "COF", "USB",
    "PNC", "TFC", "BK", "STT", "MMC", "AJG", "AON",
    
    # Healthcare
    "UNH", "LLY", "JNJ", "MRK", "ABBV", "AMGN", "PFE", "BMY", "GILD", "TMO",
    "DHR", "MDT", "SYK", "BSX", "ISRG", "ELV", "CVS", "CI", "HUM", "ZTS",
    "REGN", "VRTX", "BIIB", "ILMN", "MCK", "BDX", "DXCM",
    
    # Consumer
    "PG", "KO", "PEP", "COST", "WMT", "MDLZ", "PM", "MO", "CL", "GIS",
    "KHC", "KR", "TGT", "TJX", "CMG", "MCD", "SBUX", "LOW", "HD", "NKE",
    "BKNG", "MAR", "HLT", "MNST", "YUM",
    
    # Industrials
    "CAT", "DE", "HON", "GE", "BA", "LMT", "RTX", "NOC", "GD", "LHX",
    "ITW", "EMR", "ETN", "PH", "MMM", "CARR", "CSX", "NSC", "UNP", "UPS",
    "FDX", "WM", "RSG", "GWW", "JCI", "GNRC",
    
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC", "VLO", "PSX", "KMI",
    "WMB", "OKE",
    
    # Materials
    "LIN", "APD", "SHW", "ECL", "FCX", "NUE", "STLD", "DOW", "DD", "ALB",
    "NEM", "GOLD",
    
    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "XEL", "SRE", "PEG", "ETR", "ED",
    
    # Real Estate
    "AMT", "PLD", "CCI", "EQIX", "SPG", "O", "WELL", "VICI", "PSA", "DLR",
    "CBRE", "AVB", "EQR", "ARE",
]


def get_universe() -> List[str]:
    """
    Get the full list of tradeable symbols.
    
    Returns:
        List[str]: List of stock ticker symbols.
    """
    return UNIVERSE.copy()


def get_universe_with_proxy(proxy: str = "SPY") -> List[str]:
    """
    Get the universe plus the market proxy symbol.
    
    Args:
        proxy: Market proxy symbol (default SPY).
    
    Returns:
        List[str]: List of symbols including proxy.
    """
    symbols = get_universe()
    if proxy not in symbols:
        symbols.append(proxy)
    return symbols

