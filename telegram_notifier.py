"""
telegram_notifier.py — Kirim sinyal trading ke Telegram
Format pesan rapi dan mudah dibaca di HP
"""

from __future__ import annotations

import logging
import requests
from datetime import datetime
from config import Config

log = logging.getLogger(__name__)

# Emoji helper
EMOJI = {
    "LONG":     "🟢",
    "SHORT":    "🔴",
    "bullish":  "📈",
    "bearish":  "📉",
    "golden_zone":  "⭐",
    "deep_zone":    "🔵",
    "shallow_zone": "🟡",
}

FIB_ZONE_LABEL = {
    "golden_zone":  "Golden Zone (38.2%–61.8%)",
    "deep_zone":    "Deep Zone (61.8%–78.6%)",
    "shallow_zone": "Shallow Zone (23.6%–38.2%)",
}


class TelegramNotifier:
    def __init__(self):
        self.token   = Config.TELEGRAM_BOT_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, signal: dict, ai_commentary: str | None = None) -> bool:
        """Format dan kirim sinyal ke Telegram. Return True jika berhasil."""
        message = self._format_message(signal, ai_commentary=ai_commentary)
        return self._send(message)

    def send_text(self, text: str) -> bool:
        """Kirim pesan teks biasa (untuk notifikasi bot start/error)."""
        return self._send(text)

    # ── Formatter ─────────────────────────────────────────────────────────────
    @staticmethod
    def _format_message(s: dict, ai_commentary: str | None = None) -> str:
        dir_emoji  = EMOJI.get(s["direction"], "")
        div_emoji  = EMOJI.get(s["divergence"], "")
        zone_emoji = EMOJI.get(s["fib_zone"], "")
        zone_label = FIB_ZONE_LABEL.get(s["fib_zone"], s["fib_zone"])
        now        = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")

        # Tentukan leverage saran berdasarkan RR (semakin tinggi RR semakin konservatif)
        suggested_lev = 5 if s["rr_ratio"] < 2 else (3 if s["rr_ratio"] < 3 else 2)

        rr_stars = "⭐" * min(int(s["rr_ratio"]), 5)

        msg = f"""
{dir_emoji} *{s["direction"]} SIGNAL — {s["symbol"]}*
`{now}`

━━━━━━━━━━━━━━━━━━━━━
📊 *ANALISIS KONFIRMASI*
━━━━━━━━━━━━━━━━━━━━━
• HTF (1H) Bias  : {s["htf_bias"].upper()} {div_emoji}
• MTF (15M) Bias : {s["mtf_bias"].upper()} {div_emoji}
• RSI Divergence : {s["divergence"].upper()} (RSI: {s["rsi"]})
• Fib Zone       : {zone_emoji} {zone_label}

━━━━━━━━━━━━━━━━━━━━━
🎯 *LEVEL TRADING*
━━━━━━━━━━━━━━━━━━━━━
• Entry     : `{s["entry"]}`
• Stop Loss : `{s["stop_loss"]}`  ⛔
• TP1 (50%) : `{s["tp1"]}`  🏁
• TP2 (30%) : `{s["tp2"]}`  🏁🏁
• TP3 (20%) : `{s["tp3"]}`  🏁🏁🏁

━━━━━━━━━━━━━━━━━━━━━
📐 *RISK MANAGEMENT*
━━━━━━━━━━━━━━━━━━━━━
• R:R Ratio     : 1:{s["rr_ratio"]} {rr_stars}
• Saran Leverage: {suggested_lev}x (maks)
• Risk per trade: 1–2% kapital

━━━━━━━━━━━━━━━━━━━━━
🕯️ *SWING REFERENCE*
━━━━━━━━━━━━━━━━━━━━━
• Swing High : `{s["swing_high"]}`
• Swing Low  : `{s["swing_low"]}`

        ⚠️ _Ini sinyal edukasi, bukan rekomendasi finansial._
_Selalu gunakan risk management yang ketat._
        """.strip()

        if ai_commentary:
            msg += (
                f"\n\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 *AI COMMENTARY (DeepSeek)*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"_{ai_commentary}_"
            )

        return msg

    # ── HTTP sender ───────────────────────────────────────────────────────────
    def _send(self, text: str) -> bool:
        payload = {
            "chat_id":    self.chat_id,
            "text":       text,
            "parse_mode": "Markdown",
        }
        try:
            resp = requests.post(self.base_url, json=payload, timeout=10)
            resp.raise_for_status()
            log.info("Telegram message sent successfully")
            return True
        except requests.exceptions.RequestException as e:
            log.error(f"Telegram send failed: {e}")
            return False
