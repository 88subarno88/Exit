import sqlite3
import json
import time
from .config import DB_PATH

# Global connection to share across threads
_DB_CONN = None

def _conn():
    global _DB_CONN
    if _DB_CONN is None:
        # check_same_thread=False allows the web app and worker to share 
        # this process without throwing threading errors.
        _DB_CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
        # Ensure the table exists on startup
        _DB_CONN.execute("""
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT,
                fetched_at REAL
            )
        """)
        _DB_CONN.commit()
    return _DB_CONN


def get(key: str, ttl: int):
    """Return (value, age_seconds, is_stale) or (None, None, None) if never cached."""
    cursor = _conn().cursor()
    cursor.execute("SELECT value, fetched_at FROM kv WHERE key = ?", (key,))
    row = cursor.fetchone()
    
    if row is None:
        return (None, None, None)
        
    value_json, fetched_at = row
    age = time.time() - fetched_at
    is_stale = age > ttl
    
    # Return stale rows rather than hiding them — the CALLER decides.
    return (json.loads(value_json), age, is_stale)


def put(key: str, value) -> None:
    """INSERT OR REPLACE INTO kv(key, value, fetched_at) VALUES (?, ?, ?)."""
    now = time.time()
    value_json = json.dumps(value)
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO kv (key, value, fetched_at) VALUES (?, ?, ?)", 
        (key, value_json, now)
    )
    conn.commit()


def cached(key: str, ttl: int, fetch_fn):
    """The pattern the whole project uses.

      fresh hit            -> return it
      stale hit, fetch ok  -> store and return new
      stale hit, fetch dies-> return STALE (this is the line that saves your demo)
      no hit,    fetch dies-> re-raise, nothing else to do
    """
    val, age, is_stale = get(key, ttl)
    
    # Fresh hit -> return it immediately
    if val is not None and not is_stale:
        return val
        
    # Stale hit OR no hit -> attempt to fetch live data
    try:
        new_val = fetch_fn()
        put(key, new_val)
        return new_val
        
    except Exception as e:
        # Fetch dies -> return STALE. This rescues your app when CMC expires.
        if val is not None:
            # (Optional) You can print or log the exception here so you 
            # still see the failure in your server logs.
            print(f"Warning: Upstream fetch failed for {key}, serving {age:.0f}s stale data. Error: {e}")
            return val
            
        # No hit AND fetch dies -> re-raise, nothing else to do
        raise e