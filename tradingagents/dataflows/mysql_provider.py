"""
MySQL Database Provider for TradingAgents

Provides stable stock data from MySQL database to replace unstable AKShare API.
Database contains:
- stock_history_daily_info_entity: OHLCV daily data (16M+ rows, 5371 stocks, 1990-2026)
- alpha_factor_data: Alpha factors (11K+ rows)
- backtest_result_entity: Backtesting results (2K+ rows)
- stock_value_entity: Stock valuation data
- stock_comment_entity: Analyst comments and scores

Connection: Configurable via environment variables or defaults to 8.137.104.120:3306
"""

from typing import Annotated
from datetime import datetime
import os
import pandas as pd
import pymysql
from contextlib import contextmanager
from .symbol_utils import normalize_symbol, NoMarketDataError


# MySQL Database Configuration
# IMPORTANT: Configure via environment variables in .env file
# Do NOT commit .env to version control
#
# Required environment variables:
#   MYSQL_DB_HOST     - Database host (e.g., localhost, 8.137.104.120)
#   MYSQL_DB_PORT     - Database port (default: 3306)
#   MYSQL_DB_USER     - Database username
#   MYSQL_DB_PASSWORD - Database password (REQUIRED)
#   MYSQL_DB_NAME     - Database name (default: akshare)
#   MYSQL_DB_CHARSET  - Character set (default: utf8mb4)
#
# Security Note: Never hardcode passwords in source code.
# Always use environment variables or a secrets manager.

_mysql_password = os.getenv('MYSQL_DB_PASSWORD')
if not _mysql_password:
    import warnings
    warnings.warn(
        "MYSQL_DB_PASSWORD environment variable is not set. "
        "Please add it to your .env file. See .env.example for reference.",
        UserWarning,
        stacklevel=2
    )

DB_CONFIG = {
    'host': os.getenv('MYSQL_DB_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_DB_PORT', '3306')),
    'user': os.getenv('MYSQL_DB_USER', 'root'),
    'password': _mysql_password or '',  # Empty if not set - will fail connection
    'database': os.getenv('MYSQL_DB_NAME', 'akshare'),
    'charset': os.getenv('MYSQL_DB_CHARSET', 'utf8mb4')
}


@contextmanager
def get_db_connection():
    """Get database connection with context manager."""
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def get_mysql_stock(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "end date in YYYY-MM-DD format"],
) -> str:
    """
    Get stock OHLCV data from MySQL database.
    
    This provides stable, fast access to historical stock data without
    relying on external APIs. Data is pre-populated and updated regularly.
    
    Args:
        symbol: Stock ticker (e.g., '600519', '600519.SS', '600519.SH')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        String with OHLCV data for each date in format:
        Date | Open | High | Low | Close | Volume | Amount
        
    Example:
        >>> result = get_mysql_stock('600519', '2025-01-01', '2025-06-01')
        >>> print(result)
        Date       | Open   | High   | Low    | Close  | Volume  | Amount
        2025-01-02 | 1500.0 | 1520.0 | 1495.0 | 1510.0 | 1234567 | 1865432100.0
    """
    try:
        # Normalize symbol to pure numeric code
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        
        with get_db_connection() as conn:
            query = """
                SELECT 
                    date as Date,
                    open as Open,
                    high as High,
                    low as Low,
                    close as Close,
                    volume as Volume,
                    Trading_Value as Amount
                FROM stock_history_daily_info_entity
                WHERE symbol = %s
                  AND date >= %s
                  AND date <= %s
                ORDER BY date ASC
            """
            
            df = pd.read_sql(query, conn, params=[stock_code, start_date, end_date])
            
            if df.empty:
                # Raise NoMarketDataError to trigger fallback to next vendor
                raise NoMarketDataError(symbol, stock_code, f"No data found for stock {symbol} between {start_date} and {end_date}")
            
            # Format dates
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            # Build output string
            lines = []
            lines.append(f"Stock: {symbol} ({stock_code})")
            lines.append(f"Period: {start_date} to {end_date}")
            lines.append(f"Data Points: {len(df)}")
            lines.append("-" * 80)
            lines.append("Date       | Open   | High   | Low    | Close  | Volume  | Amount")
            lines.append("-" * 80)
            
            for _, row in df.iterrows():
                line = f"{row['Date']} | {row['Open']:8.2f} | {row['High']:8.2f} | {row['Low']:8.2f} | {row['Close']:8.2f} | {int(row['Volume']):8d} | {row['Amount']:,.2f}"
                lines.append(line)
            
            return "\n".join(lines)
            
    except NoMarketDataError:
        # Re-raise NoMarketDataError to trigger fallback
        raise
    except Exception as e:
        # For other errors (connection, query, etc.), also raise NoMarketDataError
        # to allow fallback to other vendors like yfinance
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        raise NoMarketDataError(symbol, stock_code, f"MySQL provider error for {symbol}: {str(e)}")


def get_mysql_indicators(
    symbol: Annotated[str, "ticker symbol"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "current date"],
    look_back_days: Annotated[int, "look back days"] = 60,
) -> str:
    """
    Get technical indicators from MySQL database.
    
    Note: Currently returns raw OHLCV data. Technical indicators should be
    calculated locally using pandas-ta library.
    
    Args:
        symbol: Stock ticker
        indicator: Indicator name (for compatibility, not used directly)
        curr_date: Current date in YYYY-MM-DD format
        look_back_days: Number of days to look back
    
    Returns:
        String with OHLCV data suitable for indicator calculation
    """
    try:
        from datetime import timedelta
        
        # Calculate start date
        end_dt = datetime.strptime(curr_date, '%Y-%m-%d')
        start_dt = end_dt - timedelta(days=look_back_days + 30)  # Extra buffer
        start_date = start_dt.strftime('%Y-%m-%d')
        
        # Get OHLCV data
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        
        with get_db_connection() as conn:
            query = """
                SELECT 
                    date as Date,
                    open as Open,
                    high as High,
                    low as Low,
                    close as Close,
                    volume as Volume
                FROM stock_history_daily_info_entity
                WHERE symbol = %s
                  AND date >= %s
                  AND date <= %s
                ORDER BY date ASC
            """
            
            df = pd.read_sql(query, conn, params=[stock_code, start_date, curr_date])
            
            if df.empty:
                # Try with extended date range
                start_dt = end_dt - timedelta(days=365)  # Look back 1 year
                start_date = start_dt.strftime('%Y-%m-%d')
                
                df = pd.read_sql(query, conn, params=[stock_code, start_date, curr_date])
                
                if df.empty:
                    raise NoMarketDataError(symbol, stock_code, f"No data found for calculating {indicator} for {symbol} (checked last 365 days)")
            
            # Format output
            lines = []
            lines.append(f"Technical Data for {symbol} ({stock_code})")
            lines.append(f"Indicator: {indicator}")
            lines.append(f"Period: {start_date} to {curr_date} ({len(df)} days)")
            lines.append("-" * 80)
            lines.append("Date       | Open   | High   | Low    | Close  | Volume")
            lines.append("-" * 80)
            
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            for _, row in df.iterrows():
                line = f"{row['Date']} | {row['Open']:8.2f} | {row['High']:8.2f} | {row['Low']:8.2f} | {row['Close']:8.2f} | {int(row['Volume']):8d}"
                lines.append(line)
            
            return "\n".join(lines)
            
    except NoMarketDataError:
        raise
    except Exception as e:
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        raise NoMarketDataError(symbol, stock_code, f"MySQL indicator error for {symbol}: {str(e)}")


def get_mysql_fundamentals(
    symbol: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date"],
) -> str:
    """
    Get fundamental data from MySQL database.
    
    Retrieves stock valuation metrics and analyst ratings.
    
    Args:
        symbol: Stock ticker
        curr_date: Current date in YYYY-MM-DD format
    
    Returns:
        String with fundamental data
    """
    try:
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        
        with get_db_connection() as conn:
            # Get stock name
            cursor = conn.cursor()
            cursor.execute(
                "SELECT stock_name FROM stock_name_entity WHERE symbol = %s LIMIT 1",
                [stock_code]
            )
            name_result = cursor.fetchone()
            stock_name = name_result[0] if name_result else "Unknown"
            
            # Get valuation data
            query = """
                SELECT 
                    TRADE_DATE as Date,
                    CLOSE_PRICE as ClosePrice,
                    TOTAL_MARKET_CAP as MarketCap,
                    PE_TTM as PERatio,
                    PB_MRQ as PBRatio,
                    PS_TTM as PSRatio,
                    CHANGE_RATE as ChangeRate
                FROM stock_value_entity
                WHERE symbol = %s
                ORDER BY TRADE_DATE DESC
                LIMIT 5
            """
            
            df_valuation = pd.read_sql(query, conn, params=[stock_code])
            
            # Get analyst scores
            query_score = """
                SELECT 
                    TRADE_DATE as Date,
                    TOTALSCORE as TotalScore,
                    CLOSE_PRICE as Price,
                    ORG_PARTICIPATE as OrgCount
                FROM stock_comment_entity
                WHERE symbol = %s
                ORDER BY TRADE_DATE DESC
                LIMIT 5
            """
            
            df_score = pd.read_sql(query_score, conn, params=[stock_code])
            
            # Build output
            lines = []
            lines.append(f"Fundamental Data for {symbol} ({stock_name})")
            lines.append(f"As of: {curr_date}")
            lines.append("=" * 80)
            
            if not df_valuation.empty:
                lines.append("\n📊 Valuation Metrics (Latest 5 Days):")
                lines.append("-" * 80)
                
                df_valuation['Date'] = pd.to_datetime(df_valuation['Date']).dt.strftime('%Y-%m-%d')
                
                for _, row in df_valuation.iterrows():
                    lines.append(f"\nDate: {row['Date']}")
                    lines.append(f"  Close Price:      ¥{row['ClosePrice']:.2f}")
                    if pd.notna(row['MarketCap']):
                        lines.append(f"  Market Cap:       ¥{row['MarketCap']/1e8:.2f}亿")
                    if pd.notna(row['PERatio']):
                        lines.append(f"  P/E Ratio (TTM):  {row['PERatio']:.2f}")
                    if pd.notna(row['PBRatio']):
                        lines.append(f"  P/B Ratio (MRQ):  {row['PBRatio']:.2f}")
                    if pd.notna(row['PSRatio']):
                        lines.append(f"  P/S Ratio (TTM):  {row['PSRatio']:.2f}")
                    if pd.notna(row['ChangeRate']):
                        lines.append(f"  Change Rate:      {row['ChangeRate']:.2f}%")
            
            if not df_score.empty:
                lines.append("\n📈 Analyst Ratings (Latest 5 Days):")
                lines.append("-" * 80)
                
                df_score['Date'] = pd.to_datetime(df_score['Date']).dt.strftime('%Y-%m-%d')
                
                for _, row in df_score.iterrows():
                    lines.append(f"\nDate: {row['Date']}")
                    lines.append(f"  Total Score:      {row['TotalScore']:.2f}/10")
                    lines.append(f"  Price:            ¥{row['Price']:.2f}")
                    lines.append(f"  Participating Orgs: {int(row['OrgCount'])}")
            
            return "\n".join(lines)
            
    except NoMarketDataError:
        raise
    except Exception as e:
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        raise NoMarketDataError(symbol, stock_code, f"MySQL fundamentals error for {symbol}: {str(e)}")


def get_mysql_news(
    symbol: Annotated[str, "ticker symbol"],
    num_of_news: Annotated[int, "number of news articles"] = 5,
) -> str:
    """
    Get news/analyst comments from MySQL database.
    
    Note: Currently returns analyst comments as proxy for news.
    
    Args:
        symbol: Stock ticker
        num_of_news: Number of news items to retrieve
    
    Returns:
        String with news/comment data
    """
    try:
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        
        with get_db_connection() as conn:
            query = """
                SELECT 
                    TRADE_DATE as Date,
                    SECURITY_NAME_ABBR as StockName,
                    TOTALSCORE as Score,
                    CLOSE_PRICE as Price,
                    PRIME_COST as PrimeCost
                FROM stock_comment_entity
                WHERE symbol = %s
                ORDER BY TRADE_DATE DESC
                LIMIT %s
            """
            
            df = pd.read_sql(query, conn, params=[stock_code, num_of_news])
            
            if df.empty:
                raise NoMarketDataError(symbol, stock_code, f"No news/comments found for {symbol}")
            
            lines = []
            lines.append(f"Analyst Comments for {symbol}")
            lines.append(f"Latest {len(df)} entries")
            lines.append("=" * 80)
            
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            for i, (_, row) in enumerate(df.iterrows(), 1):
                lines.append(f"\n{i}. Date: {row['Date']}")
                lines.append(f"   Stock: {row['StockName']}")
                lines.append(f"   Analyst Score: {row['Score']:.2f}/10")
                lines.append(f"   Price: ¥{row['Price']:.2f}")
                if pd.notna(row['PrimeCost']):
                    lines.append(f"   Prime Cost: ¥{row['PrimeCost']:.2f}")
            
            return "\n".join(lines)
            
    except NoMarketDataError:
        raise
    except Exception as e:
        canonical = normalize_symbol(symbol)
        stock_code = canonical.split('.')[0] if '.' in canonical else canonical
        raise NoMarketDataError(symbol, stock_code, f"MySQL news error for {symbol}: {str(e)}")


# Export functions for interface.py
get_stock = [get_mysql_stock, "OHLCV stock price data from MySQL database"]
get_indicators = [get_mysql_indicators, "Technical indicator data from MySQL"]
get_fundamentals = [get_mysql_fundamentals, "Company fundamentals from MySQL"]
get_news = [get_mysql_news, "News and analyst comments from MySQL"]
