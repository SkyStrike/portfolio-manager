import price_service
import yfinance as yf

if __name__ == "__main__":
    ticker = "QQCL.TO"
    price_service.get_yfinance_symbol(ticker, "")

    # intraday pre and post
    x = yf.download(ticker, period="1d", interval="1m")
    print(x)
    # x = yf.download(ticker, period="5d", interval="1h")
    # print(x)

    # ticker = yf.Ticker(ticker)
    # x = ticker.history(period="1d", interval="1d")
    # print(x)