"""
symbol_manager.py — Auto-refresh top liquid symbols dari Binance Futures
Berdasarkan volume 24 jam, diperbarui setiap 6 atau 12 jam secara otomatis.
"""

from __future__ import annotations

import time
import logging
import requests
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)


class SymbolManager:
    """
    Mengelola daftar SYMBOLS secara dinamis berdasarkan volume 24 jam
    dari Binance Futures public API (tidak butuh API key).
    """

    def __init__(
        self,
        base_url: str,
        top_n: int = 10,
        refresh_interval_hours: int = 6,
        blacklist: Optional[list] = None,
        quote_asset: str = "USDT",
    ):
        """
        Args:
            base_url            : BINANCE_BASE_URL dari config (https://fapi.binance.com)
            top_n               : Jumlah pair teratas yang diambil
            refresh_interval_hours: 6 atau 12 — interval refresh dalam jam
            blacklist           : Pair yang selalu dikecualikan, misal ["BTCDOMUSDT"]
            quote_asset         : Hanya ambil pair berakhiran ini (default USDT)
        """
        self.base_url = base_url
        self.top_n = top_n
        self.refresh_interval = refresh_interval_hours * 3600  # konversi ke detik
        self.blacklist = set(blacklist or [])
        self.quote_asset = quote_asset

        self._symbols: list[str] = []
        self._last_refresh: float = 0.0  # unix timestamp terakhir refresh

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def symbols(self) -> list[str]:
        """
        Kembalikan daftar symbols terkini.
        Otomatis refresh jika sudah melewati interval.
        """
        if self._needs_refresh():
            self._refresh()
        return self._symbols

    def force_refresh(self) -> list[str]:
        """Paksa refresh sekarang, terlepas dari interval."""
        self._refresh()
        return self._symbols

    def time_until_next_refresh(self) -> str:
        """Kembalikan string sisa waktu ke refresh berikutnya, untuk logging."""
        remaining = (self._last_refresh + self.refresh_interval) - time.time()
        if remaining <= 0:
            return "sekarang"
        h = int(remaining // 3600)
        m = int((remaining % 3600) // 60)
        return f"{h}j {m}m"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _needs_refresh(self) -> bool:
        """True jika belum pernah diambil atau sudah melewati interval."""
        return (
            not self._symbols
            or (time.time() - self._last_refresh) >= self.refresh_interval
        )

    def _refresh(self) -> None:
        """
        Ambil data ticker 24 jam dari Binance Futures,
        urutkan berdasarkan quoteVolume, ambil top N.
        """
        try:
            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            tickers = response.json()

            # Filter: hanya pair USDT, exclude perpetual non-standard & blacklist
            filtered = [
                t for t in tickers
                if t["symbol"].endswith(self.quote_asset)
                and t["symbol"] not in self.blacklist
                and "_" not in t["symbol"]  # hapus quarterly/delivery contracts
            ]

            # Urutkan berdasarkan quoteVolume (volume dalam USDT) descending
            sorted_tickers = sorted(
                filtered,
                key=lambda t: float(t.get("quoteVolume", 0)),
                reverse=True,
            )

            new_symbols = [t["symbol"] for t in sorted_tickers[: self.top_n]]

            if new_symbols:
                old_symbols = self._symbols.copy()
                self._symbols = new_symbols
                self._last_refresh = time.time()

                # Log perubahan pair jika ada
                self._log_changes(old_symbols, new_symbols)
                logger.info(
                    f"[SymbolManager] Symbols diperbarui: {new_symbols} "
                    f"| Refresh berikutnya dalam {self.refresh_interval // 3600} jam"
                )
            else:
                logger.warning("[SymbolManager] Tidak ada data ticker, symbols tidak diubah.")

        except requests.RequestException as e:
            logger.error(f"[SymbolManager] Gagal refresh symbols: {e}")
            # Jika gagal dan sudah ada symbols sebelumnya → tetap pakai yang lama
            if not self._symbols:
                # Fallback hardcoded jika belum pernah berhasil sama sekali
                self._symbols = self._fallback_symbols()
                logger.warning(f"[SymbolManager] Menggunakan fallback symbols: {self._symbols}")

    def _log_changes(self, old: list[str], new: list[str]) -> None:
        """Log pair yang masuk dan keluar dari daftar."""
        added = set(new) - set(old)
        removed = set(old) - set(new)
        if added:
            logger.info(f"[SymbolManager] Pair MASUK: {sorted(added)}")
        if removed:
            logger.info(f"[SymbolManager] Pair KELUAR: {sorted(removed)}")

    def _fallback_symbols(self) -> list[str]:
        """Fallback ke Config.SYMBOLS_FALLBACK jika API tidak bisa diakses sama sekali."""
        return list(Config.SYMBOLS_FALLBACK)
