"""
symbol_manager.py — Auto-refresh watchlist dari Binance Futures
Pipeline filter 3 tahap:
  1. Volume 24j ≥ MIN_VOLUME_USD  — likuiditas intraday
  2. Open Interest ≥ MIN_OI_USD   — depth pasar nyata
  3. Listing age ≥ NEW_LISTING_DAYS — hindari pump/dump listing baru
Diperbarui setiap REFRESH_HOURS jam (default 1 jam).
"""

from __future__ import annotations

import time
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)

# Binance Futures public endpoints
_EP_TICKER    = "/fapi/v1/ticker/24hr"
_EP_OI        = "/fapi/v1/openInterest"
_EP_EXCH_INFO = "/fapi/v1/exchangeInfo"


class SymbolManager:
    """
    Mengelola watchlist pair secara dinamis dengan dual-filter Volume + OI
    serta pengecualian pair listing baru.
    """

    def __init__(
        self,
        base_url: str,
        top_n: int = 20,
        refresh_interval_hours: int = 1,
        blacklist: Optional[list] = None,
        quote_asset: str = "USDT",
        min_volume_usd: float = 50_000_000,
        min_oi_usd: float = 20_000_000,
        new_listing_days: int = 7,
    ):
        self.base_url          = base_url
        self.top_n             = top_n
        self.refresh_interval  = refresh_interval_hours * 3600
        self.blacklist         = set(blacklist or [])
        self.quote_asset       = quote_asset
        self.min_volume_usd    = min_volume_usd
        self.min_oi_usd        = min_oi_usd
        self.new_listing_days  = new_listing_days

        self._symbols: list[str]       = []
        self._last_refresh: float      = 0.0
        # Cache exchange info (listing dates) — refresh sekali per sesi
        self._listing_dates: dict[str, datetime] = {}
        self._listing_dates_fetched: bool        = False

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def symbols(self) -> list[str]:
        if self._needs_refresh():
            self._refresh()
        return self._symbols

    def force_refresh(self) -> list[str]:
        self._refresh()
        return self._symbols

    def time_until_next_refresh(self) -> str:
        remaining = (self._last_refresh + self.refresh_interval) - time.time()
        if remaining <= 0:
            return "sekarang"
        h = int(remaining // 3600)
        m = int((remaining % 3600) // 60)
        return f"{h}j {m}m"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _needs_refresh(self) -> bool:
        return (
            not self._symbols
            or (time.time() - self._last_refresh) >= self.refresh_interval
        )

    def _refresh(self) -> None:
        """
        Pipeline 3 tahap:
          Tahap 1 — filter Volume ≥ MIN_VOLUME_USD dari ticker 24j
          Tahap 2 — exclude pair listing baru (< NEW_LISTING_DAYS hari)
          Tahap 3 — filter Open Interest ≥ MIN_OI_USD per kandidat
        Hasil akhir: top N pair diurutkan berdasarkan volume descending.
        """
        logger.info("[SymbolManager] Memulai refresh watchlist...")

        # ── Tahap 1: Volume filter ────────────────────────────────────────────
        candidates = self._fetch_volume_candidates()
        if not candidates:
            logger.warning("[SymbolManager] Tidak ada kandidat dari volume filter, pakai fallback.")
            if not self._symbols:
                self._symbols = self._fallback_symbols()
            return

        logger.info(f"[SymbolManager] Tahap 1 (Volume ≥ ${self.min_volume_usd/1e6:.0f}M): {len(candidates)} kandidat")

        # ── Tahap 2: Exclude new listings ────────────────────────────────────
        candidates = self._filter_new_listings(candidates)
        logger.info(f"[SymbolManager] Tahap 2 (Listing ≥ {self.new_listing_days} hari): {len(candidates)} kandidat")

        if not candidates:
            logger.warning("[SymbolManager] Semua kandidat terfilter oleh new listing, pakai fallback.")
            if not self._symbols:
                self._symbols = self._fallback_symbols()
            return

        # ── Tahap 3: OI filter ────────────────────────────────────────────────
        candidates = self._filter_by_oi(candidates)
        logger.info(f"[SymbolManager] Tahap 3 (OI ≥ ${self.min_oi_usd/1e6:.0f}M): {len(candidates)} kandidat")

        if not candidates:
            logger.warning("[SymbolManager] Semua kandidat gagal OI filter, pakai fallback.")
            if not self._symbols:
                self._symbols = self._fallback_symbols()
            return

        # ── Finalisasi: sort by volume, ambil top N ───────────────────────────
        candidates.sort(key=lambda x: x["volume"], reverse=True)
        new_symbols = [c["symbol"] for c in candidates[: self.top_n]]

        old_symbols = self._symbols.copy()
        self._symbols = new_symbols
        self._last_refresh = time.time()

        self._log_changes(old_symbols, new_symbols)
        logger.info(
            f"[SymbolManager] Watchlist diperbarui ({len(new_symbols)} pair): {new_symbols} "
            f"| Refresh berikutnya dalam {self.refresh_interval // 3600} jam"
        )

    # ── Tahap 1: Volume candidates ────────────────────────────────────────────

    def _fetch_volume_candidates(self) -> list[dict]:
        """
        Ambil semua ticker 24j dari Binance, filter:
          - quote asset = USDT
          - bukan quarterly/delivery contract (tidak ada underscore)
          - tidak di blacklist
          - quoteVolume ≥ min_volume_usd
        Return list of {"symbol": str, "volume": float}
        """
        try:
            resp = requests.get(
                f"{self.base_url}{_EP_TICKER}", timeout=10
            )
            resp.raise_for_status()
            tickers = resp.json()
        except requests.RequestException as e:
            logger.error(f"[SymbolManager] Gagal fetch ticker: {e}")
            return []

        result = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith(self.quote_asset):
                continue
            if "_" in sym:          # quarterly / delivery
                continue
            if sym in self.blacklist:
                continue
            vol = float(t.get("quoteVolume", 0))
            if vol < self.min_volume_usd:
                continue
            result.append({"symbol": sym, "volume": vol})

        return result

    # ── Tahap 2: New listing filter ───────────────────────────────────────────

    def _fetch_listing_dates(self) -> None:
        """
        Fetch exchange info sekali untuk mendapatkan onboardDate setiap pair.
        Binance menyediakan field 'onboardDate' (ms timestamp) di exchangeInfo.
        """
        try:
            resp = requests.get(
                f"{self.base_url}{_EP_EXCH_INFO}", timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"[SymbolManager] Gagal fetch exchangeInfo: {e}")
            self._listing_dates_fetched = True   # jangan retry terus
            return

        for s in data.get("symbols", []):
            onboard_ms = s.get("onboardDate")
            if onboard_ms:
                self._listing_dates[s["symbol"]] = datetime.fromtimestamp(
                    onboard_ms / 1000, tz=timezone.utc
                )

        self._listing_dates_fetched = True
        logger.info(f"[SymbolManager] Listing dates berhasil di-cache untuk {len(self._listing_dates)} symbol")

    def _filter_new_listings(self, candidates: list[dict]) -> list[dict]:
        """Exclude pair yang listing-nya kurang dari NEW_LISTING_DAYS hari."""
        if not self._listing_dates_fetched:
            self._fetch_listing_dates()

        if not self._listing_dates:
            # Tidak bisa fetch exchange info — skip filter ini, jangan block semua
            logger.warning("[SymbolManager] Listing dates tidak tersedia, skip new-listing filter.")
            return candidates

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.new_listing_days)
        filtered = []
        for c in candidates:
            listed_on = self._listing_dates.get(c["symbol"])
            if listed_on is None:
                # Tidak ada data listing → anggap sudah cukup lama, loloskan
                filtered.append(c)
            elif listed_on <= cutoff:
                filtered.append(c)
            else:
                age_days = (datetime.now(timezone.utc) - listed_on).days
                logger.debug(
                    f"[SymbolManager] Exclude {c['symbol']} — listing baru {age_days} hari lalu"
                )

        excluded = len(candidates) - len(filtered)
        if excluded:
            logger.info(f"[SymbolManager] {excluded} pair dikeluarkan karena listing < {self.new_listing_days} hari")

        return filtered

    # ── Tahap 3: Open Interest filter ────────────────────────────────────────

    def _filter_by_oi(self, candidates: list[dict]) -> list[dict]:
        """
        Fetch OI per-symbol untuk setiap kandidat dan filter OI ≥ min_oi_usd.
        Binance tidak punya bulk OI endpoint — request dilakukan satu per satu
        tapi hanya untuk kandidat yang sudah lolos filter sebelumnya (~50-100 pair).
        """
        passed = []
        for c in candidates:
            sym = c["symbol"]
            try:
                resp = requests.get(
                    f"{self.base_url}{_EP_OI}",
                    params={"symbol": sym},
                    timeout=5,
                )
                resp.raise_for_status()
                data = resp.json()
                oi_contracts = float(data.get("openInterest", 0))

                # OI dari Binance dalam satuan base asset, kalikan harga untuk dapat USD
                # Gunakan markPrice dari ticker jika ada, fallback ke 1
                price = self._get_mark_price(sym)
                oi_usd = oi_contracts * price

                if oi_usd >= self.min_oi_usd:
                    c["oi_usd"] = oi_usd
                    passed.append(c)
                else:
                    logger.debug(
                        f"[SymbolManager] Exclude {sym} — OI ${oi_usd/1e6:.1f}M < ${self.min_oi_usd/1e6:.0f}M"
                    )

            except requests.RequestException as e:
                logger.warning(f"[SymbolManager] Gagal fetch OI untuk {sym}: {e}, dilewati")
                # Jika tidak bisa fetch OI, loloskan saja agar tidak block pair bagus
                passed.append(c)

            time.sleep(0.05)   # jeda kecil agar tidak spam rate limit

        return passed

    def _get_mark_price(self, symbol: str) -> float:
        """Ambil harga mark terkini untuk konversi OI ke USD. Fallback ke 1 jika gagal."""
        try:
            resp = requests.get(
                f"{self.base_url}/fapi/v1/premiumIndex",
                params={"symbol": symbol},
                timeout=5,
            )
            resp.raise_for_status()
            return float(resp.json().get("markPrice", 1))
        except Exception:
            return 1.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_changes(self, old: list[str], new: list[str]) -> None:
        added   = set(new) - set(old)
        removed = set(old) - set(new)
        if added:
            logger.info(f"[SymbolManager] Pair MASUK: {sorted(added)}")
        if removed:
            logger.info(f"[SymbolManager] Pair KELUAR: {sorted(removed)}")

    def _fallback_symbols(self) -> list[str]:
        """Fallback ke Config.SYMBOLS_FALLBACK jika API tidak bisa diakses sama sekali."""
        return list(Config.SYMBOLS_FALLBACK)

