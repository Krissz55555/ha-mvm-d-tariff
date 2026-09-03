from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
import re

from aiohttp import ClientError, ClientResponseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    MNB_EXCHANGE_RATE_URL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


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


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _extract_price(payload: dict) -> tuple[float, str | None, str | None, str | None]:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("Energy-Charts response contains no data")

    point = data[0]
    values = point.get("values")
    if not isinstance(values, dict) or not values:
        raise ValueError("Energy-Charts response contains no values")

    price = values.get("price")
    if price is None:
        # v2 endpoints are self-describing. For extra resilience, if there is
        # exactly one numeric series, accept it even if the id changes.
        numeric = [v for v in values.values() if isinstance(v, (int, float))]
        if len(numeric) != 1:
            raise ValueError("Cannot identify current price series")
        price = numeric[0]

    attributes = payload.get("attributes") or {}
    valid_until = attributes.get("valid_until")
    return float(price), point.get("timestamp"), valid_until, payload.get("generated_at")


def _parse_mnb_eur_huf_html(html: str) -> float:
    """Extract the official EUR/HUF daily rate from the MNB exchange-rate page."""
    # Keep this dependency-free. The MNB page exposes a normal table row with
    # EUR, Euro, unit 1 and the official daily value. Accept both decimal
    # comma and decimal point and tolerate HTML tags/whitespace between cells.
    compact = re.sub(r"\s+", " ", html)
    match = re.search(
        r">\s*EUR\s*<.*?>\s*(?:Euro|Euró)\s*<.*?>\s*1\s*<.*?>\s*([0-9]+[.,][0-9]+)\s*<",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        # Fallback for minor markup changes: search a bounded window after EUR.
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

    async def _async_update_data(self) -> TariffData:
        hupx_eur_mwh, interval_start, valid_until, generated_at = await self._async_fetch_hupx()
        eur_huf = await self._async_fetch_mnb_eur_huf()

        merchant = Decimal(str(self.entry.options.get(CONF_MERCHANT_FEE, DEFAULT_MERCHANT_FEE_HUF_KWH)))
        transmission = Decimal(str(self.entry.options.get(CONF_TRANSMISSION_FEE, DEFAULT_TRANSMISSION_FEE_HUF_KWH)))
        distribution = Decimal(str(self.entry.options.get(CONF_DISTRIBUTION_FEE, DEFAULT_DISTRIBUTION_FEE_HUF_KWH)))
        vat_pct = Decimal(str(self.entry.options.get(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT)))

        hupx_huf = Decimal(str(hupx_eur_mwh)) * Decimal(str(eur_huf)) / Decimal("1000")
        net = hupx_huf + merchant + transmission + distribution
        gross = net * (Decimal("1") + vat_pct / Decimal("100"))

        return TariffData(
            price_huf_kwh_gross=float(_money(gross)),
            hupx_eur_mwh=hupx_eur_mwh,
            hupx_huf_kwh_net=float(_money(hupx_huf)),
            eur_huf=eur_huf,
            merchant_fee_huf_kwh_net=float(merchant),
            transmission_fee_huf_kwh_net=float(transmission),
            distribution_fee_huf_kwh_net=float(distribution),
            vat_percent=float(vat_pct),
            valid_until=valid_until,
            interval_start=interval_start,
            source_generated_at=generated_at,
        )
