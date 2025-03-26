import sqlite3
from datetime import datetime

from services.logger_service import logger


def init_db(db_path):
    """Create or open a database file and ensure the usage_logs table exists."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            tab TEXT,
            stops TEXT,
            departure_airports TEXT,
            arrival_airports TEXT,
            trip_type TEXT
        )
    """)
    conn.commit()
    logger.info('Finish setting up SQLite DB')
    return conn


def log_usage(tab, stops, departure_airports, arrival_airports, trip_type, db_path):
    """Insert a row in the usage_logs table."""
    # Convert lists to comma-separated strings (if not already strings)
    try:
        if isinstance(departure_airports, list):
            departure_airports = ", ".join(departure_airports)
        if isinstance(arrival_airports, list):
            arrival_airports = ", ".join(arrival_airports)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO usage_logs (timestamp, tab, stops, departure_airports, arrival_airports, trip_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),  # e.g. 2025-03-26T15:30:12.345678
            tab,
            stops,
            departure_airports,
            arrival_airports,
            trip_type
        ))

        conn.commit()
        conn.close()
        logger.debug('Saved statistics')
    except Exception as e:
        logger.exception(f'Error while saving statistics. Original error: {e}')


def fetch_all_logs(db_path):
    """Fetch all rows (for debugging/inspection)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM usage_logs ORDER BY id DESC")
    rows = cursor.fetchall()

    conn.close()
    return rows
