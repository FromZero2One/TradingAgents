"""
AKShare data provider for TradingAgents.

AKShare is a powerful Python library for Chinese financial data, providing:
- A股 (Shanghai/Shenzhen)
- 港股 (Hong Kong)
- 美股 (US stocks via proxy)
- 期货 (Futures)
- 期权 (Options)
- 基金 (Funds)
- 债券 (Bonds)
- 指数 (Indices)
- 宏观经济 (Macroeconomics)

Documentation: https://akshare.akfamily.xyz/
"""

from typing import Annotated
from datetime import datetime
import pandas as pd
import akshare as ak
import pandas_ta as ta  # Technical analysis library
from .symbol_utils import normalize_symbol, NoMarketDataError


def _convert_akshare_date(date_str):
    """Convert various date formats to YYYY-MM-DD."""
    if isinstance(date_str, (int, float)):
        date_str = str(date_str)
    
    # Remove separators
    date_str = date_str.replace('-', '').replace('/', '').replace('.', '')
    
    # Convert to YYYY-MM-DD
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    elif len(date_str) == 10:
        return date_str
    
    return date_str


def get_akshare_stock(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    """
    Get stock OHLCV data from AKShare.
    
    Supports:
    - A股: 600519 (茅台), 000001 (平安)
    - 港股: 00700 (腾讯), 09988 (阿里)
    - 美股: AAPL, MSFT (需要代理或特殊配置)
    """
    try:
        # Normalize symbol
        canonical = normalize_symbol(symbol)
        
        # Determine market and adjust symbol format for AKShare
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market == "A":
            # A股使用 ak.stock_zh_a_hist
            df = ak.stock_zh_a_hist(
                symbol=ak_symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq"  # 前复权
            )
        elif market == "HK":
            # 港股使用 ak.stock_hk_hist
            df = ak.stock_hk_hist(
                symbol=ak_symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=""
            )
        else:
            raise NoMarketDataError(
                symbol, 
                canonical, 
                f"market '{market}' not supported by AKShare yet"
            )
        
        # Check if data is empty
        if df.empty:
            raise NoMarketDataError(
                symbol, 
                canonical, 
                f"no data between {start_date} and {end_date}"
            )
        
        # Rename columns to match yfinance format
        column_mapping = {
            '日期': 'Date',
            '开盘': 'Open',
            '最高': 'High',
            '最低': 'Low',
            '收盘': 'Close',
            '成交量': 'Volume',
            '成交额': 'Turnover'
        }
        
        # Only rename columns that exist
        rename_dict = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
        
        # Ensure Date column is in correct format
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
        
        # Round numerical values
        numeric_columns = ["Open", "High", "Low", "Close"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].round(2)
        
        # Convert to CSV
        csv_string = df.to_csv()
        
        # Add header
        label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
        header = f"# Stock data for {label} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Data source: AKShare ({market}股)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except NoMarketDataError:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "no data" in error_msg or "empty" in error_msg:
            raise NoMarketDataError(symbol, symbol, str(e))
        # For other errors (network, API, etc.), also raise NoMarketDataError
        # to allow fallback to other vendors like yfinance
        canonical = normalize_symbol(symbol)
        raise NoMarketDataError(symbol, canonical, f"AKShare provider error for {symbol}: {str(e)}")


def get_akshare_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for akshare)"] = None
):
    """
    Get company fundamentals from AKShare.
    
    Uses:
    - ak.stock_individual_info_em for basic info
    - ak.stock_financial_analysis_indicator for financial metrics
    """
    try:
        canonical = normalize_symbol(ticker)
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market != "A":
            raise NoMarketDataError(
                ticker, 
                canonical, 
                f"fundamentals only supported for A-shares in AKShare"
            )
        
        # Get basic company info
        info_df = ak.stock_individual_info_em(symbol=ak_symbol)
        
        # Get financial indicators
        try:
            financial_df = ak.stock_financial_analysis_indicator(symbol=ak_symbol)
            latest_financial = financial_df.iloc[-1] if not financial_df.empty else None
        except Exception as e:
            print(f"Warning: Could not fetch financial indicators: {e}")
            latest_financial = None
        
        # Build output
        lines = []
        
        # Company basic info
        if not info_df.empty:
            for _, row in info_df.iterrows():
                key = str(row.get('item', ''))
                value = str(row.get('value', ''))
                if key and value and value != 'None':
                    lines.append(f"{key}: {value}")
        
        # Financial metrics
        if latest_financial is not None:
            financial_fields = [
                ('每股收益', 'EPS'),
                ('净资产收益率', 'ROE'),
                ('总资产收益率', 'ROA'),
                ('销售毛利率', 'Gross Margin'),
                ('销售净利率', 'Net Margin'),
                ('资产负债率', 'Debt Ratio'),
                ('营业收入同比增长', 'Revenue Growth'),
                ('净利润同比增长', 'Profit Growth'),
            ]
            
            for cn_name, en_label in financial_fields:
                if cn_name in latest_financial.index:
                    value = latest_financial[cn_name]
                    if pd.notna(value):
                        lines.append(f"{en_label}: {value}")
        
        if not lines:
            raise NoMarketDataError(ticker, canonical, "no fundamental fields returned")
        
        header = f"# Company Fundamentals for {canonical} (AKShare)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + "\n".join(lines)
        
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_akshare_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from AKShare."""
    try:
        canonical = normalize_symbol(ticker)
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market != "A":
            raise NoMarketDataError(ticker, canonical, "only A-shares supported")
        
        # Use AKShare's financial statement API
        if freq.lower() == "quarterly":
            df = ak.stock_balance_sheet_by_report_em(symbol=ak_symbol)
        else:
            df = ak.stock_balance_sheet_by_report_yearly_em(symbol=ak_symbol)
        
        if df.empty:
            raise NoMarketDataError(ticker, canonical, "no balance sheet data")
        
        # Filter by curr_date if provided
        if curr_date:
            from .stockstats_utils import filter_financials_by_date
            df = filter_financials_by_date(df, curr_date)
        
        csv_string = df.to_csv()
        header = f"# Balance Sheet data for {canonical} ({freq})\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_akshare_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from AKShare."""
    try:
        canonical = normalize_symbol(ticker)
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market != "A":
            raise NoMarketDataError(ticker, canonical, "only A-shares supported")
        
        if freq.lower() == "quarterly":
            df = ak.stock_cash_flow_statement_em(symbol=ak_symbol)
        else:
            df = ak.stock_cash_flow_statement_yearly_em(symbol=ak_symbol)
        
        if df.empty:
            raise NoMarketDataError(ticker, canonical, "no cash flow data")
        
        if curr_date:
            from .stockstats_utils import filter_financials_by_date
            df = filter_financials_by_date(df, curr_date)
        
        csv_string = df.to_csv()
        header = f"# Cash Flow data for {canonical} ({freq})\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_akshare_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from AKShare."""
    try:
        canonical = normalize_symbol(ticker)
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market != "A":
            raise NoMarketDataError(ticker, canonical, "only A-shares supported")
        
        if freq.lower() == "quarterly":
            df = ak.stock_profit_statement_em(symbol=ak_symbol)
        else:
            df = ak.stock_profit_statement_yearly_em(symbol=ak_symbol)
        
        if df.empty:
            raise NoMarketDataError(ticker, canonical, "no income statement data")
        
        if curr_date:
            from .stockstats_utils import filter_financials_by_date
            df = filter_financials_by_date(df, curr_date)
        
        csv_string = df.to_csv()
        header = f"# Income Statement data for {canonical} ({freq})\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_akshare_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get insider transactions from AKShare (A股增减持数据)."""
    try:
        canonical = normalize_symbol(ticker)
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market != "A":
            return f"No insider transactions reported for symbol '{canonical}'"
        
        # Get insider trading data (股东增减持)
        df = ak.stock_sharehold_change_em(symbol=ak_symbol)
        
        if df.empty:
            return f"No insider transactions reported for symbol '{canonical}'"
        
        csv_string = df.to_csv()
        header = f"# Insider Transactions data for {canonical}\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def get_akshare_news(
    ticker: Annotated[str, "ticker symbol of the company"],
    limit: int = 20
):
    """Get news for a specific stock from AKShare."""
    try:
        canonical = normalize_symbol(ticker)
        ak_symbol, market = _convert_symbol_for_akshare(canonical)
        
        if market == "A":
            # A股新闻
            df = ak.stock_news_em(symbol=ak_symbol)
        elif market == "HK":
            # 港股新闻（使用通用新闻接口）
            df = ak.stock_news_em(symbol=ak_symbol)
        else:
            return f"No news available for {canonical} via AKShare"
        
        if df.empty:
            return f"No recent news found for symbol '{canonical}'"
        
        # Limit number of articles
        df = df.head(limit)
        
        # Format news
        news_lines = []
        for _, row in df.iterrows():
            title = row.get('标题', row.get('title', 'N/A'))
            content = row.get('内容', row.get('content', ''))
            publish_time = row.get('发布时间', row.get('publish_time', ''))
            source = row.get('来源', row.get('source', ''))
            
            news_item = f"[{publish_time}] {title}\n"
            if source:
                news_item += f"Source: {source}\n"
            if content:
                news_item += f"{content[:500]}...\n"  # Truncate long content
            news_item += "-" * 80 + "\n"
            news_lines.append(news_item)
        
        header = f"# News for {canonical}\n"
        header += f"# Total articles: {len(news_lines)}\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + "\n".join(news_lines)
        
    except Exception as e:
        return f"Error retrieving news for {ticker}: {str(e)}"


def get_akshare_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date for reference"],
    look_back_days: Annotated[int, "how many days to look back"] = 60,
) -> str:
    """
    Get technical indicators using pandas-ta library.
    
    Calculates indicators locally from OHLCV data obtained via AKShare.
    Supports 130+ indicators through pandas-ta library.
    
    Args:
        symbol: Stock ticker (e.g., '600519', '0700.HK')
        indicator: Indicator name (e.g., 'sma_50', 'macd', 'rsi')
        curr_date: Current date in YYYY-MM-DD format
        look_back_days: Number of days to look back
    
    Returns:
        String with indicator values for each date
    """
    try:
        from datetime import timedelta
        
        # Calculate date range (add extra days for indicator warm-up)
        end_date = curr_date
        start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - 
                      timedelta(days=look_back_days + 100)).strftime("%Y-%m-%d")
        
        # 1. Get OHLCV data from AKShare
        csv_data = get_akshare_stock(symbol, start_date, end_date)
        
        # Check if we got error message
        if csv_data.startswith("Error") or "NO_DATA" in csv_data:
            return csv_data
        
        # 2. Parse CSV data
        import io
        df = pd.read_csv(io.StringIO(csv_data), parse_dates=['Date'], index_col='Date')
        
        # Ensure we have required columns
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            return f"Error: Missing required columns. Have: {list(df.columns)}"
        
        # 3. Calculate indicators using pandas-ta
        indicator_lower = indicator.lower()
        
        # Map common indicator names to pandas-ta functions
        indicator_map = {
            'close_50_sma': ('sma', {'length': 50}),
            'close_200_sma': ('sma', {'length': 200}),
            'close_10_ema': ('ema', {'length': 10}),
            'macd': ('macd', {}),
            'macds': ('macd', {}),  # Will extract signal line
            'macdh': ('macd', {}),  # Will extract histogram
            'rsi': ('rsi', {'length': 14}),
            'boll': ('bbands', {}),  # Will extract middle band
            'boll_ub': ('bbands', {}),  # Will extract upper band
            'boll_lb': ('bbands', {}),  # Will extract lower band
            'atr': ('atr', {'length': 14}),
            'vwma': ('vwma', {'length': 20}),
            'mfi': ('mfi', {'length': 14}),
        }
        
        if indicator_lower not in indicator_map:
            available = list(indicator_map.keys())
            return f"Indicator '{indicator}' not supported. Available: {available}"
        
        # Calculate the indicator
        ta_func_name, ta_params = indicator_map[indicator_lower]
        
        # Use pandas-ta to calculate
        df_with_ta = df.ta.strategy(ta_func_name, **ta_params, append=True)
        
        if df_with_ta is None or df_with_ta.empty:
            return f"Error: Failed to calculate {indicator}"
        
        # Extract the specific column based on indicator type
        if indicator_lower in ['macds']:
            # MACD Signal line
            result_col = 'MACDs_12_26_9'
        elif indicator_lower in ['macdh']:
            # MACD Histogram
            result_col = 'MACDh_12_26_9'
        elif indicator_lower in ['boll']:
            # Bollinger Middle Band
            result_col = 'BBM_20_2.0'
        elif indicator_lower in ['boll_ub']:
            # Bollinger Upper Band
            result_col = 'BBU_20_2.0'
        elif indicator_lower in ['boll_lb']:
            # Bollinger Lower Band
            result_col = 'BBL_20_2.0'
        else:
            # For simple indicators, find the column
            result_col = None
            for col in df_with_ta.columns:
                if indicator_lower.replace('_', '') in col.lower():
                    result_col = col
                    break
            
            if result_col is None:
                # Try to find by pattern
                if 'sma' in indicator_lower:
                    length = int(''.join(filter(str.isdigit, indicator_lower)))
                    result_col = f'SMA_{length}'
                elif 'ema' in indicator_lower:
                    length = int(''.join(filter(str.isdigit, indicator_lower)))
                    result_col = f'EMA_{length}'
        
        if result_col not in df_with_ta.columns:
            raise NoMarketDataError(
                symbol=symbol,
                canonical=normalize_symbol(symbol),
                message=f"Could not find result column for {indicator}. Available: {list(df_with_ta.columns)}"
            )
        
        # 4. Format output
        result_lines = []
        recent_data = df_with_ta.iloc[-look_back_days:]
        
        for date, row in recent_data.iterrows():
            value = row[result_col]
            date_str = date.strftime('%Y-%m-%d')
            
            if pd.notna(value):
                result_lines.append(f"{date_str}: {value:.4f}")
            else:
                result_lines.append(f"{date_str}: N/A")
        
        # Add indicator description
        descriptions = {
            'close_50_sma': '50-day Simple Moving Average: Medium-term trend indicator',
            'close_200_sma': '200-day Simple Moving Average: Long-term trend benchmark',
            'close_10_ema': '10-day Exponential Moving Average: Short-term sensitive average',
            'macd': 'MACD: Momentum and trend changes',
            'macds': 'MACD Signal: Smoothed MACD line for trading signals',
            'macdh': 'MACD Histogram: Difference between MACD and signal line',
            'rsi': 'RSI: Relative Strength Index (0-100, >70 overbought, <30 oversold)',
            'boll': 'Bollinger Middle Band: 20-day SMA baseline',
            'boll_ub': 'Bollinger Upper Band: Typically 2 standard deviations above',
            'boll_lb': 'Bollinger Lower Band: Typically 2 standard deviations below',
            'atr': 'ATR: Average True Range - volatility measure',
            'vwma': 'VWMA: Volume Weighted Moving Average',
            'mfi': 'MFI: Money Flow Index - volume-weighted RSI',
        }
        
        description = descriptions.get(indicator_lower, f'{indicator} technical indicator')
        
        result_str = f"## {indicator} values from {recent_data.index[0].strftime('%Y-%m-%d')} to {end_date}:\n\n"
        result_str += '\n'.join(result_lines)
        result_str += f"\n\n{description}"
        
        return result_str
        
    except NoMarketDataError:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        canonical = normalize_symbol(symbol)
        raise NoMarketDataError(symbol, canonical, f"AKShare indicator calculation error for {symbol}: {str(e)}")


def get_akshare_global_news(
    queries: list = None,
    lookback_days: int = 7,
    limit: int = 10
):
    """Get global/macro news from AKShare."""
    try:
        if queries is None:
            queries = ["宏观经济", "央行政策", "股市动态"]
        
        all_news = []
        
        for query in queries:
            try:
                # Use stock news API with the query as symbol
                df = ak.stock_news_em(symbol=query)
                
                if not df.empty:
                    df = df.head(limit // len(queries))
                    
                    for _, row in df.iterrows():
                        title = row.get('标题', row.get('title', 'N/A'))
                        content = row.get('内容', row.get('content', ''))
                        publish_time = row.get('发布时间', row.get('publish_time', ''))
                        
                        news_item = {
                            'title': title,
                            'content': content[:300] if content else '',
                            'time': publish_time,
                            'query': query
                        }
                        all_news.append(news_item)
            except Exception as e:
                print(f"Warning: Failed to fetch news for query '{query}': {e}")
                continue
        
        if not all_news:
            return "No global news found"
        
        # Format output
        news_lines = []
        for item in all_news:
            news_item = f"[{item['time']}] [{item['query']}] {item['title']}\n"
            if item['content']:
                news_item += f"{item['content']}...\n"
            news_item += "-" * 80 + "\n"
            news_lines.append(news_item)
        
        header = f"# Global/Macro News\n"
        header += f"# Queries: {', '.join(queries)}\n"
        header += f"# Total articles: {len(news_lines)}\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + "\n".join(news_lines)
        
    except NoMarketDataError:
        raise
    except Exception as e:
        raise NoMarketDataError(
            symbol="global",
            canonical="global",
            message=f"AKShare global news error: {str(e)}"
        )


def _convert_symbol_for_akshare(symbol: str) -> tuple:
    """
    Convert standard ticker symbol to AKShare format.
    
    Returns:
        tuple: (akshare_symbol, market_type)
               market_type: 'A' for A股, 'HK' for 港股, 'US' for 美股
    """
    symbol_upper = symbol.upper().strip()
    
    # HK stocks: 0700.HK -> 00700
    if '.HK' in symbol_upper:
        hk_code = symbol_upper.replace('.HK', '').zfill(5)
        return hk_code, "HK"
    
    # A股: 600519.SS or 600519.SH -> 600519
    if '.SS' in symbol_upper or '.SH' in symbol_upper:
        a_code = symbol_upper.replace('.SS', '').replace('.SH', '')
        return a_code, "A"
    
    # A股: 000001.SZ -> 000001
    if '.SZ' in symbol_upper:
        a_code = symbol_upper.replace('.SZ', '')
        return a_code, "A"
    
    # Pure numeric codes (assume A股 based on prefix)
    if symbol.isdigit():
        if len(symbol) == 6:
            if symbol.startswith(('6', '9')):
                return symbol, "A"  # Shanghai
            elif symbol.startswith(('0', '3')):
                return symbol, "A"  # Shenzhen
    
    # US stocks (limited support)
    # For now, we'll mark as unsupported
    return symbol, "US"


# Export functions for interface.py
get_stock = [get_akshare_stock, "OHLCV stock price data"]
get_indicators = [get_akshare_indicators, "Technical analysis indicators (via pandas-ta)"]
get_fundamentals = [get_akshare_fundamentals, "Company fundamentals"]
get_balance_sheet = [get_akshare_balance_sheet, "Balance sheet data"]
get_cashflow = [get_akshare_cashflow, "Cash flow data"]
get_income_statement = [get_akshare_income_statement, "Income statement data"]
get_insider_transactions = [get_akshare_insider_transactions, "Insider transactions"]
get_news = [get_akshare_news, "Stock-specific news"]
get_global_news = [get_akshare_global_news, "Global/macro news"]
