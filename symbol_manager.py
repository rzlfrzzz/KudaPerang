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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        # Cache listing dates — di-refresh bersamaan dengan watchlist (tiap siklus _refresh)
        self._listing_dates: dict[str, datetime] = {}
        self._listing_dates_last_fetch: float    = 0.0

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

        # Refresh listing dates setiap siklus agar pair baru terdeteksi
        self._fetch_listing_dates()

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
            result.append({
                "symbol": sym,
                "volume": vol,
                "last_price": float(t.get("lastPrice") or t.get("markPrice") or 1),
            })

        return result

    # ── Tahap 2: New listing filter ───────────────────────────────────────────

    def _fetch_listing_dates(self) -> None:
        """
        Fetch exchange info untuk mendapatkan onboardDate setiap pair.
        Dipanggil setiap siklus refresh watchlist agar pair listing baru terdeteksi.
        """
        try:
            resp = requests.get(
                f"{self.base_url}{_EP_EXCH_INFO}", timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"[SymbolManager] Gagal fetch exchangeInfo: {e}")
            return

        new_dates: dict[str, datetime] = {}
        for s in data.get("symbols", []):
            onboard_ms = s.get("onboardDate")
            if onboard_ms:
                new_dates[s["symbol"]] = datetime.fromtimestamp(
                    onboard_ms / 1000, tz=timezone.utc
                )

        self._listing_dates = new_dates
        self._listing_dates_last_fetch = time.time()
        logger.info(f"[SymbolManager] Listing dates di-refresh untuk {len(new_dates)} symbol")

    def _filter_new_listings(self, candidates: list[dict]) -> list[dict]:
        """Exclude pair yang listing-nya kurang dari NEW_LISTING_DAYS hari."""
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
        Fetch OI secara concurrent (max 5 thread) lalu filter OI ≥ min_oi_usd.
        Tidak ada blocking sleep di main thread — tiap thread jeda 0.1s sendiri.

        Fallback policy: pair yang gagal di-fetch OI hanya diloloskan jika
        jumlah error < 30% dari total kandidat (intermittent).
        """
        error_limit = max(1, int(len(candidates) * 0.30))
        results: list[tuple[dict, float | None]] = []   # (candidate, oi_usd | None)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self._fetch_oi_single, c): c for c in candidates}
            for future in as_completed(futures):
                c = futures[future]
                try:
                    oi_usd = future.result()
                    results.append((c, oi_usd))
                except Exception as e:
                    logger.warning(f"[SymbolManager] Thread OI error untuk {c['symbol']}: {e}")
                    results.append((c, None))

        passed      = []
        error_count = sum(1 for _, v in results if v is None)

        if error_count > 0:
            logger.info(f"[SymbolManager] OI fetch: {error_count} error dari {len(candidates)} kandidat")

        for c, oi_usd in results:
            if oi_usd is None:
                if error_count <= error_limit:
                    passed.append(c)   # intermittent — loloskan
                else:
                    logger.warning(f"[SymbolManager] Skip {c['symbol']} — OI tidak bisa di-fetch (terlalu banyak error)")
            elif oi_usd >= self.min_oi_usd:
                c["oi_usd"] = oi_usd
                passed.append(c)
            else:
                logger.debug(
                    f"[SymbolManager] Exclude {c['symbol']} — OI ${oi_usd/1e6:.1f}M < ${self.min_oi_usd/1e6:.0f}M"
                )

        return passed

    def _fetch_oi_single(self, c: dict) -> float:
        """
        Fetch OI satu symbol dan return nilai OI dalam USD.
        Dipanggil dari thread pool. Raise exception jika request gagal.
        """
        resp = requests.get(
            f"{self.base_url}{_EP_OI}",
            params={"symbol": c["symbol"]},
            timeout=5,
        )
        resp.raise_for_status()
        oi_contracts = float(resp.json().get("openInterest", 0))
        price        = c.get("last_price", 1.0)
        time.sleep(0.1)   # jeda kecil per thread agar tidak spike
        return oi_contracts * price

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

