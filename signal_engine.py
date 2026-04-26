"""
signal_engine.py — Otak bot: filter kondisi sinyal sebelum dikirim

Strategi:
  1. HTF  MACD direction → bias arah (bullish / bearish)
  2. MTF  MACD direction → konfirmasi arah selaras dengan HTF
  3. LTF  MACD crossover → trigger entry
  4. LTF  ADX > ADX_MIN  → pasar sedang trending, bukan sideways
  5. LTF  RSI netral     → tidak overbought / oversold
  6. LTF  Candle kuat    → body candle dominan
  7. LTF  Tidak choppy   → Choppiness Index di bawah threshold

  Setelah semua filter lolos → susun sinyal SL/TP via _build_signal()
"""

import logging
import pandas as pd
from config import Config
from indicators import Indicators

log = logging.getLogger(__name__)


class SignalEngine:

    @staticmethod
    def evaluate(
        symbol:  str,
        df_htf:  pd.DataFrame,
        df_mtf:  pd.DataFrame,
        df_ltf:  pd.DataFrame,
    ) -> dict | None:
        """
        Evaluasi semua kondisi.
        Return dict sinyal jika semua konfirmasi terpenuhi, None jika tidak.
        """

        # ── Langkah 1: HTF Bias via MACD direction ────────────────────────────
        htf_bias = SignalEngine._get_macd_bias(df_htf)
        log.debug(f"[{symbol}] HTF MACD bias: {htf_bias}")

        if htf_bias == "sideways":
            log.info(f"[{symbol}] HTF MACD sideways → skip")
            return None

        # ── Langkah 2: MTF Konfirmasi via MACD direction ──────────────────────
        mtf_bias = SignalEngine._get_macd_bias(df_mtf)
        log.debug(f"[{symbol}] MTF MACD bias: {mtf_bias}")

        if mtf_bias != htf_bias:
            log.info(f"[{symbol}] HTF/MTF tidak selaras ({htf_bias}/{mtf_bias}) → skip")
            return None

        # ── Langkah 3: LTF MACD Crossover (trigger) ──────────────────────────
        ltf_cross = df_ltf["macd_cross"].iloc[-1]
        log.debug(f"[{symbol}] LTF MACD cross: {ltf_cross}")

        if htf_bias == "bullish" and ltf_cross != "bullish":
            log.info(f"[{symbol}] Tidak ada MACD bullish crossover di LTF → skip")
            return None

        if htf_bias == "bearish" and ltf_cross != "bearish":
            log.info(f"[{symbol}] Tidak ada MACD bearish crossover di LTF → skip")
            return None

        # ── Langkah 4: ADX — trend strength ───────────────────────────────────
        adx_min = getattr(Config, "ADX_MIN", 25)
        adx_val = df_ltf["adx"].iloc[-1]
        log.debug(f"[{symbol}] ADX: {adx_val:.1f} (min {adx_min})")

        if adx_val < adx_min:
            log.info(f"[{symbol}] ADX {adx_val:.1f} < {adx_min} → trend lemah, skip")
            return None

        # ── Langkah 5: RSI netral (tidak OB/OS) ──────────────────────────────
        rsi_val = df_ltf["rsi"].iloc[-1]
        rsi_ob  = getattr(Config, "RSI_OVERBOUGHT", 70)
        rsi_os  = getattr(Config, "RSI_OVERSOLD", 35)
        log.debug(f"[{symbol}] RSI: {rsi_val:.1f}")

        if htf_bias == "bullish" and rsi_val >= rsi_ob:
            log.info(f"[{symbol}] RSI {rsi_val:.1f} overbought → skip LONG")
            return None

        if htf_bias == "bearish" and rsi_val <= rsi_os:
            log.info(f"[{symbol}] RSI {rsi_val:.1f} oversold → skip SHORT")
            return None

        # ── Langkah 6: Candle strength ────────────────────────────────────────
        candle_strong = df_ltf["candle_strong"].iloc[-1]
        candle_dir    = df_ltf["candle_dir"].iloc[-1]
        log.debug(f"[{symbol}] Candle dir: {candle_dir}, strong: {candle_strong}")

        if not candle_strong:
            log.info(f"[{symbol}] Candle lemah (doji/indecision) → skip")
            return None

        expected_candle = "bull" if htf_bias == "bullish" else "bear"
        if candle_dir != expected_candle:
            log.info(f"[{symbol}] Candle {candle_dir} berlawanan dengan arah {htf_bias} → skip")
            return None

        # ── Langkah 7: Anti-choppy (Choppiness Index) ─────────────────────────
        is_choppy = df_ltf["is_choppy"].iloc[-1]
        chop_val  = df_ltf["choppiness"].iloc[-1]
        log.debug(f"[{symbol}] Choppiness: {chop_val:.1f}, choppy: {is_choppy}")

        if is_choppy:
            log.info(f"[{symbol}] Market choppy (CI={chop_val:.1f}) → skip")
            return None

        # ── Semua filter lolos! Susun sinyal ─────────────────────────────────
        direction = "LONG" if htf_bias == "bullish" else "SHORT"

        # Fibonacci zone masih digunakan untuk SL/TP reference
        fib_zone = Indicators.price_in_fib_zone(df_ltf, direction=direction)

        signal = SignalEngine._build_signal(
            symbol    = symbol,
            direction = direction,
            df_ltf    = df_ltf,
            fib_zone  = fib_zone,
            adx       = adx_val,
            rsi       = rsi_val,
            htf_bias  = htf_bias,
            mtf_bias  = mtf_bias,
            chop_val  = chop_val,
        )

        if signal is None:
            return None

        log.info(
            f"[{symbol}] ✅ SIGNAL {direction} | "
            f"entry={signal['entry']:.4f} SL={signal['stop_loss']:.4f} "
            f"TP1={signal['tp1']:.4f} RR={signal['rr_ratio']:.1f} "
            f"ADX={adx_val:.1f} CI={chop_val:.1f}"
        )
        return signal

    # ── Helper: tentukan bias MACD dari direction histogram ───────────────────
    @staticmethod
    def _get_macd_bias(df: pd.DataFrame) -> str:
        """
        Bullish  : histogram MACD positif
        Bearish  : histogram MACD negatif
        Sideways : histogram nyaris nol (dalam 10% dari std histogram)
        """
        hist    = df["macd_hist"].iloc[-1]
        std     = df["macd_hist"].std()
        epsilon = std * 0.1 if std > 0 else 1e-9

        if abs(hist) < epsilon:
            return "sideways"
        return "bullish" if hist > 0 else "bearish"

    # ── Helper: susun dict sinyal lengkap ─────────────────────────────────────
    @staticmethod
    def _build_signal(
        symbol: str, direction: str, df_ltf: pd.DataFrame,
        fib_zone: str | None, adx: float, rsi: float,
        htf_bias: str, mtf_bias: str, chop_val: float,
    ) -> dict | None:
        last  = df_ltf.iloc[-1]
        close = last["close"]

        swing_high = last["swing_high"]
        swing_low  = last["swing_low"]
        fib_618    = last["fib_618"]
        fib_382    = last["fib_382"]
        fib_0      = last["fib_0"]
        fib_100    = last["fib_100"]

        if direction == "LONG":
            entry     = close
            stop_loss = swing_low  - (swing_low  * 0.005)   # 0.5% di bawah swing low
            tp1       = fib_382
            tp2       = fib_0
            tp3       = fib_0 + (fib_0 - fib_100) * 0.618
        else:  # SHORT
            entry     = close
            stop_loss = swing_high + (swing_high * 0.005)   # 0.5% di atas swing high
            tp1       = fib_618
            tp2       = fib_100
            tp3       = fib_100 - (fib_0 - fib_100) * 0.618

        risk     = abs(entry - stop_loss)
        reward   = abs(tp2 - entry)
        rr_ratio = reward / risk if risk > 0 else 0

        if rr_ratio < Config.RISK_REWARD_MIN:
            log.info(
                f"[{symbol}] RR {rr_ratio:.1f} < minimum {Config.RISK_REWARD_MIN}, skip"
            )
            return None

        return {
            "symbol":         symbol,
            "direction":      direction,
            "entry":          round(entry, 4),
            "stop_loss":      round(stop_loss, 4),
            "tp1":            round(tp1, 4),
            "tp2":            round(tp2, 4),
            "tp3":            round(tp3, 4),
            "rr_ratio":       round(rr_ratio, 2),
            "rsi":            round(rsi, 1),
            "adx":            round(adx, 1),
            "choppiness":     round(chop_val, 1),
            "fib_zone":       fib_zone or "n/a",
            "htf_bias":       htf_bias,
            "mtf_bias":       mtf_bias,
            "ltf_close_time": str(df_ltf.index[-1]),
            "swing_high":     round(swing_high, 4),
            "swing_low":      round(swing_low, 4),
        }
