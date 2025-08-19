import json
import shutil
import time
import requests
from copy import deepcopy
from pathlib import Path
from datetime import datetime

import schedule

from services import ScraperService, data_manager, FlightFinderService, ReportService, logger
from services.emailer import email_service, roundtrip_kwargs, oneway_kwargs
from services.parallel_scraper import manage_parallel_scraping
from utils import increment_date, get_current_date, is_date_in_range, upload_file_via_ssh, get_iata_code
from services.rest_scraper import (
    get_session_tokens,
    convert_possible_to_request_flights,
    convert_response_to_checked_flight,
    prepare_request_data,
    send_request_with_retries
)


def setup_rest_api(scraper):
    """
    Sets up the browser and prepares API access
    """
    scraper.setup_browser()
    # Check a dummy flight to generate tokens
    finder = FlightFinderService()
    flights = finder.find_possible_one_stop_flights(max_stops=0, save_data=False)
    date = get_current_date()
    # Check a flight availability to generate the needed tokens
    if flights and 'first_flight' in flights[0]:
        scraper.check_direct_flight_availability(flights[0]['first_flight'], date)
    return prepare_request_data()


def round_trip_workflow(mode='classic'):
    """
    Find round-trip flights from departure airports to destination airports.
    
    Args:
        mode (str): Either 'classic' for browser-based checking or 'rest' for API-based checking
    """
    scraper = ScraperService()
    
    try:
        # Adding unknown airports to the database+
        flight_finder = FlightFinderService()
        flight_finder.find_possible_roundtrip_flights_from_departure_airports()
        flights = data_manager.get_possible_flights()

        departure_date = data_manager.config.flight_data.departure_date if data_manager.config.flight_data.departure_date \
            else get_current_date()
        last_date = increment_date(departure_date, 3)

        logger.info('Checking availability for possible flights...')
        
        if mode == 'classic':
            # Classic browser-based mode
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
        elif mode == 'rest':
            # API-based mode
            url, headers, cookies = setup_rest_api(scraper)
            checked_flights = {}
            success_count = 0
            dates = [increment_date(departure_date, i) for i in range(4)]

            for date in dates:
                possible_flights_data = flights.get('possible_flights', [])
                api_flights = convert_possible_to_request_flights(possible_flights_data, date)

                for i, (flight_data, hash_) in enumerate(api_flights):
                    try:
                        response, url, headers, cookies = send_request_with_retries(
                            url, headers, cookies, flight_data, max_retries=3
                        )

                        if response is None:
                            logger.error(f"Request for {flight_data['origin']} → {flight_data['destination']} failed after retries")
                            checked_flights[f'{hash_}-{date}'] = None
                            continue

                        # After a certain number of successes, pause to avoid rate limiting
                        if success_count and success_count % 40 == 0:
                            logger.info("Pausing for 30 seconds to avoid rate limiting ⏳")
                            scraper.driver.quit()
                            time.sleep(30)
                            scraper.setup_browser()
                            url, headers, cookies = prepare_request_data()

                        success_count += 1
                        logger.info(f"Request {flight_data['origin']} → {flight_data['destination']} succeeded ✅ (Total successes: {success_count})")

                        data = response.json()
                        response_flights = data.get("flightsOutbound")

                        if response_flights:
                            for response_flight in response_flights:
                                convert_response_to_checked_flight(response_flight, hash_, date, checked_flights)
                        else:
                            checked_flights[f'{hash_}-{date}'] = None
                    except Exception as e:
                        logger.exception(f"Error during request: {e}")

            # Save checked flights data
            data_manager.add_checked_flights(
                {'checked_flights': checked_flights}
            )
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'classic' or 'rest'.")

        available_flights = flight_finder.find_available_roundtrip_flights()
        data_manager.add_available_flights(available_flights)
        reporter = ReportService()
        reporter.generate_roundtrip_flight_report()
        email_service.send_email(**oneway_kwargs, recipient_emails=[data_manager.config.emailer.recipient])
    except Exception as e:
        logger.exception(f"Failed to complete the round-trip workflow: {e}")
    finally:
        # Close the browser
        time.sleep(5)
        scraper.driver.quit()


def one_way_workflow(mode='classic'):
    """Find one-way flights from departure airports to destination airports. There are no return flights.
    
    Args:
        mode (str): Either 'classic' for browser-based checking or 'rest' for API-based checking
    """
    scraper = ScraperService()
    
    try:
        # Adding unknown airports to the database
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
        
        if mode == 'classic':
            # Classic browser-based mode
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
        elif mode == 'rest':
            # API-based mode
            url, headers, cookies = setup_rest_api(scraper)
            checked_flights = {}
            success_count = 0
            dates = [increment_date(departure_date, i) for i in range(4)]
            
            for date in dates:
                possible_flights_data = flights.get('possible_flights', [])
                api_flights = convert_possible_to_request_flights(possible_flights_data, date)
                
                for i, (flight_data, hash_) in enumerate(api_flights):
                    try:
                        response, url, headers, cookies = send_request_with_retries(
                            url, headers, cookies, flight_data, max_retries=3
                        )
                        
                        if response is None:
                            logger.error(f"Request for {flight_data['origin']} → {flight_data['destination']} failed after retries")
                            checked_flights[f'{hash_}-{date}'] = None
                            continue
                            
                        # After a certain number of successes, pause to avoid rate limiting
                        if success_count and success_count % 40 == 0:
                            wait_time = data_manager.config.general.rate_limit_wait_time
                            logger.info(f"Pausing for {wait_time} seconds to avoid rate limiting ⏳")
                            scraper.driver.quit()
                            time.sleep(wait_time)
                            scraper.setup_browser()
                            url, headers, cookies = prepare_request_data()

                        success_count += 1
                        logger.info(f"Request {flight_data['origin']} → {flight_data['destination']} succeeded ✅ (Total successes: {success_count})")
                        
                        data = response.json()
                        response_flights = data.get("flightsOutbound")
                        
                        if response_flights:
                            for response_flight in response_flights:
                                convert_response_to_checked_flight(response_flight, hash_, date, checked_flights)
                        else:
                            checked_flights[f'{hash_}-{date}'] = None
                    except Exception as e:
                        logger.exception(f"Error during request: {e}")
                        
            # Save checked flights data
            data_manager.add_checked_flights(
                {'checked_flights': checked_flights}
            )
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'classic' or 'rest'.")
        
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
        scraper.driver.quit()


def check_possible_flights_workflow(mode='roundtrip', save_data=True, max_stops=1):
    flight_finder = FlightFinderService()
    if mode == 'roundtrip':
        flight_finder.find_possible_roundtrip_flights_from_departure_airports(save_data=save_data)
    elif mode == 'oneway':
        flight_finder.find_possible_one_stop_flights(save_data=save_data, max_stops=max_stops)


def create_report(mode='roundtrip'):
    reporter = ReportService()
    if mode == 'roundtrip':
        reporter.generate_roundtrip_flight_report()
    elif mode == 'oneway':
        reporter.generate_oneway_flight_report()


def send_email():
    email_service.send_email(**roundtrip_kwargs, recipient_emails=[data_manager.config.emailer.recipient])


def check_available_flights(mode='roundtrip', save_data=True):
    flight_finder = FlightFinderService()
    if mode == 'oneway':
        available_flights = flight_finder.find_available_oneway_flights()
    elif mode == 'roundtrip':
        # flight_finder.find_possible_flights_from_departure_airports()
        available_flights = flight_finder.find_available_roundtrip_flights()
    data_manager.add_available_flights(available_flights, save_data=save_data)


def update_airports_database():
    scraper = ScraperService()
    scraper.setup_browser()
    scraper.update_airport_database()


def schedule_one_way_workflow(mode='classic'):
    try:
        logger.info(f"Setting up one-way workflow schedule with mode: {mode}")
        schedule.every().thursday.at("12:00").do(one_way_workflow, mode=mode)
        schedule.every().thursday.at("15:00").do(one_way_workflow, mode=mode)
    except Exception as e:
        logger.exception(f"Failed to schedule one-way workflow: {e}")
    finally:
        # Close the browser
        time.sleep(5)
        scraper.driver.quit()


def schedule_round_trip_workflow(mode='classic'):
    try:
        logger.info(f"Setting up round-trip workflow schedule with mode: {mode}")
        schedule.every().thursday.at("08:00").do(round_trip_workflow, mode=mode)
        schedule.every().thursday.at("14:00").do(round_trip_workflow, mode=mode)
    except Exception as e:
        logger.exception(f"Failed to schedule round-trip workflow: {e}")


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
                data_manager.load_config(str(file))
                data_manager._setup_edge_driver()

                if data_manager.config.general.mode == 'oneway':
                    one_way_workflow(mode='rest')
                elif data_manager.config.general.mode == 'roundtrip':
                    round_trip_workflow(mode='rest')
                file.unlink()
            except Exception as e:
                file.unlink()
                logger.exception(f"Failed to process job: {file} - {e}")
        time.sleep(10)


def scrape_with_multiprocessing():
    try:
        data_manager.config.flight_data.departure_airports = None
        data_manager.config.flight_data.destination_airports = None
        data_manager.config.data_manager.reset_databases = False
        data_manager.config.data_manager.use_wizz_availability_pdf = True
        data_manager.config.data_manager.checked_flights_path = \
            data_manager.config.data_manager.multi_scraper_output_path
        finder = FlightFinderService()
        finder.find_possible_one_stop_flights(max_stops=0)
        shared_dict = manage_parallel_scraping(data_manager.get_possible_flights()['possible_flights'],
                                               data_manager.config,
                                               max_workers=3)
        # with open('shared_dict.json', 'w', encoding='utf-8') as f:
        #     json.dump(shared_dict, f, ensure_ascii=False, indent=4)
        data_manager.save_data({'checked_flights': shared_dict},
                               data_manager.config.data_manager.multi_scraper_output_path)
        data_manager._reset_databases()

        # Upload the output file to the server
        # upload_file_via_ssh(
        #     local_path=r'C:\Users\Mohammad.Al-zoubi\Documents\projects\AYCF-Flight-Finder\data\multi_scraper_output'
        #                r'.yaml',
        #     remote_path=r'/home/ubuntu/AYCF-Flight-Finder/data/multi_scraper_output.yaml',
        #     hostname='18.153.206.111',
        #     username='ubuntu',
        #     key_path=r'C:\Users\Mohammad.Al-zoubi\.ssh\aws-ec2-new'
        # )

    except Exception as e:
        logger.exception(f"Failed to scrape with multiprocessing: {e}")


if __name__ == '__main__':
    # check_possible_flights_workflow('oneway')
    # one_way_workflow(mode='rest')
    # round_trip_workflow(mode='rest')
    # send_email()
    # schedule_one_way_workflow()
    # update_airports_database()

    # finder = FlightFinderService()
    # finder.find_possible_roundtrip_flights_from_departure_airports()
    # finder.find_possible_one_stop_flights(max_stops=0)
    #
    # checked_flights = data_manager.load_data(data_manager.config.data_manager.checked_flights_path)
    # data_manager.add_checked_flights(checked_flights)
    # check_available_flights('oneway')
    # create_report('oneway')
    # create_report('roundtrip')

    do_pending_jobs()

    # Parallel Processing
    # while True:
    #     scrape_with_multiprocessing()
    #     time.sleep(60)
