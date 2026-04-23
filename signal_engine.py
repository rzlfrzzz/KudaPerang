"""
signal_engine.py — Otak bot: gabungkan 3 konfirmasi menjadi satu sinyal

Logika:
  LONG  = HTF bullish + MTF bullish + LTF di fib zone + RSI bullish divergence
  SHORT = HTF bearish + MTF bearish + LTF di fib zone + RSI bearish divergence
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

        # ── Langkah 1: HTF Bias ───────────────────────────────────────────────
        htf_bias = SignalEngine._get_trend_bias(df_htf)
        log.debug(f"[{symbol}] HTF bias: {htf_bias}")

        if htf_bias == "sideways":
            log.info(f"[{symbol}] HTF sideways → skip")
            return None

        # ── Langkah 2: MTF Konfirmasi ─────────────────────────────────────────
        mtf_bias = SignalEngine._get_trend_bias(df_mtf)
        log.debug(f"[{symbol}] MTF bias: {mtf_bias}")

        if mtf_bias != htf_bias:
            log.info(f"[{symbol}] HTF/MTF tidak selaras ({htf_bias}/{mtf_bias}) → skip")
            return None

        # ── Langkah 3: LTF Fibonacci Zone ─────────────────────────────────────
        direction_hint = "LONG" if htf_bias == "bullish" else "SHORT"
        fib_zone = Indicators.price_in_fib_zone(df_ltf, direction=direction_hint)
        log.debug(f"[{symbol}] Fib zone: {fib_zone}")

        if fib_zone is None:
            log.info(f"[{symbol}] Harga di luar fib zone → skip")
            return None

        # ── Langkah 4: RSI Divergence ─────────────────────────────────────────
        divergence = Indicators.detect_rsi_divergence(df_ltf)
        log.debug(f"[{symbol}] RSI divergence: {divergence}")

        if divergence is None:
            log.info(f"[{symbol}] Tidak ada RSI divergence → skip")
            return None

        # ── Langkah 5: Validasi arah sinyal konsisten ─────────────────────────
        if htf_bias == "bullish" and divergence != "bullish":
            log.info(f"[{symbol}] HTF bullish tapi divergence bearish → konflik → skip")
            return None

        if htf_bias == "bearish" and divergence != "bearish":
            log.info(f"[{symbol}] HTF bearish tapi divergence bullish → konflik → skip")
            return None

        # ── Semua konfirmasi terpenuhi! ───────────────────────────────────────
        direction = "LONG" if htf_bias == "bullish" else "SHORT"

        signal = SignalEngine._build_signal(
            symbol     = symbol,
            direction  = direction,
            df_ltf     = df_ltf,
            fib_zone   = fib_zone,
            divergence = divergence,
            htf_bias   = htf_bias,
            mtf_bias   = mtf_bias,
        )

        if signal is None:
            return None

        log.info(
            f"[{symbol}] ✅ SIGNAL {direction} | "
            f"entry={signal['entry']:.4f} SL={signal['stop_loss']:.4f} "
            f"TP1={signal['tp1']:.4f} RR={signal['rr_ratio']:.1f}"
        )
        return signal

    # ── Helper: tentukan bias trend dari EMA ──────────────────────────────────
    @staticmethod
    def _get_trend_bias(df: pd.DataFrame) -> str:
        """
        Bullish : EMA fast > EMA slow DAN harga close > EMA fast
        Bearish : EMA fast < EMA slow DAN harga close < EMA fast
        Sideways: EMA fast ≈ EMA slow (dalam 0.3%)
        """
        last = df.iloc[-1]
        ema_fast  = last["ema_fast"]
        ema_slow  = last["ema_slow"]
        close     = last["close"]

        diff_pct = abs(ema_fast - ema_slow) / ema_slow * 100 if ema_slow != 0 else 0

        if diff_pct < 0.3:
            return "sideways"

        if ema_fast > ema_slow and close > ema_fast:
            return "bullish"

        if ema_fast < ema_slow and close < ema_fast:
            return "bearish"

        return "sideways"

    # ── Helper: susun dict sinyal lengkap ─────────────────────────────────────
    @staticmethod
    def _build_signal(
        symbol: str, direction: str, df_ltf: pd.DataFrame,
        fib_zone: str, divergence: str, htf_bias: str, mtf_bias: str,
    ) -> dict | None:
        last  = df_ltf.iloc[-1]
        close = last["close"]
        rsi   = last["rsi"]

        swing_high = last["swing_high"]
        swing_low  = last["swing_low"]
        fib_618    = last["fib_618"]
        fib_382    = last["fib_382"]
        fib_0      = last["fib_0"]
        fib_100    = last["fib_100"]

        if direction == "LONG":
            entry     = close
            stop_loss = swing_low - (swing_low * 0.005)    # 0.5% di bawah swing low
            tp1       = fib_382
            tp2       = fib_0
            tp3       = fib_0 + (fib_0 - fib_100) * 0.618
        else:  # SHORT
            entry     = close
            stop_loss = swing_high + (swing_high * 0.005)  # 0.5% di atas swing high
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
            "fib_zone":       fib_zone,
            "divergence":     divergence,
            "htf_bias":       htf_bias,
            "mtf_bias":       mtf_bias,
            "ltf_close_time": str(df_ltf.index[-1]),
            "swing_high":     round(swing_high, 4),
            "swing_low":      round(swing_low, 4),
        }
