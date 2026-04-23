"""
data_fetcher.py — Ambil data OHLCV dari Binance Futures REST API
Tidak butuh API key (public endpoint)
"""

import logging
import requests
import pandas as pd
from config import Config

log = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> pd.DataFrame | None:
        """
        Ambil candlestick data dari Binance Futures.
        Return DataFrame dengan kolom: open, high, low, close, volume, close_time
        """
        url = f"{Config.BINANCE_BASE_URL}/fapi/v1/klines"
        params = {
            "symbol":   symbol,
            "interval": interval,
            "limit":    limit,
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            log.error(f"[{symbol}/{interval}] Request error: {e}")
            return None

        if not data or len(data) < 20:
            log.warning(f"[{symbol}/{interval}] Data terlalu sedikit: {len(data)} candle")
            return None

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])

        # Konversi tipe data
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["open_time"]  = pd.to_datetime(df["open_time"],  unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        df.set_index("open_time", inplace=True)

        # Buang candle terakhir (belum close)
        df = df.iloc[:-1]

        log.debug(f"[{symbol}/{interval}] {len(df)} candle fetched, last: {df.index[-1]}")
        return df
