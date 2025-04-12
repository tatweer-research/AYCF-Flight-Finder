import time

import requests

from services import FlightFinderService
from services.logger_service import logger
from services.data_manager import data_manager
from services.scraper import ScraperService
from utils import get_current_date


def get_session_tokens(driver):
    # Method 1: Get cookies from browser
    cookies = driver.get_cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    xsrf_token = cookie_dict.get("XSRF-TOKEN")
    laravel_session = cookie_dict.get("laravel_session")

    return xsrf_token, laravel_session, cookie_dict


# Initialize services
scraper = ScraperService()


def setup_website():
    global finder, date, session_uuid, base_url
    scraper.setup_browser()
    finder = FlightFinderService()
    flights = finder.find_possible_one_stop_flights(max_stops=0)
    date = get_current_date()
    # First navigate to the website to get cookies
    # Check flight availability
    scraper.check_direct_flight_availability(flights[0]['first_flight'], date)


setup_website()

xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)
print("XSRF token after visiting sanctum route:", xsrf_token)
print("laravel_session after visiting sanctum route:", laravel_session)

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
    "Referer": "https://multipass.wizzair.com/de/w6/subscriptions/availability/b128d7ef-d1e5-4b7a-aa5e-6e66fc5e4e73",
    "X-XSRF-TOKEN": "eyJpdiI6InlGaE9ERHNFNmhUbFg2YmJxOGhraHc9PSIsInZhbHVlIjoiVFwvTWRrYnUwM0UxRnMwempOY280dE9COGNCUlFNWU1HdmQ3eGNHRTdPbUN6ZGVGSTF3TThwcEhzaWkzeVNqbXhCUjdTYWs0Y2RBdm9HY2xlR2lrVDlBPT0iLCJtYWMiOiI0M2NjNDYyNDhhMjY0ZDA3ZjBiNDFkMzAzMDQxZGM0YWMxZDg0MGI2OGZhNThjZWEyYWIyYTgyY2Q0ODcyM2RiIn0="
}

# 🍪 Cookies
cookies = {
    "XSRF-TOKEN": f"{xsrf_token}",
    "laravel_session": f"{laravel_session}"
}

# ✈️ Payload
payload = {
    "flightType": "OW",
    "origin": "AUH",
    "destination": "AMM",
    "departure": "2025-04-13",
    "arrival": None,
    "intervalSubtype": None
}

print("Making requests with:")
print(f"Headers: {headers}")
print(f"Cookies: {cookies}")

success_count = 0
logger.info('Starting test...')
for i in range(10000):
    try:
        # 📡 POST request
        response = requests.post(url, headers=headers, cookies=cookies, json=payload)

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

    # time.sleep(5)  # Wait between requests to avoid rate limiting

logger.info('Test ended successfully ✅')

# Clean up
data_manager.driver.quit()
