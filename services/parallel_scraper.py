import multiprocessing
import os
import random
import time
import traceback
from copy import deepcopy

from services.data_manager import logger, data_manager
from services.scraper import ScraperService
from utils import get_current_date, increment_date, is_date_in_range


def _init_browser(config_dict):
    """Each process initializes its own WebDriver once and reuses it."""
    scraper = ScraperService(config_override=config_dict)
    scraper.setup_browser()
    return scraper


def _check_flight_worker(flight, date, scraper, shared_dict, lock):
    """Worker function that checks flight availability and writes to shared storage.
    Only suitable for direct flights. In case of multi-leg flights, the first leg is checked.
    TODO 1: Update the function to handle one-stop and roundtrip flights if necessary. Currently, there is
     no need for that as we intend to only use for the large direct flight only database.
    """
    try:
        # Introduce a small random delay to avoid being blocked by the server
        time.sleep(random.uniform(1, 2))

        flight_segment = flight.get('outward_flight') or flight.get('first_flight')
        if not flight_segment:
            return

        # Perform the scraping check
        result = scraper.check_direct_flight_availability(flight_segment, date)

        if result:
            with lock:
                key = f"{flight_segment['hash']}-{date}"
                shared_dict[key] = result

    except Exception as e:
        logger.error(f"PID-{os.getpid()}: Worker encountered an error: {e}")
        traceback.print_exc()


def _process_worker(flights, config_dict, shared_dict, lock):
    """
    Each worker process:
    1. Initializes its own WebDriver once.
    2. Checks multiple flights using the same browser instance.
    3. Waits for 3 seconds after every 3 flight checks to avoid rate limiting.
    4. Closes the browser when finished.
    Automatically determines dates for the next three days.
    """
    scraper = _init_browser(config_dict)  # Setup browser once per process
    flight_count = 0  # Counter to track number of checks

    departure_date = get_current_date()
    last_date = increment_date(departure_date, 3)

    try:
        for flight in flights:
            date = deepcopy(departure_date)
            for _ in range(4):  # Checking up to 4 consecutive days
                if not is_date_in_range(date, departure_date, last_date):
                    break
                _check_flight_worker(flight, date, scraper, shared_dict, lock)
                flight_count += 1  # Increment check count
                date = increment_date(date)

                # If the worker has completed 9 flight checks, wait for 30 seconds
                if flight_count % 9 == 0:
                    logger.info(f"PID-{os.getpid()}: Worker is pausing for 30 seconds to avoid rate limiting.")
                    time.sleep(data_manager.config.general.rate_limit_wait_time)

    except Exception as e:
        logger.error(f"Process encountered an error: {e}")
        traceback.print_exc()
    finally:
        if scraper.driver:
            scraper.driver.quit()  # Ensure browser closes properly
            logger.info("Browser closed successfully.")


def manage_parallel_scraping(possible_flights, config_dict, max_workers=4):
    """
    Orchestrates parallel scraping with multiprocessing.
    Each process:
    - Creates **one** WebDriver instance.
    - Checks multiple flights.
    - Pauses every 3 checks for 3 seconds to avoid rate limiting.
    - Closes the WebDriver before exiting.
    """
    manager = multiprocessing.Manager()
    shared_dict = manager.dict()
    lock = manager.Lock()

    # Split flights across processes
    chunk_size = max(1, len(possible_flights) // max_workers)
    flight_chunks = [possible_flights[i:i + chunk_size] for i in range(0, len(possible_flights), chunk_size)]

    processes = []
    for chunk in flight_chunks:
        p = multiprocessing.Process(target=_process_worker,
                                    args=(chunk, config_dict, shared_dict, lock))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    return dict(shared_dict)
