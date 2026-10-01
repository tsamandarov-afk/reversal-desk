# Reversal Desk

Live demo dashboard: six agents (Spotter, Prior, Edge, Kelly · Taker, Closer) and one eye watching seven coins
(BTC ETH SOL XRP DOGE BNB ZEC) on Polymarket 5m/15m Up/Down markets.

Strategy: one-candle reversal — RSI(4) + Bollinger %B(22, 1.4) + ATR(41).
All trades are **paper** trades at real order-book prices. No real money, not financial advice.

- `index.html` — the site (static, canvas, live Binance candles)
- `feed.json` — paper-trading results, rebuilt every 5 minutes by `build_feed.py`
