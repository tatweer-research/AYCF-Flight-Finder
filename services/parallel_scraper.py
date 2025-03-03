# services/parallel_scraper.py

import multiprocessing
import random
import time
import traceback

from services.data_manager import logger
from services.scraper import ScraperService


def _init_browser(config_dict):
    """Each process initializes its own WebDriver once and reuses it."""
    scraper = ScraperService(config_override=config_dict)
    scraper.setup_browser()
    return scraper


def _check_flight_worker(flight, date, scraper, shared_dict, lock):
    """Worker function that checks flight availability and writes to shared storage."""
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
        logger.error(f"Worker encountered an error: {e}")
        traceback.print_exc()


def _process_worker(flights, dates_to_check, config_dict, shared_dict, lock):
    """
    Each worker process:
    1. Initializes its own WebDriver once.
    2. Checks multiple flights using the same browser instance.
    3. Waits for 3 seconds after every 3 flight checks to avoid rate limiting.
    4. Closes the browser when finished.
    """
    scraper = _init_browser(config_dict)  # Setup browser once per process
    flight_count = 0  # Counter to track number of checks

    try:
        for flight in flights:
            for date in dates_to_check:
                _check_flight_worker(flight, date, scraper, shared_dict, lock)
                flight_count += 1  # Increment check count

                # If the worker has completed 3 flight checks, wait for 3 seconds
                if flight_count % 12 == 0:
                    logger.info(f"Worker is pausing for 3 seconds to avoid rate limiting.")
                    time.sleep(3)

    except Exception as e:
        logger.error(f"Process encountered an error: {e}")
        traceback.print_exc()
    finally:
        if scraper.driver:
            scraper.driver.quit()  # Ensure browser closes properly
            logger.info("Browser closed successfully.")


def manage_parallel_scraping(possible_flights, dates_to_check, config_dict, max_workers=4):
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
                                    args=(chunk, dates_to_check, config_dict, shared_dict, lock))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    return dict(shared_dict)
