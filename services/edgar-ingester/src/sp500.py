"""S&P 500 company list with CIK mappings (top companies for MVP)."""

# Subset of S&P 500 companies for MVP testing
# Full list can be fetched from SEC EDGAR or Wikipedia
SP500_COMPANIES = [
    {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193", "sector": "Technology"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "cik": "0000789019", "sector": "Technology"},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "cik": "0001018724", "sector": "Consumer Discretionary"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "cik": "0001652044", "sector": "Technology"},
    {"ticker": "META", "name": "Meta Platforms Inc.", "cik": "0001326801", "sector": "Technology"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "cik": "0001045810", "sector": "Technology"},
    {"ticker": "TSLA", "name": "Tesla Inc.", "cik": "0001318605", "sector": "Consumer Discretionary"},
    {"ticker": "BRK.B", "name": "Berkshire Hathaway Inc.", "cik": "0001067983", "sector": "Financials"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "cik": "0000019617", "sector": "Financials"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "cik": "0000200406", "sector": "Healthcare"},
    {"ticker": "V", "name": "Visa Inc.", "cik": "0001403161", "sector": "Financials"},
    {"ticker": "UNH", "name": "UnitedHealth Group Inc.", "cik": "0000731766", "sector": "Healthcare"},
    {"ticker": "HD", "name": "The Home Depot Inc.", "cik": "0000354950", "sector": "Consumer Discretionary"},
    {"ticker": "PG", "name": "Procter & Gamble Co.", "cik": "0000080424", "sector": "Consumer Staples"},
    {"ticker": "MA", "name": "Mastercard Inc.", "cik": "0001141391", "sector": "Financials"},
    {"ticker": "DIS", "name": "The Walt Disney Company", "cik": "0001744489", "sector": "Communication Services"},
    {"ticker": "ADBE", "name": "Adobe Inc.", "cik": "0000796343", "sector": "Technology"},
    {"ticker": "CRM", "name": "Salesforce Inc.", "cik": "0001108524", "sector": "Technology"},
    {"ticker": "NFLX", "name": "Netflix Inc.", "cik": "0001065280", "sector": "Communication Services"},
    {"ticker": "PFE", "name": "Pfizer Inc.", "cik": "0000078003", "sector": "Healthcare"},
    {"ticker": "KO", "name": "The Coca-Cola Company", "cik": "0000021344", "sector": "Consumer Staples"},
    {"ticker": "PEP", "name": "PepsiCo Inc.", "cik": "0000077476", "sector": "Consumer Staples"},
    {"ticker": "TMO", "name": "Thermo Fisher Scientific", "cik": "0000097745", "sector": "Healthcare"},
    {"ticker": "COST", "name": "Costco Wholesale Corp.", "cik": "0000909832", "sector": "Consumer Staples"},
    {"ticker": "AVGO", "name": "Broadcom Inc.", "cik": "0001649338", "sector": "Technology"},
    {"ticker": "WMT", "name": "Walmart Inc.", "cik": "0000104169", "sector": "Consumer Staples"},
    {"ticker": "BAC", "name": "Bank of America Corp.", "cik": "0000070858", "sector": "Financials"},
    {"ticker": "CSCO", "name": "Cisco Systems Inc.", "cik": "0000858877", "sector": "Technology"},
    {"ticker": "ACN", "name": "Accenture plc", "cik": "0001281761", "sector": "Technology"},
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "cik": "0000034088", "sector": "Energy"},
]


def get_sp500_companies() -> list[dict]:
    return SP500_COMPANIES
