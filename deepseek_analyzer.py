"""
deepseek_analyzer.py — AI commentary untuk sinyal trading menggunakan DeepSeek API
DeepSeek API kompatibel dengan OpenAI SDK (gunakan base_url custom)

Cara kerja:
  - Terima dict sinyal dari SignalEngine
  - Kirim ke DeepSeek untuk mendapatkan analisis singkat dalam Bahasa Indonesia
  - Return string komentar, atau None jika gagal / fitur dinonaktifkan
"""

from __future__ import annotations

import logging
from openai import OpenAI, APIError, APITimeoutError
from config import Config

log = logging.getLogger(__name__)


class DeepSeekAnalyzer:
    def __init__(self):
        self._client = None
        if Config.DEEPSEEK_ENABLED:
            self._client = OpenAI(
                api_key=Config.DEEPSEEK_API_KEY,
                base_url=Config.DEEPSEEK_BASE_URL,
                timeout=Config.DEEPSEEK_TIMEOUT,
            )
            log.info("DeepSeekAnalyzer initialized")
        else:
            log.info("DeepSeekAnalyzer disabled (DEEPSEEK_ENABLED=False)")

    def analyze(self, signal: dict) -> str | None:
        """
        Kirim data sinyal ke DeepSeek dan minta komentar analisis singkat.

        Return:
            str  — komentar AI (1–3 kalimat, Bahasa Indonesia)
            None — jika fitur disabled atau request gagal
        """
        if not Config.DEEPSEEK_ENABLED or self._client is None:
            return None

        prompt = self._build_prompt(signal)

        try:
            response = self._client.chat.completions.create(
                model=Config.DEEPSEEK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kamu adalah analis trading crypto profesional. "
                            "Berikan komentar singkat (maksimal 3 kalimat, Bahasa Indonesia) "
                            "tentang kualitas setup sinyal yang diberikan. "
                            "Fokus pada kekuatan konfirmasi, level kunci, dan potensi risiko. "
                            "Gunakan bahasa yang mudah dipahami trader retail."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.3,
            )
            commentary = response.choices[0].message.content.strip()
            log.info(f"[{signal['symbol']}] DeepSeek commentary received")
            return commentary

        except APITimeoutError:
            log.warning(f"[{signal['symbol']}] DeepSeek timeout, sinyal dikirim tanpa AI commentary")
            return None
        except APIError as e:
            log.warning(f"[{signal['symbol']}] DeepSeek API error: {e}, sinyal dikirim tanpa AI commentary")
            return None
        except Exception as e:
            log.warning(f"[{signal['symbol']}] DeepSeek unexpected error: {e}")
            return None

    @staticmethod
    def _build_prompt(s: dict) -> str:
        return (
            f"Analisa sinyal trading berikut:\n"
            f"- Pair      : {s['symbol']}\n"
            f"- Arah      : {s['direction']}\n"
            f"- HTF Bias  : {s['htf_bias']} | MTF Bias: {s['mtf_bias']}\n"
            f"- Divergence: RSI {s['divergence']}\n"
            f"- Fib Zone  : {s['fib_zone']}\n"
            f"- RSI saat ini: {s['rsi']}\n"
            f"- Entry     : {s['entry']}\n"
            f"- Stop Loss : {s['stop_loss']}\n"
            f"- TP1/TP2/TP3: {s['tp1']} / {s['tp2']} / {s['tp3']}\n"
            f"- R:R Ratio : 1:{s['rr_ratio']}\n"
            f"- Swing High: {s['swing_high']} | Swing Low: {s['swing_low']}"
        )
