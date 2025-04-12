import time

import requests
from datetime import datetime

from services import FlightFinderService
from services.logger_service import logger
from services.data_manager import data_manager
from services.scraper import ScraperService
from utils import get_current_date, get_iata_code


def get_session_tokens(driver):
    # Method 1: Get cookies from browser
    cookies = driver.get_cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    xsrf_token = cookie_dict.get("XSRF-TOKEN")
    laravel_session = cookie_dict.get("laravel_session")
    logger.info("🔐 XSRF-TOKEN:", xsrf_token)
    logger.info("🔐 laravel_session:", laravel_session)
    return xsrf_token, laravel_session, cookie_dict


def convert_flights(possible_flights, departure_date):
    # Convert date from 'DD-MM-YYYY' to 'YYYY-MM-DD'
    formatted_date = datetime.strptime(departure_date, "%d-%m-%Y").strftime("%Y-%m-%d")

    formatted_flights = []
    for entry in possible_flights:
        for key in ["first_flight", "second_flight"]:
            flight = entry.get(key)
            if flight:
                formatted_flights.append({
                    "flightType": "OW",
                    "origin": get_iata_code(flight["airport"]),
                    "destination": get_iata_code(flight["destination"]),
                    "departure": formatted_date,
                    "arrival": None,
                    "intervalSubtype": None
                })

    return formatted_flights


# Initialize services
scraper = ScraperService()


def setup_website():
    scraper.setup_browser()
    finder = FlightFinderService()
    flights = finder.find_possible_one_stop_flights(max_stops=0)
    date = get_current_date()

    # Check a dummy flight availability to generate the needed tokens
    scraper.check_direct_flight_availability(flights[0]['first_flight'], date)


setup_website()


def prepare_request_data():
    global xsrf_token, laravel_session, cookie_dict, url, headers, cookies, payload
    xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)
    # 🔗 Endpoint URL (UUID must match the session)
    session_uuid = "b128d7ef-d1e5-4b7a-aa5e-6e66fc5e4e73"
    base_url = "https://multipass.wizzair.com"
    url = scraper.driver.current_url
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


url, headers, cookies = prepare_request_data()

flights = convert_flights(data_manager.get_possible_flights(), get_current_date())

success_count = 0
for i, flight in enumerate(flights):
    try:
        # 📡 POST request
        response = requests.post(url, headers=headers, cookies=cookies, json=flight)

        if success_count == 1500:
            break

        if success_count and success_count % 40 == 0:
            scraper.driver.quit()
            time.sleep(30)
            scraper.setup_browser()
            xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)

        # 🧾 Handle response
        if response.status_code == 200 or response.status_code == 400:
            data = response.json()
            success_count += 1
            print(f"Request #{i} succeeded ✅ (Total successes: {success_count})")

            # Print the first flight info on first success
            if success_count == 1 and data.get("flightsOutbound"):
                flight = data.get("flightsOutbound")[0]
                print(
                    f"First flight: {flight['flightCode']} from {flight['departureStationText']} to {flight['arrivalStationText']}")
                print(f"Price: {flight['price']} {flight['currency']}")

        else:
            print(f"Request #{i} failed ❌ - Status code: {response.status_code}")
            print(f"Response: {response.text[:200]}...")  # Print first 200 chars
            scraper.driver.quit()
            time.sleep(10)
            scraper.setup_browser()
            xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)

    except Exception as e:
        print(f"Error during request: {e}")

    finally:
        # Close the browser
        time.sleep(5)
        scraper.driver.quit()
