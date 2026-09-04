from __future__ import annotations

from datetime import timedelta

DOMAIN = "mvm_d_tariff"

ENERGY_CHARTS_CURRENT_URL = "https://api.energy-charts.info/v2/price_current?bzn=HU"
ENERGY_CHARTS_PRICE_URL = "https://api.energy-charts.info/v2/price"
MNB_EXCHANGE_RATE_URL = "https://www.mnb.hu/en/arfolyamok"

DEFAULT_MERCHANT_FEE_HUF_KWH = 13.70
DEFAULT_TRANSMISSION_FEE_HUF_KWH = 4.84
DEFAULT_DISTRIBUTION_FEE_HUF_KWH = 18.56
DEFAULT_VAT_PERCENT = 27.0
DEFAULT_A1_PRICE_HUF_KWH = 70.104
DEFAULT_CHEAP_THRESHOLD_HUF_KWH = 50.0

UPDATE_INTERVAL = timedelta(minutes=5)

CONF_MERCHANT_FEE = "merchant_fee_huf_kwh"
CONF_TRANSMISSION_FEE = "transmission_fee_huf_kwh"
CONF_DISTRIBUTION_FEE = "distribution_fee_huf_kwh"
CONF_VAT_PERCENT = "vat_percent"
CONF_A1_PRICE = "a1_price_huf_kwh"
CONF_CHEAP_THRESHOLD = "cheap_threshold_huf_kwh"
CONF_ENERGY_ENTITY = "energy_entity_id"

SIGNAL_COST_UPDATED = f"{DOMAIN}_cost_updated"
