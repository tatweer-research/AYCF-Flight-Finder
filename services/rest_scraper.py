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
    return xsrf_token, laravel_session, cookie_dict


def convert_possible_to_request_flights(possible_flights, departure_date):
    formatted_date = datetime.strptime(departure_date, "%d-%m-%Y").strftime("%Y-%m-%d")
    formatted_flights = []
    for entry in possible_flights:
        for key in ["first_flight", "second_flight"]:
            flight = entry.get(key)
            if flight:
                formatted_flights.append((
                    {
                        "flightType": "OW",
                        "origin": get_iata_code(flight["airport"]),
                        "destination": get_iata_code(flight["destination"]),
                        "departure": formatted_date,
                        "arrival": None,
                        "intervalSubtype": None
                    },
                    flight['hash']
                ))
    return formatted_flights


def convert_response_to_checked_flight(flight, hash_, date, checked_flights):
    # Convert 12h time to 24h format
    def to_24h(time_str):
        return datetime.strptime(time_str.strip(), "%I:%M %p").strftime("%H:%M")

    # Build entry key: hash - departure date in DD-MM-YYYY
    entry_key = f"{hash_}-{date}"
    # Build readable date for UI
    readable_date = datetime.strptime(flight["departureDateIso"], "%Y-%m-%d").strftime("%a %d, %B %Y")
    entry = {
        "arrival": {
            "city": flight["arrivalStationText"],
            "time": to_24h(flight["arrival"]),
            "timezone": flight["arrivalOffsetText"]
        },
        "carrier": flight["carrierText"],
        "date": readable_date,
        "departure": {
            "city": flight["departureStationText"],
            "time": to_24h(flight["departure"]),
            "timezone": flight["departureOffsetText"]
        },
        "duration": flight["duration"],
        "flight_code": flight["flightCode"],
        "price": f"{flight['currency']} {flight['totalPrice']}"
    }
    if not checked_flights.get(entry_key):
        checked_flights[entry_key] = [entry]
    else:
        checked_flights[entry_key].append(entry)


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
    xsrf_token, laravel_session, _ = get_session_tokens(scraper.driver)
    # 🔗 Endpoint URL (UUID must match the session)
    session_uuid = data_manager.config.scraper.session_uuid
    base_url = "https://multipass.wizzair.com"
    url = f"{base_url}/de/w6/subscriptions/json/availability/{session_uuid}"
    # 📄 Headers with new X-XSRF-TOKEN
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://multipass.wizzair.com",
        "Referer": scraper.driver.current_url,
        "X-XSRF-TOKEN": data_manager.config.scraper.xsrf_token
    }
    # 🍪 Cookies
    cookies = {
        "XSRF-TOKEN": f"{xsrf_token}",
        "laravel_session": f"{laravel_session}"
    }
    return url, headers, cookies


def send_request_with_retries(url, headers, cookies, flight, max_retries=3):
    """
    Attempts to send a POST request for the given flight. In case of failure or an unexpected
    status code, closes the browser, sleeps for 10 seconds, reinitializes, and retries.
    Returns a tuple (response, url, headers, cookies). If all attempts fail, response is None.
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, cookies=cookies, json=flight)
            if response.status_code in [200, 400]:
                return response, url, headers, cookies
            else:
                logger.warning(f"Attempt {attempt}: Received status code {response.status_code}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt}: Exception during request: {e}")
        # Close the browser, sleep and reinitialize before retrying
        scraper.driver.quit()
        time.sleep(10)
        scraper.setup_browser()
        url, headers, cookies = prepare_request_data()
    return None, url, headers, cookies


def manage_rest_scraping():
    logger.info("Started rest scraping ✅")
    setup_website()
    url, headers, cookies = prepare_request_data()
    success_count = 0
    dates = [increment_date(get_current_date(), i) for i in range(4)]
    checked_flights = {}
    try:
        for date in dates:
            possible_flights_data = data_manager.get_possible_flights().get('possible_flights', [])
            flights = convert_possible_to_request_flights(possible_flights_data, date)
            for i, (flight, hash_) in enumerate(flights):
                try:
                    response, url, headers, cookies = send_request_with_retries(url, headers, cookies, flight, max_retries=3)
                    if response is None:
                        logger.error(f"Request for {flight['origin']} → {flight['destination']} failed after retries")
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
                    logger.info(f"Request {flight['origin']} → {flight['destination']} succeeded ✅ (Total successes: {success_count})")
                    data = response.json()
                    response_flights = data.get("flightsOutbound")
                    if response_flights:
                        for response_flight in response_flights:
                            convert_response_to_checked_flight(response_flight, hash_, date, checked_flights)
                    else:
                        checked_flights[f'{hash_}-{date}'] = None
                except Exception as e:
                    logger.exception(f"Error during request: {e}")
        data_manager.save_data({'checked_flights': checked_flights},
                               data_manager.config.data_manager.multi_scraper_output_path)

    finally:
        logger.info("Completed availability check for all possible flights ✅")
        time.sleep(5)
        scraper.driver.quit()
        data_manager._reset_databases()

if __name__ == '__main__':
    while True:
        try:
            manage_rest_scraping()
            time.sleep(30)
        except Exception as e:
            logger.exception(f"Error during scraping: {e}")
