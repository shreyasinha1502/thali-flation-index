"""Registry of real source endpoints. Endpoints only — no data lives here."""

DATA_GOV_API_BASE = "https://api.data.gov.in/resource"

# Source #1: "Current Daily Price of Various Commodities from Various Markets (Mandi)".
# A rolling current-day snapshot: history exists only if we snapshot it ourselves, daily.
MANDI_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
MANDI_URL = f"{DATA_GOV_API_BASE}/{MANDI_RESOURCE_ID}"
MANDI_SOURCE = "datagov_mandi"
