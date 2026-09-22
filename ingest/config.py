from dotenv import load_dotenv
import os

load_dotenv()

CMC_API_KEY = os.environ["CMC_API_KEY"]   # KeyError on startup is GOOD here —
                                          # fail loudly rather than 401 later
BASE_URL    = os.getenv("CMC_BASE_URL", "https://pro-api.coinmarketcap.com")
DB_PATH     = os.getenv("DB_PATH", "data/exit.db")
UNIVERSE    = int(os.getenv("UNIVERSE_SIZE", "500"))

# Auth header CMC expects — see
# https://coinmarketcap.com/api/documentation/v1/#section/Authentication
HEADERS = {"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"}

# Cache TTLs in seconds. Tune these AFTER you know your credit burn.
TTL = {
    "listings":     3600,
    "market_pairs": 3600,
    "quotes":        900,
    "info":        86400,
    "map":        604800,   # ids never change — cache this almost forever
}
