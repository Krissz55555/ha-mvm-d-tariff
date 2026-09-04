from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
import logging
import re

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DISTRIBUTION_FEE,
    CONF_MERCHANT_FEE,
    CONF_TRANSMISSION_FEE,
    CONF_VAT_PERCENT,
    DEFAULT_DISTRIBUTION_FEE_HUF_KWH,
    DEFAULT_MERCHANT_FEE_HUF_KWH,
    DEFAULT_TRANSMISSION_FEE_HUF_KWH,
    DEFAULT_VAT_PERCENT,
    ENERGY_CHARTS_CURRENT_URL,
    ENERGY_CHARTS_PRICE_URL,
    MNB_EXCHANGE_RATE_URL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# The next-day DAM curve is normally published during the previous day.
# Before noon it is usually pointless to continuously retry. After this time,
# the coordinator checks periodically until a usable next-day curve appears.
NEXT_DAY_FIRST_CHECK_HOUR = 12
NEXT_DAY_RETRY_INTERVAL = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    timestamp: str
    hupx_eur_mwh: float
    hupx_huf_kwh_net: float
    d_price_huf_kwh_gross: float


@dataclass(frozen=True, slots=True)
class TariffData:
    price_huf_kwh_gross: float
    hupx_eur_mwh: float
    hupx_huf_kwh_net: float
    eur_huf: float
    merchant_fee_huf_kwh_net: float
    transmission_fee_huf_kwh_net: float
    distribution_fee_huf_kwh_net: float
    vat_percent: float
    valid_until: str | None
    interval_start: str | None
    source_generated_at: str | None
    forecast: tuple[ForecastPoint, ...]
    forecast_date: str | None
    forecast_generated_at: str | None
    forecast_is_fallback: bool
    tomorrow_forecast: tuple[ForecastPoint, ...]
    tomorrow_forecast_date: str | None
    tomorrow_forecast_generated_at: str | None
    tomorrow_forecast_is_fallback: bool


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _extract_numeric_price(values: dict) -> float:
    price = values.get("price")
    if price is None:
        numeric = [v for v in values.values() if isinstance(v, (int, float))]
        if len(numeric) != 1:
            raise ValueError("Cannot identify price series")
        price = numeric[0]
    return float(price)


def _extract_price(payload: dict) -> tuple[float, str | None, str | None, str | None]:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("Energy-Charts response contains no data")
    point = data[0]
    values = point.get("values")
    if not isinstance(values, dict) or not values:
        raise ValueError("Energy-Charts response contains no values")
    attributes = payload.get("attributes") or {}
    return (
        _extract_numeric_price(values),
        point.get("timestamp"),
        attributes.get("valid_until"),
        payload.get("generated_at"),
    )


def _parse_mnb_eur_huf_html(html: str) -> float:
    compact = re.sub(r"\s+", " ", html)
    match = re.search(
        r">\s*EUR\s*<.*?>\s*(?:Euro|Euró)\s*<.*?>\s*1\s*<.*?>\s*([0-9]+[.,][0-9]+)\s*<",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"EUR.{0,800}?([0-9]{3}[.,][0-9]{2,4})", compact, flags=re.IGNORECASE)
    if not match:
        raise ValueError("EUR rate not found on MNB exchange-rate page")
    return float(match.group(1).replace(",", "."))


class MvmDTariffCoordinator(DataUpdateCoordinator[TariffData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="MVM D Tariff",
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.entry = entry
        self.session = async_get_clientsession(hass)
        # Keep store version 1 so existing v0.2 test installations can be read.
        # The payload is migrated in memory from the old single-day shape.
        self._forecast_store: Store[dict] = Store(hass, 1, f"{entry.entry_id}_mvm_d_tariff_forecast")
        self._stored_forecast: dict = {"days": {}}
        self._first_update = True
        self._last_tomorrow_attempt: datetime | None = None

    async def async_load_cached_forecast(self) -> None:
        stored = await self._forecast_store.async_load()
        if not isinstance(stored, dict):
            self._stored_forecast = {"days": {}}
            return

        if isinstance(stored.get("days"), dict):
            self._stored_forecast = stored
            return

        # Backward-compatible migration from the dev single-day cache format.
        old_date = stored.get("date")
        old_points = stored.get("points")
        if old_date and isinstance(old_points, list):
            self._stored_forecast = {
                "days": {
                    str(old_date): {
                        "generated_at": stored.get("generated_at"),
                        "points": old_points,
                    }
                }
            }
        else:
            self._stored_forecast = {"days": {}}

    def _fees(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        merchant = Decimal(str(self.entry.options.get(CONF_MERCHANT_FEE, DEFAULT_MERCHANT_FEE_HUF_KWH)))
        transmission = Decimal(str(self.entry.options.get(CONF_TRANSMISSION_FEE, DEFAULT_TRANSMISSION_FEE_HUF_KWH)))
        distribution = Decimal(str(self.entry.options.get(CONF_DISTRIBUTION_FEE, DEFAULT_DISTRIBUTION_FEE_HUF_KWH)))
        vat_pct = Decimal(str(self.entry.options.get(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT)))
        return merchant, transmission, distribution, vat_pct

    def gross_d_price(self, hupx_eur_mwh: float, eur_huf: float) -> tuple[float, float]:
        merchant, transmission, distribution, vat_pct = self._fees()
        hupx_huf = Decimal(str(hupx_eur_mwh)) * Decimal(str(eur_huf)) / Decimal("1000")
        net = hupx_huf + merchant + transmission + distribution
        gross = net * (Decimal("1") + vat_pct / Decimal("100"))
        return float(_money(hupx_huf)), float(_money(gross))

    async def _async_fetch_hupx(self) -> tuple[float, str | None, str | None, str | None]:
        try:
            async with self.session.get(ENERGY_CHARTS_CURRENT_URL, timeout=20) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise UpdateFailed(f"HUPX/Energy-Charts query failed: {err}") from err
        try:
            return _extract_price(payload)
        except (TypeError, ValueError, KeyError) as err:
            raise UpdateFailed(f"Unexpected Energy-Charts response: {err}") from err

    async def _async_fetch_mnb_eur_huf(self) -> float:
        try:
            async with self.session.get(MNB_EXCHANGE_RATE_URL, timeout=20) as response:
                response.raise_for_status()
                text = await response.text()
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"MNB exchange-rate query failed: {err}") from err
        try:
            return _parse_mnb_eur_huf_html(text)
        except ValueError as err:
            raise UpdateFailed(f"Unexpected MNB response: {err}") from err

    async def _async_save_forecast_day(
        self,
        target_date: str,
        generated_at: str | None,
        points: tuple[ForecastPoint, ...],
    ) -> None:
        days = self._stored_forecast.setdefault("days", {})
        days[target_date] = {
            "generated_at": generated_at,
            # Raw HUPX EUR/MWh is authoritative. HUF prices are retained for
            # diagnostics, but are recalculated from the current MNB rate when
            # a cached curve is read.
            "points": [
                {
                    "timestamp": p.timestamp,
                    "hupx_eur_mwh": p.hupx_eur_mwh,
                    "hupx_huf_kwh_net": p.hupx_huf_kwh_net,
                    "d_price_huf_kwh_gross": p.d_price_huf_kwh_gross,
                }
                for p in points
            ],
        }

        # Keep only a small rolling window: yesterday, today and next days.
        today = dt_util.now().date()
        keep_from = (today - timedelta(days=1)).isoformat()
        for cached_date in list(days):
            if cached_date < keep_from:
                days.pop(cached_date, None)

        await self._forecast_store.async_save(self._stored_forecast)

    async def _async_fetch_day_forecast(
        self,
        target: date,
        eur_huf: float,
    ) -> tuple[tuple[ForecastPoint, ...], str, str | None]:
        target_date = target.isoformat()
        url = f"{ENERGY_CHARTS_PRICE_URL}?bzn=HU&start={target_date}&end={target_date}"
        try:
            async with self.session.get(url, timeout=20) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise ValueError(f"Energy-Charts daily curve query failed for {target_date}: {err}") from err

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError(f"Energy-Charts daily curve contains no data for {target_date}")

        points: list[ForecastPoint] = []
        for row in data:
            values = row.get("values")
            timestamp = row.get("timestamp")
            if not isinstance(values, dict) or not timestamp:
                continue
            price_eur = _extract_numeric_price(values)
            hupx_huf, gross = self.gross_d_price(price_eur, eur_huf)
            points.append(ForecastPoint(str(timestamp), price_eur, hupx_huf, gross))

        if not points:
            raise ValueError(f"Energy-Charts daily curve has no usable points for {target_date}")

        generated_at = payload.get("generated_at")
        result = tuple(points)
        await self._async_save_forecast_day(target_date, generated_at, result)
        return result, target_date, generated_at

    def _cached_forecast_for_date(
        self,
        target: date,
        eur_huf: float,
    ) -> tuple[tuple[ForecastPoint, ...], str | None, str | None]:
        target_date = target.isoformat()
        days = self._stored_forecast.get("days") or {}
        cached = days.get(target_date) or {}
        raw_points = cached.get("points") or []
        points: list[ForecastPoint] = []
        for item in raw_points:
            try:
                price_eur = float(item["hupx_eur_mwh"])
                hupx_huf, gross = self.gross_d_price(price_eur, eur_huf)
                points.append(
                    ForecastPoint(
                        timestamp=str(item["timestamp"]),
                        hupx_eur_mwh=price_eur,
                        hupx_huf_kwh_net=hupx_huf,
                        d_price_huf_kwh_gross=gross,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not points:
            return (), None, None
        return tuple(points), target_date, cached.get("generated_at")

    def _should_try_tomorrow(self, tomorrow: date) -> bool:
        # Already cached: no need to repeatedly download a fixed DAM curve.
        days = self._stored_forecast.get("days") or {}
        if tomorrow.isoformat() in days and (days[tomorrow.isoformat()].get("points") or []):
            return False

        now = dt_util.now()
        # On the first coordinator update (startup/reload), try immediately if
        # we are already in the likely publication window.
        if now.hour < NEXT_DAY_FIRST_CHECK_HOUR:
            return False
        if self._last_tomorrow_attempt is None:
            return True
        return now - self._last_tomorrow_attempt >= NEXT_DAY_RETRY_INTERVAL

    async def _async_update_data(self) -> TariffData:
        # Current interval and official exchange rate are always refreshed on
        # startup and then by the normal coordinator interval.
        hupx_eur_mwh, interval_start, valid_until, generated_at = await self._async_fetch_hupx()
        eur_huf = await self._async_fetch_mnb_eur_huf()

        merchant, transmission, distribution, vat_pct = self._fees()
        hupx_huf_float, gross_float = self.gross_d_price(hupx_eur_mwh, eur_huf)

        today = dt_util.now().date()
        tomorrow = today + timedelta(days=1)

        # TODAY: on startup/reload always download a fresh current-day DAM
        # curve. During normal 5-minute polling the already cached curve is
        # sufficient because day-ahead prices are fixed for that delivery day.
        forecast_is_fallback = False
        forecast: tuple[ForecastPoint, ...]
        forecast_date: str | None
        forecast_generated_at: str | None
        if self._first_update:
            try:
                forecast, forecast_date, forecast_generated_at = await self._async_fetch_day_forecast(today, eur_huf)
            except (TypeError, ValueError, KeyError) as err:
                _LOGGER.warning("Using cached D tariff forecast for today: %s", err)
                forecast, forecast_date, forecast_generated_at = self._cached_forecast_for_date(today, eur_huf)
                forecast_is_fallback = bool(forecast)
        else:
            forecast, forecast_date, forecast_generated_at = self._cached_forecast_for_date(today, eur_huf)
            if not forecast:
                try:
                    forecast, forecast_date, forecast_generated_at = await self._async_fetch_day_forecast(today, eur_huf)
                except (TypeError, ValueError, KeyError) as err:
                    _LOGGER.warning("D tariff forecast for today unavailable: %s", err)
                    forecast_is_fallback = False

        # TOMORROW: if already cached, expose it immediately. If it is not yet
        # published, retry periodically after noon. On startup after noon this
        # attempt happens immediately, so no waiting for the next long cycle.
        tomorrow_is_fallback = False
        tomorrow_forecast, tomorrow_date, tomorrow_generated_at = self._cached_forecast_for_date(tomorrow, eur_huf)
        if self._should_try_tomorrow(tomorrow):
            self._last_tomorrow_attempt = dt_util.now()
            try:
                tomorrow_forecast, tomorrow_date, tomorrow_generated_at = await self._async_fetch_day_forecast(
                    tomorrow, eur_huf
                )
            except (TypeError, ValueError, KeyError) as err:
                # This is expected before the next-day DAM publication.
                _LOGGER.debug("Next-day DAM curve not available yet: %s", err)
                tomorrow_forecast, tomorrow_date, tomorrow_generated_at = self._cached_forecast_for_date(
                    tomorrow, eur_huf
                )
                tomorrow_is_fallback = bool(tomorrow_forecast)

        self._first_update = False

        return TariffData(
            price_huf_kwh_gross=gross_float,
            hupx_eur_mwh=hupx_eur_mwh,
            hupx_huf_kwh_net=hupx_huf_float,
            eur_huf=eur_huf,
            merchant_fee_huf_kwh_net=float(merchant),
            transmission_fee_huf_kwh_net=float(transmission),
            distribution_fee_huf_kwh_net=float(distribution),
            vat_percent=float(vat_pct),
            valid_until=valid_until,
            interval_start=interval_start,
            source_generated_at=generated_at,
            forecast=forecast,
            forecast_date=forecast_date,
            forecast_generated_at=forecast_generated_at,
            forecast_is_fallback=forecast_is_fallback,
            tomorrow_forecast=tomorrow_forecast,
            tomorrow_forecast_date=tomorrow_date,
            tomorrow_forecast_generated_at=tomorrow_generated_at,
            tomorrow_forecast_is_fallback=tomorrow_is_fallback,
        )
