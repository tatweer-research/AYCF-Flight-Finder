import os
import yaml
import datetime
from threading import Lock

from services.logger_service import logger

# Global lock to make YAML writes thread-safe
yaml_write_lock = Lock()


def init_db(yaml_path):
    """
    Ensures that the YAML file exists and starts with:

        usage_logs:

    so that we can append log entries to it.
    """
    if not os.path.exists(yaml_path):
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write("usage_logs:\n")
        logger.info('Finish setting up YAML DB')


def log_usage(tab, stops, departure_airports, arrival_airports, trip_type, yaml_path):
    """
    Appends a single usage log entry to the YAML file, without re-writing the whole file.
    """
    try:
        # Convert lists to comma-separated strings (if not already strings)
        if isinstance(departure_airports, list):
            departure_airports = ", ".join(departure_airports)
        if isinstance(arrival_airports, list):
            arrival_airports = ", ".join(arrival_airports)

        # Prepare a chunk of valid YAML that adds one item under '- '
        # Indent each subsequent line by at least 2 spaces for valid YAML
        log_entry = (
            f"- timestamp: {datetime.datetime.now(datetime.UTC).isoformat()}\n"
            f"  tab: {tab}\n"
            f"  stops: {stops}\n"
            f"  departure_airports: {departure_airports}\n"
            f"  arrival_airports: {arrival_airports}\n"
            f"  trip_type: {trip_type}\n"
        )

        # Acquire the lock so no two threads append at the same time
        with yaml_write_lock:
            # Append this log entry at the end of the file
            with open(yaml_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
                f.write("\n")  # Blank line after each item for readability

        logger.debug('Saved statistics via YAML append')
    except Exception as e:
        logger.exception(f'Error while saving statistics. Original error: {e}')


def fetch_all_logs(yaml_path):
    """
    Reads the entire YAML file and returns the list under 'usage_logs'.
    """
    try:
        with yaml_write_lock:
            if not os.path.exists(yaml_path):
                # If the file doesn't exist, nothing to return
                return []

            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

        # If there's no data or the structure doesn't have a usage_logs key, return empty
        if not data or 'usage_logs' not in data:
            return []
        return data['usage_logs']

    except Exception as e:
        logger.exception(f'Error while reading logs. Original error: {e}')
        return []
