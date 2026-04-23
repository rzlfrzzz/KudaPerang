# KudaPerang — MTF Signal Bot

Bot sinyal crypto pribadi yang jalan otomatis. Strategi dasarnya Multi-Timeframe + RSI Divergence + Fibonacci, sinyal dikirim langsung ke Telegram.

Tidak eksekusi order, murni signal only.

---

## File

```
├── bot.py               — entry point
├── config.py            — semua config ada di sini
├── data_fetcher.py      — ambil OHLCV dari Binance Futures
├── indicators.py        — EMA, RSI, Fibonacci
├── signal_engine.py     — logika sinyal
├── deepseek_analyzer.py — AI commentary via DeepSeek
├── telegram_notifier.py — kirim ke Telegram
└── requirements.txt
```

---

## Setup

```bash
pip install -r requirements.txt
```

Isi `config.py`:

```python
TELEGRAM_BOT_TOKEN = "token dari @BotFather"
TELEGRAM_CHAT_ID   = "chat_id atau @username_channel"
DEEPSEEK_API_KEY   = "sk-..."   # dari platform.deepseek.com, bisa dikosongkan
```

Jalankan:

```bash
python bot.py
```

---

## Cara Dapat Chat ID Telegram

**Kalau pakai personal chat:**
1. Kirim pesan ke bot kamu
2. Buka `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Cari `"id"` di dalam `"chat"`

**Kalau pakai channel:**
- Channel publik → `@username_channel`
- Channel privat → numeric ID, biasanya diawali `-100`
- Bot harus dijadikan admin dengan permission *Post Messages*

---

## Cara Kerja

Setiap 5 menit bot scan semua pair, satu per satu:

1. Cek bias HTF (1H) lewat EMA 21/50
2. Konfirmasi di MTF (15M), harus searah
3. Cek posisi harga di Fibonacci zone (LTF 5M)
4. Cek RSI divergence (LTF 5M)
5. Kalau semua konfirmasi oke → minta komentar ke DeepSeek → kirim ke Telegram

Sinyal LONG butuh 4 konfirmasi: HTF bullish, MTF bullish, harga di fib support zone, RSI bullish divergence.
Sinyal SHORT kebalikannya.

---

## Contoh Sinyal

```
🟢 LONG SIGNAL — BTCUSDT
12 Jan 2025 08:35 UTC

━━━━━━━━━━━━━━━━━━━━━
📊 ANALISIS KONFIRMASI
━━━━━━━━━━━━━━━━━━━━━
• HTF (1H) Bias  : BULLISH 📈
• MTF (15M) Bias : BULLISH 📈
• RSI Divergence : BULLISH (RSI: 38.2)
• Fib Zone       : ⭐ Golden Zone (38.2%–61.8%)

━━━━━━━━━━━━━━━━━━━━━
🎯 LEVEL TRADING
━━━━━━━━━━━━━━━━━━━━━
• Entry     : 42850.0000
• Stop Loss : 42100.0000  ⛔
• TP1 (50%) : 44200.0000  🏁
• TP2 (30%) : 45800.0000  🏁🏁
• TP3 (20%) : 47900.0000  🏁🏁🏁

━━━━━━━━━━━━━━━━━━━━━
📐 RISK MANAGEMENT
━━━━━━━━━━━━━━━━━━━━━
• R:R Ratio     : 1:3.8 ⭐⭐⭐
• Saran Leverage: 3x (maks)
• Risk per trade: 1–2% kapital

━━━━━━━━━━━━━━━━━━━━━
🤖 AI COMMENTARY (DeepSeek)
━━━━━━━━━━━━━━━━━━━━━
Setup ini cukup solid dengan konfluensi 3 timeframe yang searah...
```

---

## Catatan

- Sinyal masuk bukan berarti langsung entry, tetap konfirmasi manual di chart
- SL wajib dipasang, jangan dihapus dengan alasan apapun
- Leverage disarankan 2–5x, jangan lebih
- Risiko per trade maksimal 1–2% dari kapital

---

> Bukan financial advice. Dibuat untuk keperluan pribadi.
