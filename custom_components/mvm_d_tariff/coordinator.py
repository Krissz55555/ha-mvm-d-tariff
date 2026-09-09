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
    ENERGY_CHARTS_NEXT_DAY_URL,
    ENERGY_CHARTS_PRICE_URL,
    MNB_EXCHANGE_RATE_URL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

NEXT_DAY_FIRST_CHECK_HOUR = 12
NEXT_DAY_RETRY_INTERVAL = timedelta(minutes=15)
TODAY_RETRY_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    timestamp: str
    hupx_eur_mwh: float
    hupx_huf_kwh_net: float
    d_price_huf_kwh_gross: float


@dataclass(frozen=True, slots=True)
class TariffData:
    price_huf_kwh_gross: float | None
    hupx_eur_mwh: float | None
    hupx_huf_kwh_net: float | None
    eur_huf: float | None
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
    forecast_current_price_huf_kwh_gross: float | None
    current_price_source: str | None
    fx_source: str | None
    forecast_source: str | None
    tomorrow_forecast: tuple[ForecastPoint, ...]
    tomorrow_forecast_date: str | None
    tomorrow_forecast_generated_at: str | None
    tomorrow_forecast_is_fallback: bool
    tomorrow_forecast_source: str | None


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
    """Coordinator with independent external-source channels.

    The three external channels (MNB FX, current HUPX, daily DAM) are isolated:
    a failure in one channel never raises the whole coordinator update. Each
    channel has its own persisted fallback state. This keeps unrelated entities
    alive during partial upstream outages.
    """

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

        # Existing forecast store is preserved for upgrade compatibility.
        self._forecast_store: Store[dict] = Store(
            hass, 1, f"{entry.entry_id}_mvm_d_tariff_forecast"
        )
        self._stored_forecast: dict = {"days": {}}

        # New independent source cache. It intentionally has a separate Store
        # key so forecast history and other v0.2.x persisted state are untouched.
        self._source_store: Store[dict] = Store(
            hass, 1, f"{entry.entry_id}_mvm_d_tariff_sources"
        )
        self._stored_sources: dict = {}

        self._last_tomorrow_attempt: datetime | None = None
        self._last_today_attempt: datetime | None = None

    async def async_load_cached_forecast(self) -> None:
        stored = await self._forecast_store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("days"), dict):
            self._stored_forecast = stored
        elif isinstance(stored, dict):
            # Migration from the older single-day cache shape.
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
        else:
            self._stored_forecast = {"days": {}}

        source_state = await self._source_store.async_load()
        self._stored_sources = source_state if isinstance(source_state, dict) else {}

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

    # ---------------------------------------------------------------------
    # Channel A: current HUPX endpoint
    # ---------------------------------------------------------------------
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

    async def _async_save_current_source(
        self,
        price_eur_mwh: float,
        interval_start: str | None,
        valid_until: str | None,
        generated_at: str | None,
    ) -> None:
        self._stored_sources["current"] = {
            "hupx_eur_mwh": price_eur_mwh,
            "interval_start": interval_start,
            "valid_until": valid_until,
            "generated_at": generated_at,
            "saved_at": dt_util.utcnow().isoformat(),
        }
        try:
            await self._source_store.async_save(self._stored_sources)
        except Exception as err:  # persistence failure must not invalidate live API data
            _LOGGER.warning("Could not persist current-price cache: %s", err)

    # ---------------------------------------------------------------------
    # Channel B: MNB EUR/HUF
    # ---------------------------------------------------------------------
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

    async def _async_get_fx(self) -> tuple[float | None, str | None]:
        try:
            value = await self._async_fetch_mnb_eur_huf()
            self._stored_sources["fx"] = {
                "eur_huf": value,
                "saved_at": dt_util.utcnow().isoformat(),
            }
            try:
                await self._source_store.async_save(self._stored_sources)
            except Exception as save_err:  # live FX remains usable even if Store has a problem
                _LOGGER.warning("Could not persist MNB FX cache: %s", save_err)
            return value, "mnb_live"
        except UpdateFailed as err:
            cached = self._stored_sources.get("fx") or {}
            try:
                value = float(cached["eur_huf"])
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("MNB EUR/HUF unavailable and no cached FX exists: %s", err)
                return None, None
            _LOGGER.warning("MNB EUR/HUF unavailable; using persisted FX cache: %s", err)
            return value, "mnb_cache"

    # ---------------------------------------------------------------------
    # Channel C: daily DAM curves + independent persistent cache
    # ---------------------------------------------------------------------
    async def _async_save_forecast_day(
        self,
        target_date: str,
        generated_at: str | None,
        points: tuple[ForecastPoint, ...],
    ) -> None:
        days = self._stored_forecast.setdefault("days", {})
        days[target_date] = {
            "generated_at": generated_at,
            "saved_at": dt_util.utcnow().isoformat(),
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

        today = dt_util.now().date()
        keep_from = (today - timedelta(days=1)).isoformat()
        keep_until = (today + timedelta(days=2)).isoformat()
        for cached_date in list(days):
            if cached_date < keep_from or cached_date > keep_until:
                days.pop(cached_date, None)

        try:
            await self._forecast_store.async_save(self._stored_forecast)
        except Exception as err:  # fetched DAM remains usable even if persistence fails
            _LOGGER.warning("Could not persist DAM forecast cache: %s", err)

    def _parse_forecast_payload(
        self,
        payload: dict,
        target_date: str,
        eur_huf: float,
    ) -> tuple[tuple[ForecastPoint, ...], str, str | None]:
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

        return tuple(points), target_date, payload.get("generated_at")

    async def _async_fetch_day_forecast(
        self,
        target: date,
        eur_huf: float,
    ) -> tuple[tuple[ForecastPoint, ...], str, str | None]:
        target_date = target.isoformat()
        # Daily format: a single start date already means the complete local day.
        # Avoid redundant end=... because the v2 API explicitly documents this.
        url = f"{ENERGY_CHARTS_PRICE_URL}?bzn=HU&start={target_date}"
        try:
            async with self.session.get(url, timeout=20) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise ValueError(f"Energy-Charts daily curve query failed for {target_date}: {err}") from err

        result, result_date, generated_at = self._parse_forecast_payload(payload, target_date, eur_huf)
        await self._async_save_forecast_day(result_date, generated_at, result)
        return result, result_date, generated_at

    async def _async_fetch_next_day_forecast(
        self,
        target: date,
        eur_huf: float,
    ) -> tuple[tuple[ForecastPoint, ...], str, str | None]:
        target_date = target.isoformat()
        try:
            async with self.session.get(ENERGY_CHARTS_NEXT_DAY_URL, timeout=20) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise ValueError(f"Energy-Charts next-day curve query failed for {target_date}: {err}") from err

        attributes = payload.get("attributes") or {}
        delivery_date = attributes.get("delivery_date")
        if delivery_date and str(delivery_date) != target_date:
            raise ValueError(
                f"Energy-Charts next-day delivery date mismatch: expected {target_date}, got {delivery_date}"
            )

        result, result_date, generated_at = self._parse_forecast_payload(payload, target_date, eur_huf)
        await self._async_save_forecast_day(result_date, generated_at, result)
        return result, result_date, generated_at

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

    def _current_forecast_point(
        self,
        forecast: tuple[ForecastPoint, ...],
    ) -> tuple[ForecastPoint, str | None] | None:
        now_utc = dt_util.utcnow()
        timed_points: list[tuple[datetime, ForecastPoint]] = []

        for point in forecast:
            parsed = dt_util.parse_datetime(point.timestamp)
            if parsed is None or parsed.tzinfo is None:
                continue
            timed_points.append((dt_util.as_utc(parsed), point))

        if not timed_points:
            return None

        timed_points.sort(key=lambda item: item[0])
        selected_index: int | None = None
        for index, (timestamp, _) in enumerate(timed_points):
            if timestamp <= now_utc:
                selected_index = index
            else:
                break

        if selected_index is None:
            return None

        selected = timed_points[selected_index][1]
        valid_until = (
            timed_points[selected_index + 1][1].timestamp
            if selected_index + 1 < len(timed_points)
            else None
        )
        return selected, valid_until

    def _should_try_tomorrow(self, tomorrow: date) -> bool:
        days = self._stored_forecast.get("days") or {}
        if tomorrow.isoformat() in days and (days[tomorrow.isoformat()].get("points") or []):
            return False

        now = dt_util.now()
        if now.hour < NEXT_DAY_FIRST_CHECK_HOUR:
            return False
        if self._last_tomorrow_attempt is None:
            return True
        return now - self._last_tomorrow_attempt >= NEXT_DAY_RETRY_INTERVAL

    async def _async_get_today_forecast(
        self,
        today: date,
        eur_huf: float | None,
    ) -> tuple[tuple[ForecastPoint, ...], str | None, str | None, bool, str | None]:
        if eur_huf is None:
            return (), None, None, False, None

        # Cache-first at startup/midnight: tomorrow's curve is pre-fetched the
        # previous afternoon, so an overnight API outage cannot wipe the day.
        cached, cached_date, cached_generated = self._cached_forecast_for_date(today, eur_huf)
        if cached:
            return cached, cached_date, cached_generated, True, "today_dam_cache"

        # No cache exists for the new calendar day. Retry every five minutes
        # until the new DAM curve appears. Manual/extra coordinator refreshes
        # inside that window do not hammer the API. A failed attempt never
        # deletes yesterday/tomorrow cache entries.
        now = dt_util.now()
        if (
            self._last_today_attempt is not None
            and now - self._last_today_attempt < TODAY_RETRY_INTERVAL
        ):
            return (), None, None, False, None
        self._last_today_attempt = now
        try:
            forecast, forecast_date, generated_at = await self._async_fetch_day_forecast(today, eur_huf)
            return forecast, forecast_date, generated_at, False, "today_dam_live"
        except (TypeError, ValueError, KeyError) as err:
            _LOGGER.warning(
                "Today DAM unavailable; retrying automatically on the next 5-minute update. "
                "Persisted caches are kept intact: %s",
                err,
            )
            return (), None, None, False, None

    async def _async_get_tomorrow_forecast(
        self,
        tomorrow: date,
        eur_huf: float | None,
    ) -> tuple[tuple[ForecastPoint, ...], str | None, str | None, bool, str | None]:
        if eur_huf is None:
            return (), None, None, False, None

        cached, cached_date, cached_generated = self._cached_forecast_for_date(tomorrow, eur_huf)
        if cached:
            return cached, cached_date, cached_generated, True, "tomorrow_dam_cache"

        if not self._should_try_tomorrow(tomorrow):
            return (), None, None, False, None

        self._last_tomorrow_attempt = dt_util.now()
        try:
            forecast, forecast_date, generated_at = await self._async_fetch_next_day_forecast(tomorrow, eur_huf)
            return forecast, forecast_date, generated_at, False, "price_next_day"
        except (TypeError, ValueError, KeyError) as next_day_err:
            # Some Energy-Charts publication windows can make price_next_day
            # temporarily unavailable. Try the generic dated DAM endpoint too
            # before waiting for the next 15-minute prefetch attempt.
            try:
                forecast, forecast_date, generated_at = await self._async_fetch_day_forecast(tomorrow, eur_huf)
                return forecast, forecast_date, generated_at, False, "tomorrow_dam_live"
            except (TypeError, ValueError, KeyError) as dated_err:
                _LOGGER.debug(
                    "Next-day DAM not available yet; retrying in 15 minutes. "
                    "price_next_day=%s; dated_DAM=%s",
                    next_day_err,
                    dated_err,
                )
                return (), None, None, False, None

    async def _async_update_data(self) -> TariffData:
        """Refresh all channels independently and always return partial data."""
        merchant, transmission, distribution, vat_pct = self._fees()
        today = dt_util.now().date()
        tomorrow = today + timedelta(days=1)

        # B: FX channel. Unexpected failures are contained here so they cannot
        # mark the DAM/current/cost channels unavailable.
        try:
            eur_huf, fx_source = await self._async_get_fx()
        except Exception as err:
            _LOGGER.exception("Independent MNB channel failed unexpectedly: %s", err)
            eur_huf, fx_source = None, None

        # C: DAM channel. A today-DAM failure is isolated from current price and
        # from the tomorrow-prefetch channel.
        try:
            forecast, forecast_date, forecast_generated_at, forecast_is_fallback, forecast_source = (
                await self._async_get_today_forecast(today, eur_huf)
            )
        except Exception as err:
            _LOGGER.exception("Independent today-DAM channel failed unexpectedly: %s", err)
            forecast, forecast_date, forecast_generated_at = (), None, None
            forecast_is_fallback, forecast_source = False, None

        try:
            active_forecast = self._current_forecast_point(forecast)
        except Exception as err:
            _LOGGER.exception("Could not resolve active DAM interval: %s", err)
            active_forecast = None
        forecast_current_price = active_forecast[0].d_price_huf_kwh_gross if active_forecast else None

        try:
            tomorrow_forecast, tomorrow_date, tomorrow_generated_at, tomorrow_is_fallback, tomorrow_source = (
                await self._async_get_tomorrow_forecast(tomorrow, eur_huf)
            )
        except Exception as err:
            _LOGGER.exception("Independent tomorrow-DAM channel failed unexpectedly: %s", err)
            tomorrow_forecast, tomorrow_date, tomorrow_generated_at = (), None, None
            tomorrow_is_fallback, tomorrow_source = False, None

        # A: current-price channel. Its failure cannot change forecast availability.
        hupx_eur_mwh: float | None = None
        hupx_huf_float: float | None = None
        gross_float: float | None = None
        interval_start: str | None = None
        valid_until: str | None = None
        generated_at: str | None = None
        current_price_source: str | None = None

        try:
            live_eur, interval_start, valid_until, generated_at = await self._async_fetch_hupx()
            hupx_eur_mwh = live_eur
            if eur_huf is not None:
                hupx_huf_float, gross_float = self.gross_d_price(live_eur, eur_huf)
                current_price_source = "price_current"
                await self._async_save_current_source(live_eur, interval_start, valid_until, generated_at)
        except Exception as err:
            if active_forecast is not None:
                point, fallback_valid_until = active_forecast
                hupx_eur_mwh = point.hupx_eur_mwh
                hupx_huf_float = point.hupx_huf_kwh_net
                gross_float = point.d_price_huf_kwh_gross
                interval_start = point.timestamp
                valid_until = fallback_valid_until
                generated_at = forecast_generated_at
                current_price_source = "today_dam_fallback"
                _LOGGER.warning(
                    "Current HUPX unavailable; using independent today-DAM channel (%s): %s",
                    interval_start,
                    err,
                )
            else:
                _LOGGER.warning(
                    "Current HUPX unavailable; DAM channel also has no current-day point. "
                    "Only current-price-dependent entities are unavailable: %s",
                    err,
                )

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
            forecast_current_price_huf_kwh_gross=forecast_current_price,
            current_price_source=current_price_source,
            fx_source=fx_source,
            forecast_source=forecast_source,
            tomorrow_forecast=tomorrow_forecast,
            tomorrow_forecast_date=tomorrow_date,
            tomorrow_forecast_generated_at=tomorrow_generated_at,
            tomorrow_forecast_is_fallback=tomorrow_is_fallback,
            tomorrow_forecast_source=tomorrow_source,
        )
