"""
indicators.py — Kalkulasi semua indikator teknikal
EMA, RSI, Fibonacci Retracement levels
"""

import pandas as pd
import numpy as np
from config import Config


class Indicators:

    @staticmethod
    def add_ema(df: pd.DataFrame) -> pd.DataFrame:
        """Tambah EMA fast & slow ke DataFrame"""
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=Config.EMA_FAST, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=Config.EMA_SLOW, adjust=False).mean()
        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame) -> pd.DataFrame:
        """Hitung RSI dengan metode Wilder smoothing (sama dengan TradingView)"""
        df = df.copy()
        period = Config.RSI_PERIOD

        delta = df["close"].diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)

        # Wilder smoothing (EWMA dengan alpha = 1/period)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs  = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        df["rsi"] = df["rsi"].fillna(50)
        return df

    @staticmethod
    def add_fibonacci(df: pd.DataFrame) -> pd.DataFrame:
        """
        Hitung level Fibonacci Retracement berdasarkan swing high/low
        dalam lookback terakhir (Config.FIB_LOOKBACK candle).

        Level yang dihitung: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%
        """
        df = df.copy()
        lookback = min(Config.FIB_LOOKBACK, len(df))
        recent   = df.iloc[-lookback:]

        swing_high = recent["high"].max()
        swing_low  = recent["low"].min()
        diff       = swing_high - swing_low

        fib_levels = {
            "fib_0":    swing_high,
            "fib_236":  swing_high - 0.236 * diff,
            "fib_382":  swing_high - 0.382 * diff,
            "fib_50":   swing_high - 0.500 * diff,
            "fib_618":  swing_high - 0.618 * diff,
            "fib_786":  swing_high - 0.786 * diff,
            "fib_100":  swing_low,
            "swing_high": swing_high,
            "swing_low":  swing_low,
        }

        for key, val in fib_levels.items():
            df[key] = val

        return df

    @staticmethod
    def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 5) -> str | None:
        """
        Deteksi RSI divergence pada candle terakhir vs beberapa candle sebelumnya.

        Return:
            "bullish" — harga lower low tapi RSI higher low (potensi naik)
            "bearish" — harga higher high tapi RSI lower high (potensi turun)
            None      — tidak ada divergence
        """
        if len(df) < lookback + 3:
            return None

        # Bandingkan 2 titik: ujung kiri (beberapa candle lalu) vs ujung kanan (terbaru)
        recent = df.iloc[-(lookback):]

        # Cari swing low untuk bullish divergence
        price_low_left  = recent["low"].iloc[0]
        price_low_right = recent["low"].iloc[-1]
        rsi_low_left    = recent["rsi"].iloc[0]
        rsi_low_right   = recent["rsi"].iloc[-1]

        # Cari swing high untuk bearish divergence
        price_high_left  = recent["high"].iloc[0]
        price_high_right = recent["high"].iloc[-1]
        rsi_high_left    = recent["rsi"].iloc[0]
        rsi_high_right   = recent["rsi"].iloc[-1]

        rsi_current = df["rsi"].iloc[-1]

        # Bullish: harga turun (lower low) tapi RSI naik (higher low) + RSI oversold area
        if (price_low_right < price_low_left
                and rsi_low_right > rsi_low_left
                and rsi_current < Config.RSI_OVERSOLD + 15):
            return "bullish"

        # Bearish: harga naik (higher high) tapi RSI turun (lower high) + RSI overbought area
        if (price_high_right > price_high_left
                and rsi_high_right < rsi_high_left
                and rsi_current > Config.RSI_OVERBOUGHT - 15):
            return "bearish"

        return None

    @staticmethod
    def price_in_fib_zone(df: pd.DataFrame, direction: str = "LONG") -> str | None:
        """
        Cek apakah harga close terakhir berada di zona Fibonacci kunci.

        Parameter:
            direction: "LONG" atau "SHORT" — menentukan zona mana yang relevan

        Untuk LONG (pullback ke support):
            "golden_zone" — 38.2%–61.8% (zona paling kuat)
            "deep_zone"   — 61.8%–78.6% (retrace dalam, masih valid)

        Untuk SHORT (pullback ke resistance):
            "golden_zone" — 38.2%–61.8% dari atas (zona paling kuat)
            "shallow_zone"— 23.6%–38.2% (retrace dangkal ke resistance)

        Return None jika harga di luar zona relevan.
        """
        last_close = df["close"].iloc[-1]
        fib_382    = df["fib_382"].iloc[-1]
        fib_618    = df["fib_618"].iloc[-1]
        fib_236    = df["fib_236"].iloc[-1]
        fib_786    = df["fib_786"].iloc[-1]

        if direction == "LONG":
            # Untuk LONG: harga harus pullback ke bawah (antara fib_618 dan fib_382)
            if fib_618 <= last_close <= fib_382:
                return "golden_zone"   # 38.2%–61.8% — zona paling kuat

            if fib_786 <= last_close < fib_618:
                return "deep_zone"     # 61.8%–78.6% — retrace dalam, masih valid

        else:  # SHORT
            # Untuk SHORT: harga harus pullback ke atas (antara fib_382 dan fib_236)
            if fib_618 <= last_close <= fib_382:
                return "golden_zone"   # 38.2%–61.8% — zona resistance kuat

            if fib_382 < last_close <= fib_236:
                return "shallow_zone"  # 23.6%–38.2% — retrace dangkal ke resistance

        return None
