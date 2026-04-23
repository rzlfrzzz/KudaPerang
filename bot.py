"""
MTF + RSI Divergence + S/R Fibonacci Signal Bot
Binance Futures → Telegram (Signal Only, No Execution)

Timeframes:
  HTF : 1H  (bias trend)
  MTF : 15M (konfirmasi)
  LTF : 5M  (entry signal)

Author  : generated for educational purposes
Disclaimer: bukan financial advice, gunakan dengan bijak
"""

from __future__ import annotations

import time
import logging
import sys
from datetime import datetime
from config import Config
from data_fetcher import DataFetcher
from indicators import Indicators
from signal_engine import SignalEngine
from telegram_notifier import TelegramNotifier
from deepseek_analyzer import DeepSeekAnalyzer
from symbol_manager import SymbolManager

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
log = logging.getLogger(__name__)


def main():
    log.info("=" * 60)
    log.info("  MTF Signal Bot started")
    log.info(f"  HTF/MTF/LTF : {Config.HTF}/{Config.MTF}/{Config.LTF}")
    log.info("=" * 60)

    fetcher  = DataFetcher()
    notifier = TelegramNotifier()
    analyzer = DeepSeekAnalyzer()
    symbol_mgr = SymbolManager(
        base_url=Config.BINANCE_BASE_URL,
        top_n=Config.SYMBOLS_TOP_N,
        refresh_interval_hours=Config.SYMBOLS_REFRESH_HOURS,
        blacklist=Config.SYMBOLS_BLACKLIST,
    )

    # Track last candle close timestamp per symbol agar tidak kirim sinyal duplikat
    last_signal: dict[str, str] = {}

    while True:
        try:
            cycle_start = time.time()
            now_str = datetime.utcnow().strftime("%H:%M:%S UTC")
            log.info(f"── Scan cycle {now_str} ──")

            symbols = symbol_mgr.symbols
            log.info(f"Scanning {len(symbols)} pairs | Refresh berikutnya: {symbol_mgr.time_until_next_refresh()}")

            for symbol in symbols:
                try:
                    _process_symbol(symbol, fetcher, notifier, analyzer, last_signal)
                except Exception as e:
                    log.error(f"[{symbol}] Error: {e}", exc_info=True)

                # Jeda antar pair agar tidak spike request
                time.sleep(Config.REQUEST_DELAY)

            elapsed = time.time() - cycle_start
            sleep_time = max(0, Config.SCAN_INTERVAL - elapsed)
            log.info(f"Cycle done in {elapsed:.1f}s, sleeping {sleep_time:.0f}s")
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            log.info("Bot dihentikan oleh user.")
            sys.exit(0)
        except Exception as e:
            log.error(f"[MAIN LOOP] Unexpected error: {e}", exc_info=True)
            log.info("Restart cycle dalam 60 detik...")
            time.sleep(60)



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Bot dihentikan.")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Bot crash fatal: {e}", exc_info=True)
        sys.exit(1)


def _process_symbol(
    symbol: str,
    fetcher: "DataFetcher",
    notifier: "TelegramNotifier",
    analyzer: "DeepSeekAnalyzer",
    last_signal: dict,
) -> None:
    log.info(f"[{symbol}] Fetching data...")

    # 1. Ambil data ketiga timeframe
    df_htf = fetcher.get_klines(symbol, Config.HTF, limit=100)
    df_mtf = fetcher.get_klines(symbol, Config.MTF, limit=100)
    df_ltf = fetcher.get_klines(symbol, Config.LTF, limit=100)

    if df_htf is None or df_mtf is None or df_ltf is None:
        log.warning(f"[{symbol}] Data tidak lengkap, skip")
        return

    # 2. Hitung indikator
    df_htf = Indicators.add_ema(df_htf)
    df_mtf = Indicators.add_ema(df_mtf)
    df_ltf = Indicators.add_ema(df_ltf)
    df_ltf = Indicators.add_rsi(df_ltf)
    df_ltf = Indicators.add_fibonacci(df_ltf)

    # 3. Jalankan engine sinyal
    signal = SignalEngine.evaluate(symbol, df_htf, df_mtf, df_ltf)

    if signal is None:
        log.info(f"[{symbol}] No signal")
        return

    # 4. Cek duplikat (tidak kirim sinyal yang sama dalam 1 jam)
    sig_key = f"{symbol}_{signal['direction']}_{signal['ltf_close_time']}"
    if last_signal.get(symbol) == sig_key:
        log.info(f"[{symbol}] Duplikat sinyal, skip")
        return

    last_signal[symbol] = sig_key

    # 5. Dapatkan AI commentary dari DeepSeek (opsional, graceful fallback)
    ai_commentary = analyzer.analyze(signal)

    # 6. Kirim ke Telegram
    log.info(f"[{symbol}] *** SIGNAL {signal['direction']} *** sending to Telegram")
    success = notifier.send_signal(signal, ai_commentary=ai_commentary)
    if not success:
        log.warning(f"[{symbol}] Gagal mengirim sinyal ke Telegram")
