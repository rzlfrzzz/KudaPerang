"""
telegram_notifier.py — Kirim sinyal trading ke Telegram
Format pesan rapi dan mudah dibaca di HP
"""

from __future__ import annotations

import logging
import requests
from datetime import datetime, timezone
from config import Config

log = logging.getLogger(__name__)

# Karakter yang wajib di-escape di MarkdownV2
_MDV2_CHARS = r"\_*[]()~`>#+-=|{}.!"

# Emoji helper
EMOJI = {
    "LONG":  "🟢",
    "SHORT": "🔴",
    "bullish": "📈",
    "bearish": "📉",
}

FIB_ZONE_LABEL = {
    "golden_zone":  "Golden Zone (38.2%–61.8%)",
    "deep_zone":    "Deep Zone (61.8%–78.6%)",
    "shallow_zone": "Shallow Zone (23.6%–38.2%)",
    "n/a":          "—",
}


def _esc(text: str) -> str:
    """Escape semua karakter spesial MarkdownV2 Telegram."""
    for ch in _MDV2_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text


class TelegramNotifier:
    def __init__(self):
        self.token    = Config.TELEGRAM_BOT_TOKEN
        self.chat_id  = Config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, signal: dict, ai_commentary: str | None = None) -> bool:
        """Format dan kirim sinyal ke Telegram. Return True jika berhasil."""
        message = self._format_message(signal, ai_commentary=ai_commentary)
        return self._send(message, parse_mode="MarkdownV2")

    def send_text(self, text: str) -> bool:
        """Kirim pesan teks biasa tanpa Markdown (untuk notifikasi startup/error)."""
        return self._send(text, parse_mode=None)

    # ── Formatter ─────────────────────────────────────────────────────────────
    @staticmethod
    def _format_message(s: dict, ai_commentary: str | None = None) -> str:
        dir_emoji  = EMOJI.get(s["direction"], "")
        bias_emoji = EMOJI.get(s["htf_bias"], "")
        zone_label = _esc(FIB_ZONE_LABEL.get(s.get("fib_zone", "n/a"), s.get("fib_zone", "—")))
        now        = _esc(datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"))

        direction  = _esc(s["direction"])
        symbol     = _esc(s["symbol"])
        htf_bias   = _esc(s["htf_bias"].upper())
        mtf_bias   = _esc(s["mtf_bias"].upper())
        rsi        = _esc(str(s["rsi"]))
        adx        = _esc(str(s.get("adx", "—")))
        chop       = _esc(str(s.get("choppiness", "—")))
        entry      = _esc(str(s["entry"]))
        stop_loss  = _esc(str(s["stop_loss"]))
        tp1        = _esc(str(s["tp1"]))
        tp2        = _esc(str(s["tp2"]))
        tp3        = _esc(str(s["tp3"]))
        rr_ratio   = _esc(str(s["rr_ratio"]))
        swing_high = _esc(str(s["swing_high"]))
        swing_low  = _esc(str(s["swing_low"]))

        suggested_lev = 5 if s["rr_ratio"] < 2 else (3 if s["rr_ratio"] < 3 else 2)
        rr_stars      = "⭐" * min(int(s["rr_ratio"]), 5)

        msg = (
            f"{dir_emoji} *{direction} SIGNAL — {symbol}*\n"
            f"`{now}`\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *ANALISIS KONFIRMASI*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• HTF \\(1H\\) Bias  : {htf_bias} {bias_emoji}\n"
            f"• MTF \\(15M\\) Bias : {mtf_bias} {bias_emoji}\n"
            f"• MACD Crossover : LTF ✅\n"
            f"• ADX            : {adx} 💪\n"
            f"• RSI            : {rsi}\n"
            f"• Choppiness CI  : {chop}\n"
            f"• Fib Reference  : {zone_label}\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *LEVEL TRADING*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Entry     : `{entry}`\n"
            f"• Stop Loss : `{stop_loss}`  ⛔\n"
            f"• TP1 \\(50%\\) : `{tp1}`  🏁\n"
            f"• TP2 \\(30%\\) : `{tp2}`  🏁🏁\n"
            f"• TP3 \\(20%\\) : `{tp3}`  🏁🏁🏁\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 *RISK MANAGEMENT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• R:R Ratio     : 1:{rr_ratio} {rr_stars}\n"
            f"• Saran Leverage: {suggested_lev}x \\(maks\\)\n"
            f"• Risk per trade: 1–2% kapital\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕯️ *SWING REFERENCE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Swing High : `{swing_high}`\n"
            f"• Swing Low  : `{swing_low}`\n"
            f"\n"
            f"⚠️ _Ini sinyal edukasi, bukan rekomendasi finansial\\._\n"
            f"_Selalu gunakan risk management yang ketat\\._"
        )

        if ai_commentary:
            safe = _esc(ai_commentary)
            msg += (
                f"\n\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 *AI COMMENTARY \\(DeepSeek\\)*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"_{safe}_"
            )

        return msg

    # ── HTTP sender ───────────────────────────────────────────────────────────
    def _send(self, text: str, parse_mode: str | None = "MarkdownV2") -> bool:
        payload: dict = {
            "chat_id": self.chat_id,
            "text":    text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = requests.post(self.base_url, json=payload, timeout=10)
            resp.raise_for_status()
            log.info("Telegram message sent successfully")
            return True
        except requests.exceptions.RequestException as e:
            log.error(f"Telegram send failed: {e}")
            return False

