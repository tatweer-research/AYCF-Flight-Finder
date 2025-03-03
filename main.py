import shutil
import time
from copy import deepcopy

import schedule
from pathlib import Path

from services import ScraperService, data_manager, FlightFinderService, ReportService
from services.data_manager import logger
from services.emailer import email_service, roundtrip_kwargs, oneway_kwargs
from utils import increment_date, get_current_date, is_date_in_range
from services.parallel_scraper import manage_parallel_scraping


def round_trip_workflow():
    try:
        # Adding unknown airports to the database
        scraper = ScraperService()

        flight_finder = FlightFinderService()
        flight_finder.find_possible_roundtrip_flights_from_departure_airports()
        flights = data_manager.get_possible_flights()

        departure_date = data_manager.config.flight_data.departure_date if data_manager.config.flight_data.departure_date \
            else get_current_date()
        last_date = increment_date(departure_date, 3)

        logger.info('Checking availability for possible flights...')
        scraper.setup_browser()

        for flight in flights['possible_flights']:
            for i in range(4):
                if i == 0:
                    date = deepcopy(departure_date)
                else:
                    date = increment_date(date)
                if not is_date_in_range(date, departure_date, last_date):
                    break

                outward_result = scraper.check_direct_flight_availability(flight['outward_flight'],
                                                                          date)
                if not outward_result:
                    continue

                for j in range(4):
                    if j > 0:
                        date = increment_date(date)
                    if not is_date_in_range(date, departure_date, last_date):
                        break
                    for outward_flight in outward_result:
                        return_result = scraper.check_direct_flight_availability(flight['return_flight'],
                                                                                 date)
        available_flights = flight_finder.find_available_roundtrip_flights()
        data_manager.add_available_flights(available_flights)
        reporter = ReportService()
        reporter.generate_roundtrip_flight_report()
        email_service.send_email(**oneway_kwargs, recipient_emails=[data_manager.config.emailer.recipient])
    except Exception as e:
        logger.error(f"Failed to complete the round-trip workflow: {e}")
    finally:
        # Close the browser
        time.sleep(5)
        data_manager.driver.quit()


def one_way_workflow():
    """Find one-way flights from departure airports to destination airports. There are no return flights."""
    try:
        # Adding unknown airports to the database
        scraper = ScraperService()

        flight_finder = FlightFinderService()
        flight_finder.find_possible_one_stop_flights(max_stops=data_manager.config.flight_data.max_stops)
        flights = data_manager.get_possible_flights()

        departure_date = data_manager.config.flight_data.departure_date if data_manager.config.flight_data.departure_date \
            else get_current_date()
        last_date = data_manager.config.flight_data.departure_date if data_manager.config.flight_data.departure_date \
            else increment_date(departure_date, 3)
        last_date_one_stop = increment_date(deepcopy(last_date), 1) if data_manager.config.flight_data.departure_date \
            else last_date

        logger.info('Checking availability for possible flights...')
        scraper.setup_browser()

        for flight in flights['possible_flights']:
            for i in range(4):
                if i == 0:
                    date = deepcopy(departure_date)
                else:
                    date = increment_date(date)
                if not is_date_in_range(date, departure_date, last_date):
                    break

                first_result = scraper.check_direct_flight_availability(flight['first_flight'],
                                                                        date)
                if not first_result:
                    continue
                for first_flight in first_result:
                    if not flight['second_flight']:
                        continue
                    for j in range(4):
                        if j > 0:
                            date = increment_date(date)
                        if not is_date_in_range(date, departure_date, last_date_one_stop):
                            break
                        second_result = scraper.check_direct_flight_availability(flight['second_flight'],
                                                                                 date)
        available_flights = flight_finder.find_available_oneway_flights()
        data_manager.add_available_flights(available_flights)
        reporter = ReportService()
        reporter.generate_oneway_flight_report()
        email_service.send_email(**oneway_kwargs, recipient_emails=[data_manager.config.emailer.recipient])
    except Exception as e:
        logger.exception(f"Failed to complete the one-way workflow: {e}")
    finally:
        # Close the browser
        time.sleep(5)
        data_manager.driver.quit()


def check_possible_flights_workflow(mode='roundtrip'):
    flight_finder = FlightFinderService()
    if mode == 'roundtrip':
        flight_finder.find_possible_roundtrip_flights_from_departure_airports()
    elif mode == 'oneway':
        flight_finder.find_possible_one_stop_flights()


def create_report(mode='roundtrip'):
    reporter = ReportService()
    if mode == 'roundtrip':
        reporter.generate_roundtrip_flight_report()
    elif mode == 'oneway':
        reporter.generate_oneway_flight_report()


def send_email():
    email_service.send_email(**roundtrip_kwargs, recipient_emails=[data_manager.config.emailer.recipient])


def check_available_flights():
    flight_finder = FlightFinderService()
    available_flights = flight_finder.find_available_oneway_flights()
    # flight_finder.find_possible_flights_from_departure_airports()
    # available_flights = flight_finder.find_available_roundtrip_flights()
    data_manager.add_available_flights(available_flights)


def update_airports_database():
    scraper = ScraperService()
    scraper.setup_browser()
    scraper.update_airport_database()


def schedule_one_way_workflow():
    schedule.every().day.at("07:00").do(one_way_workflow)

    while True:
        schedule.run_pending()
        time.sleep(5)


def schedule_round_trip_workflow():
    schedule.every().day.at("06:00").do(round_trip_workflow)

    while True:
        schedule.run_pending()
        time.sleep(5)


def do_pending_jobs():
    logger.info('Checking for pending jobs...')
    while True:
        directory = Path('jobs')
        yaml_files = list(directory.rglob('*.yaml')) + list(directory.rglob('*.yml'))
        for file in yaml_files:
            try:
                shutil.copy(file, 'cache')
                # Do not change the order of the following lines
                data_manager._reset_databases()
                data_manager.config = data_manager.load_data(str(file))
                data_manager._setup_edge_driver()

                if data_manager.config.general.mode == 'oneway':
                    one_way_workflow()
                elif data_manager.config.general.mode == 'roundtrip':
                    round_trip_workflow()
                file.unlink()
            except Exception as e:
                file.unlink()
                logger.error(f"Failed to process job: {file} - {e}")
        time.sleep(10)


if __name__ == '__main__':
    # create_report('oneway')
    # create_report('roundtrip')
    # check_possible_flights_workflow('oneway')
    one_way_workflow()
    # round_trip_workflow()
    # send_email()
    # schedule_one_way_workflow()
    # update_airports_database()
    # finder = FlightFinderService()
    # finder.find_one_stop_flights(max_stops=0)
    # checked_flights = data_manager.load_data(config.data_manager.checked_flights_path)
    # data_manager.add_checked_flights(checked_flights)
    # check_available_flights()

    # do_pending_jobs()
    # manage_parallel_scraping()
