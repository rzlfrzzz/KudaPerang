"""
indicators.py — Kalkulasi semua indikator teknikal
EMA, RSI, MACD, ADX, Fibonacci Retracement levels, Candle Strength, Choppiness Index
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

    @staticmethod
    def add_macd(df: pd.DataFrame) -> pd.DataFrame:
        """
        Hitung MACD: macd_line, signal_line, histogram.

        Kolom yang ditambahkan:
          macd_line    — EMA(fast) - EMA(slow)
          macd_signal  — EMA(macd_line, signal_period)
          macd_hist    — macd_line - macd_signal
          macd_cross   — "bullish" | "bearish" | None  (crossover pada candle terakhir)
        """
        df = df.copy()
        fast   = getattr(Config, "MACD_FAST", 12)
        slow   = getattr(Config, "MACD_SLOW", 26)
        signal = getattr(Config, "MACD_SIGNAL", 9)

        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()

        df["macd_line"]   = ema_fast - ema_slow
        df["macd_signal"] = df["macd_line"].ewm(span=signal, adjust=False).mean()
        df["macd_hist"]   = df["macd_line"] - df["macd_signal"]

        # Deteksi crossover: bandingkan candle terakhir vs sebelumnya
        prev_hist = df["macd_hist"].iloc[-2] if len(df) > 1 else 0
        curr_hist = df["macd_hist"].iloc[-1]

        if prev_hist < 0 and curr_hist >= 0:
            df["macd_cross"] = "bullish"
        elif prev_hist > 0 and curr_hist <= 0:
            df["macd_cross"] = "bearish"
        else:
            df["macd_cross"] = None

        return df

    @staticmethod
    def add_adx(df: pd.DataFrame) -> pd.DataFrame:
        """
        Hitung Average Directional Index (ADX) beserta +DI dan -DI.

        Kolom yang ditambahkan: adx, plus_di, minus_di
        """
        df = df.copy()
        period = getattr(Config, "ADX_PERIOD", 14)

        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low  - close.shift(1)).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movement
        up_move   = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        plus_dm_s  = pd.Series(plus_dm,  index=df.index)
        minus_dm_s = pd.Series(minus_dm, index=df.index)

        # Wilder smoothing
        atr        = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        plus_di_s  = 100 * plus_dm_s.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan)
        minus_di_s = 100 * minus_dm_s.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan)

        dx    = 100 * (plus_di_s - minus_di_s).abs() / (plus_di_s + minus_di_s).replace(0, np.nan)
        adx_s = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        df["adx"]      = adx_s.fillna(0)
        df["plus_di"]  = plus_di_s.fillna(0)
        df["minus_di"] = minus_di_s.fillna(0)
        return df

    @staticmethod
    def add_candle_strength(df: pd.DataFrame) -> pd.DataFrame:
        """
        Analisis kekuatan candle terakhir.

        Kolom yang ditambahkan:
          candle_body_pct — rasio body vs total range (0–1)
          candle_dir      — "bull" | "bear"
          candle_strong   — True jika body >= CANDLE_BODY_MIN dari total range
        """
        df = df.copy()
        body_min = getattr(Config, "CANDLE_BODY_MIN", 0.5)

        body = (df["close"] - df["open"]).abs()
        rng  = (df["high"] - df["low"]).replace(0, np.nan)

        df["candle_body_pct"] = (body / rng).fillna(0)
        df["candle_dir"]      = np.where(df["close"] >= df["open"], "bull", "bear")
        df["candle_strong"]   = df["candle_body_pct"] >= body_min
        return df

    @staticmethod
    def add_choppiness(df: pd.DataFrame) -> pd.DataFrame:
        """
        Hitung Choppiness Index.
        Nilai mendekati 100 = choppy (ranging), mendekati 0 = trending kuat.
        Pasar dianggap choppy jika CI >= CHOP_THRESHOLD (default 61.8).

        Kolom yang ditambahkan: choppiness, is_choppy
        """
        df = df.copy()
        period    = getattr(Config, "CHOP_PERIOD", 14)
        threshold = getattr(Config, "CHOP_THRESHOLD", 61.8)

        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        # True Range per candle
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low  - close.shift(1)).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr_sum   = tr.rolling(window=period).sum()
        high_roll = high.rolling(window=period).max()
        low_roll  = low.rolling(window=period).min()
        rng_roll  = (high_roll - low_roll).replace(0, np.nan)

        ci = 100 * np.log10(atr_sum / rng_roll) / np.log10(period)
        df["choppiness"] = ci.fillna(50)
        df["is_choppy"]  = df["choppiness"] >= threshold
        return df
