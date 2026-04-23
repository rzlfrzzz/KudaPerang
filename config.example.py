"""
config.py — Semua konfigurasi bot di satu tempat
Salin file ini menjadi config.py lalu isi nilai yang diperlukan
"""


class Config:
    # ── Telegram ─────────────────────────────────────────────────────────────
    # Dapatkan BOT_TOKEN dari @BotFather di Telegram
    # Chat ID bisa berupa numeric ID atau @username_channel
    TELEGRAM_BOT_TOKEN = "ISI_TOKEN_BOT_KAMU_DI_SINI"
    TELEGRAM_CHAT_ID   = "ISI_CHAT_ID_ATAU_@USERNAME_CHANNEL"

    # ── Binance ───────────────────────────────────────────────────────────────
    # Bot ini hanya membaca data publik, TIDAK butuh API key
    BINANCE_BASE_URL = "https://fapi.binance.com"

    # ── Dynamic Symbols (auto-refresh) ────────────────────────────────────────
    # Pair tidak lagi ditulis manual — diambil otomatis dari Binance berdasarkan
    # volume 24 jam tertinggi. Daftar ini hanya dipakai sebagai FALLBACK
    # jika API Binance tidak bisa diakses saat bot pertama kali start.
    SYMBOLS_FALLBACK = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "POLUSDT",
    ]

    # Jumlah pair teratas yang dipantau
    SYMBOLS_TOP_N = 10

    # Interval refresh symbols dalam JAM — pilih 6 atau 12
    SYMBOLS_REFRESH_HOURS = 6

    # Pair yang SELALU dikecualikan dari daftar
    SYMBOLS_BLACKLIST = [
        "BTCDOMUSDT",
        "DEFIUSDT",
    ]

    # ── Timeframes ────────────────────────────────────────────────────────────
    HTF = "1h"   # High Timeframe  — bias trend
    MTF = "15m"  # Mid  Timeframe  — konfirmasi
    LTF = "5m"   # Low  Timeframe  — entry signal

    # ── Indikator ─────────────────────────────────────────────────────────────
    EMA_FAST       = 21
    EMA_SLOW       = 50
    RSI_PERIOD     = 14
    RSI_OVERSOLD   = 35
    RSI_OVERBOUGHT = 70
    FIB_LOOKBACK   = 100

    # ── Timing ───────────────────────────────────────────────────────────────
    SCAN_INTERVAL  = 300
    REQUEST_DELAY  = 0.3

    # ── Risk Management ───────────────────────────────────────────────────────
    RISK_REWARD_MIN = 2.0

    # ── DeepSeek AI Analyzer ──────────────────────────────────────────────────
    # Dapatkan API key dari https://platform.deepseek.com
    # Set DEEPSEEK_ENABLED = False jika tidak ingin pakai fitur AI commentary
    DEEPSEEK_API_KEY  = "ISI_DEEPSEEK_API_KEY_KAMU_DI_SINI"
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    DEEPSEEK_MODEL    = "deepseek-chat"
    DEEPSEEK_ENABLED  = True
    DEEPSEEK_TIMEOUT  = 30
