"""
Still a draft! We need to bypass the scraping limitation of the website.
"""

import sys

from services.data_manager import data_manager, logger
from services.emailer import email_service, oneway_kwargs
from services.emailer import roundtrip_kwargs
from services.flight_finder import FlightFinderService
from services.parallel_scraper import manage_parallel_scraping
from services.reporter import ReportService


def round_trip_workflow():
    try:
        logger.info("Starting round-trip workflow (multiprocessing).")

        # 1. Find possible flights
        flight_finder = FlightFinderService()
        flight_finder.find_possible_roundtrip_flights_from_departure_airports()
        possible_flights = data_manager.get_possible_flights()['possible_flights']

        # 2. Prepare some date range to check
        dates_to_check = ["20-04-2025", "21-04-2025"]

        # 3. Launch parallel scraping
        #    We'll pass data_manager.config as the config_dict
        final_checked_results = manage_parallel_scraping(
            possible_flights=possible_flights,
            dates_to_check=dates_to_check,
            config_dict=data_manager.config,
            max_workers=4
        )

        # 4. Merge final_checked_results into your local DataManager
        #    Each key is like "flightHash-date": flightData
        for key, flight_result in final_checked_results.items():
            # The key can be split or stored directly
            flight_hash, date = key.rsplit('-', 1)
            # We must reconstruct the 'flight' dict if necessary or store partial info
            # For simplicity, let's do the DataManager approach:
            mock_flight = {'hash': flight_hash}
            data_manager.add_checked_flight(mock_flight, flight_result, date)

        # 5. Now use the flight finder to see what's available
        available_flights = flight_finder.find_available_roundtrip_flights()
        data_manager.add_available_flights(available_flights)

        # 6. Generate and send the report
        reporter = ReportService()
        reporter.generate_roundtrip_flight_report()
        email_service.send_email(**roundtrip_kwargs,
                                 recipient_emails=[data_manager.config.emailer.recipient])

    except Exception as e:
        logger.error(f"Failed to complete round-trip workflow: {e}")
        sys.exit(1)
    finally:
        # The main driver is typically stored in data_manager, if you want to close it:
        #   data_manager.driver.quit()
        # But keep in mind each process had its own driver, closed individually.
        pass


def one_way_workflow():
    """
    Example of a one-way workflow using multiprocessing parallel scraping.
    """
    try:
        logger.info("Starting one-way workflow (multiprocessing).")

        # 1. Use the FlightFinderService to discover possible flights.
        #    For example, direct flights (max_stops=0) or one-stop (max_stops=1).
        flight_finder = FlightFinderService()
        flight_finder.find_possible_one_stop_flights(max_stops=data_manager.config.flight_data.max_stops)

        # 2. Retrieve the flights that were discovered.
        possible_flights = data_manager.get_possible_flights()['possible_flights']
        if not possible_flights:
            logger.info("No possible flights found for one-way workflow.")
            return

        # 3. Define some date(s) to check for availability.
        #    You can pull these from configuration or user input if desired.
        dates_to_check = ["22-02-2025", "23-02-2025", "24-02-2025"]

        # 4. Launch parallel scraping to check each flight on each date.
        #    This returns a dictionary mapping "flightHash-date" -> scraping result.
        final_checked_results = manage_parallel_scraping(
            possible_flights=possible_flights,
            dates_to_check=dates_to_check,
            config_dict=data_manager.config,
            max_workers=4  # Adjust concurrency as needed
        )

        # 5. Merge the final results into data_manager so that we can filter them
        #    using existing flight_finder methods (like find_available_flights).
        for key, flight_result in final_checked_results.items():
            # The key is something like "abc123hash-25-06-2025"
            flight_hash, date = key.rsplit('-', 1)
            # Create a minimal flight dict for data_manager to store
            mock_flight = {'hash': flight_hash}
            data_manager.add_checked_flight(mock_flight, flight_result, date)

        # 6. Filter the available flights now that we've added the checks.
        possible_flights = data_manager.get_possible_flights()
        checked_flights = data_manager.get_checked_flights()
        available_flights = flight_finder.find_available_oneway_flights(possible_flights, checked_flights)
        data_manager.add_available_flights(available_flights)

        # 7. Generate the one-way flight report.
        reporter = ReportService()
        reporter.generate_oneway_flight_report()

        # 8. Send the report via email (PDF attachment).
        email_service.send_email(
            **oneway_kwargs,
            recipient_emails=[data_manager.config.emailer.recipient]
        )

    except Exception as e:
        logger.error(f"Failed to complete the one-way workflow: {e}")
        sys.exit(1)
    finally:
        # Each process spawns its own browser, so there's no global browser to close here.
        # If you do open a single driver in the main process, you can close it:
        #   data_manager.driver.quit()
        pass


if __name__ == '__main__':
    one_way_workflow()
