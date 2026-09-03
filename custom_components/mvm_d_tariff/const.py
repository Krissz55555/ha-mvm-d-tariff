from __future__ import annotations

from datetime import timedelta

DOMAIN = "mvm_d_tariff"
PLATFORMS = ["sensor"]

ENERGY_CHARTS_CURRENT_URL = "https://api.energy-charts.info/v2/price_current?bzn=HU"
MNB_EXCHANGE_RATE_URL = "https://www.mnb.hu/en/arfolyamok"

DEFAULT_MERCHANT_FEE_HUF_KWH = 13.70
DEFAULT_TRANSMISSION_FEE_HUF_KWH = 4.84
DEFAULT_DISTRIBUTION_FEE_HUF_KWH = 18.56
DEFAULT_VAT_PERCENT = 27.0

UPDATE_INTERVAL = timedelta(minutes=5)

CONF_MERCHANT_FEE = "merchant_fee_huf_kwh"
CONF_TRANSMISSION_FEE = "transmission_fee_huf_kwh"
CONF_DISTRIBUTION_FEE = "distribution_fee_huf_kwh"
CONF_VAT_PERCENT = "vat_percent"
