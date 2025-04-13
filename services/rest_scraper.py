import time

import requests
from datetime import datetime

from services import FlightFinderService
from services.logger_service import logger
from services.data_manager import data_manager
from services.scraper import ScraperService
from utils import get_current_date, get_iata_code, increment_date


def get_session_tokens(driver):
    # Method 1: Get cookies from browser
    cookies = driver.get_cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    xsrf_token = cookie_dict.get("XSRF-TOKEN")
    laravel_session = cookie_dict.get("laravel_session")
    # logger.info("🔐 XSRF-TOKEN:", xsrf_token)
    # logger.info("🔐 laravel_session:", laravel_session)
    return xsrf_token, laravel_session, cookie_dict


def convert_possible_to_request_flights(possible_flights, departure_date):
    # Convert date from 'DD-MM-YYYY' to 'YYYY-MM-DD'
    formatted_date = datetime.strptime(departure_date, "%d-%m-%Y").strftime("%Y-%m-%d")

    formatted_flights = []
    for entry in possible_flights:
        for key in ["first_flight", "second_flight"]:
            flight = entry.get(key)
            if flight:
                formatted_flights.append(({
                                              "flightType": "OW",
                                              "origin": get_iata_code(flight["airport"]),
                                              "destination": get_iata_code(flight["destination"]),
                                              "departure": formatted_date,
                                              "arrival": None,
                                              "intervalSubtype": None
                                          }, flight['hash']))

    return formatted_flights


def convert_response_to_checked_flight(flight, hash_, date, cached_flights):
    # Build entry key: reference - departure date in DD-MM-YYYY
    entry_key = f"{hash_}-{date}"

    # Build readable date for UI
    readable_date = datetime.strptime(flight["departureDateIso"], "%Y-%m-%d").strftime("%a %d, %B %Y")

    entry = {
        "arrival": {
            "city": flight["arrivalStationText"],
            "time": flight["arrival"],
            "timezone": flight["arrivalOffsetText"]
        },
        "carrier": flight["carrierText"],
        "date": readable_date,
        "departure": {
            "city": flight["departureStationText"],
            "time": flight["departure"],
            "timezone": flight["departureOffsetText"]
        },
        "duration": flight["duration"],
        "flight_code": flight["flightCode"],
        "price": f"{flight['currency']} {flight['totalPrice']}"
    }

    if not checked_flights.get(entry_key):
        cached_flights[entry_key] = [entry]
    else:
        cached_flights[entry_key] += [entry]


# Initialize services
scraper = ScraperService()


def setup_website():
    scraper.setup_browser()
    finder = FlightFinderService()
    flights = finder.find_possible_one_stop_flights(max_stops=0)
    date = get_current_date()

    # Check a dummy flight availability to generate the needed tokens
    scraper.check_direct_flight_availability(flights[0]['first_flight'], date)




def prepare_request_data():
    xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)
    # 🔗 Endpoint URL (UUID must match the session)
    session_uuid = "b128d7ef-d1e5-4b7a-aa5e-6e66fc5e4e73"
    base_url = "https://multipass.wizzair.com"
    url = f"{base_url}/de/w6/subscriptions/json/availability/{session_uuid}"

    # 📄 Headers with new X-XSRF-TOKEN
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://multipass.wizzair.com",
        "Referer": scraper.driver.current_url,
        "X-XSRF-TOKEN": "eyJpdiI6InlGaE9ERHNFNmhUbFg2YmJxOGhraHc9PSIsInZhbHVlIjoiVFwvTWRrYnUwM0UxRnMwempOY280dE9COGNCUlFNWU1HdmQ3eGNHRTdPbUN6ZGVGSTF3TThwcEhzaWkzeVNqbXhCUjdTYWs0Y2RBdm9HY2xlR2lrVDlBPT0iLCJtYWMiOiI0M2NjNDYyNDhhMjY0ZDA3ZjBiNDFkMzAzMDQxZGM0YWMxZDg0MGI2OGZhNThjZWEyYWIyYTgyY2Q0ODcyM2RiIn0="
    }

    # 🍪 Cookies
    cookies = {
        "XSRF-TOKEN": f"{xsrf_token}",
        "laravel_session": f"{laravel_session}"
    }
    return url, headers, cookies


def manage_rest_scraping():
    setup_website()
    url, headers, cookies = prepare_request_data()

    success_count = 0
    dates = [increment_date(get_current_date(), i) for i in range(4)]
    checked_flights = {}
    try:
        for date in dates:
            flights = convert_possible_to_request_flights(data_manager.get_possible_flights()['possible_flights'],
                                                          date)

            for i, (flight, hash_) in enumerate(flights):
                try:
                    # 📡 POST request
                    response = requests.post(url, headers=headers, cookies=cookies, json=flight)

                    if success_count and success_count % 40 == 0:
                        scraper.driver.quit()
                        time.sleep(30)
                        scraper.setup_browser()
                        xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)

                    # 🧾 Handle response
                    if response.status_code == 200 or response.status_code == 400:
                        data = response.json()
                        success_count += 1
                        logger.info(f"Request {flight['origin']} → {flight['destination']} succeeded ✅ (Total "
                                    f"successes: {success_count})")
                        response_flights = data.get("flightsOutbound")

                        if response_flights:
                            for response_flight in response_flights:
                                convert_response_to_checked_flight(response_flight, hash_, date, checked_flights)
                        else:
                            checked_flights[f'{hash_}-{date}'] = None

                    else:
                        print(f"Request #{i} failed ❌ - Status code: {response.status_code}")
                        print(f"Response: {response.text[:200]}...")  # Print first 200 chars
                        scraper.driver.quit()
                        time.sleep(10)
                        scraper.setup_browser()
                        xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)

                except Exception as e:
                    logger.exception(f"Error during request: {e}")

            data_manager.save_data({'checked_flights': checked_flights},
                                   data_manager.config.data_manager.multi_scraper_output_path)
    finally:
        logger.info("Completed availability check for all possible flights ✅")

        # Close the browser
        time.sleep(5)
        scraper.driver.quit()


manage_rest_scraping()
