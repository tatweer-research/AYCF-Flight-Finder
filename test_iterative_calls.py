import time
import requests
import base64
import json
import re
from services import FlightFinderService
from services.data_manager import data_manager
from services.scraper import ScraperService
from utils import get_current_date


def get_session_tokens(driver):
    # Method 1: Get cookies from browser
    cookies = driver.get_cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    xsrf_token = cookie_dict.get("XSRF-TOKEN")
    laravel_session = cookie_dict.get("laravel_session")

    # Method 2: Try to get XSRF token from meta tag or form
    if not xsrf_token:
        try:
            # Try to find CSRF token in meta tags
            meta_token = driver.find_element_by_xpath("//meta[@name='csrf-token']").get_attribute('content')
            if meta_token:
                xsrf_token = meta_token
                print("Found XSRF token in meta tag:", xsrf_token)
        except:
            print("No CSRF token in meta tags")

        try:
            # Try to find token in any input field
            input_token = driver.find_element_by_xpath("//input[@name='_token']").get_attribute('value')
            if input_token:
                xsrf_token = input_token
                print("Found XSRF token in input field:", xsrf_token)
        except:
            print("No CSRF token in input fields")

    # Method 3: Try to extract it from page source
    if not xsrf_token:
        page_source = driver.page_source
        # Look for CSRF token in JavaScript variables
        csrf_match = re.search(r"csrfToken['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", page_source)
        if csrf_match:
            xsrf_token = csrf_match.group(1)
            print("Found XSRF token in page source:", xsrf_token)

    # Method 4: Try to get token from localStorage
    if not xsrf_token:
        try:
            xsrf_token = driver.execute_script("return localStorage.getItem('XSRF-TOKEN') || window.Laravel?.csrfToken")
            if xsrf_token:
                print("Found XSRF token in localStorage:", xsrf_token)
        except:
            print("Failed to extract token from localStorage")

    # Method 5: If the Laravel session is encrypted, we can try a default token
    if not xsrf_token and laravel_session:
        print("Using fallback XSRF token generation")
        # Laravel often creates XSRF token based on session - try a simple approach
        xsrf_token = "wizzair-csrf-token"  # A placeholder that might work

    print("🔐 Final XSRF-TOKEN:", xsrf_token)
    print("🔐 Final laravel_session:", laravel_session)

    return xsrf_token, laravel_session, cookie_dict


def decode_cookies(driver):
    """Try to decode Laravel cookies for debugging"""
    try:
        # Get document.cookie
        all_cookies = driver.execute_script("return document.cookie")
        print("All cookies from document.cookie:", all_cookies)

        # Specifically look at headers
        headers = driver.execute_script("""
            var req = new XMLHttpRequest();
            req.open('GET', document.location.href, false);
            req.send(null);
            var headers = {};
            var headerString = req.getAllResponseHeaders();
            var headerLines = headerString.split('\\n');
            for (var i = 0; i < headerLines.length; i++) {
                var line = headerLines[i].trim();
                if (line) {
                    var parts = line.split(': ');
                    headers[parts[0]] = parts[1];
                }
            }
            return headers;
        """)
        print("Response headers:", headers)
    except Exception as e:
        print(f"Error decoding cookies: {e}")


# Initialize services
scraper = ScraperService()
scraper.setup_browser()
finder = FlightFinderService()
flights = finder.find_possible_one_stop_flights(max_stops=0)
date = get_current_date()

# First navigate to the website to get cookies
session_uuid = "b128d7ef-d1e5-4b7a-aa5e-6e66fc5e4e73"
base_url = "https://multipass.wizzair.com"
# data_manager.driver.get(f"{base_url}/de/w6/subscriptions/availability/{session_uuid}")

# Check flight availability
scraper.check_direct_flight_availability(flights[0]['first_flight'], date)

# date = '13-04-2025'
# flight = {
#     'hash': '6a92570e0164f103fe1454b8d315af911f1d9367f9258ec4a54426844dd2a350',
#     'airport': 'Abu Dhabi (AUH)',
#     'destination': 'Amman (AMM)'
# }

# scraper.check_direct_flight_availability(flight, date)

# Visit the "sanctum/csrf-cookie" endpoint so Laravel sets XSRF-TOKEN
# data_manager.driver.get(f"{base_url}/sanctum/csrf-cookie")

# Give it a moment to process the response and set cookies

# Now visit the page that requires the token
# data_manager.driver.get(f"{base_url}/de/w6/subscriptions/availability/{session_uuid}")

time.sleep(5)

xsrf_token, laravel_session, cookie_dict = get_session_tokens(scraper.driver)
print("XSRF token after visiting sanctum route:", xsrf_token)
print("laravel_session after visiting sanctum route:", laravel_session)
print()

# # Wait longer for page to fully load
# print("Waiting for page to fully load...")
# time.sleep(5)
#
# # Decode cookies for debugging
# decode_cookies(data_manager.driver)
#
# # Check flight availability
# scraper.check_direct_flight_availability(flights[0]['first_flight'], date)
#
# # Get tokens after page has fully loaded
# xsrf_token, laravel_session, cookie_dict = get_session_tokens(data_manager.driver)

# 🔗 Endpoint URL (UUID must match the session)
url = f"{base_url}/de/w6/subscriptions/json/availability/{session_uuid}"

# 📄 Headers with new X-XSRF-TOKEN
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": base_url,
    "Referer": f"{base_url}/de/w6/subscriptions/availability/{session_uuid}",
}

# Only add X-XSRF-TOKEN if we have it
if xsrf_token:
    headers["X-XSRF-TOKEN"] = xsrf_token

# 🍪 Cookies
cookies = {}
if laravel_session:
    cookies["laravel_session"] = laravel_session
if xsrf_token:
    cookies["XSRF-TOKEN"] = xsrf_token

# Add other cookies that might be needed
for name, value in cookie_dict.items():
    if name not in cookies and value:
        cookies[name] = value

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
for i in range(10000):
    try:
        # 📡 POST request
        response = requests.post(url, headers=headers, cookies=cookies, json=payload)

        # 🧾 Handle response
        if response.status_code == 200:
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

            # If we get consistent failures, try to refresh the session
            if i > 0 and success_count == 0 and i % 3 == 0:
                print("Multiple failures. Refreshing browser session...")
                data_manager.driver.refresh()
                time.sleep(5)

                # Try a different approach - use the Network tab to get the actual request
                try:
                    print("Analyzing network requests to find a working XSRF token...")
                    # Execute a small script in the browser to get the most recent CSRF token
                    network_data = data_manager.driver.execute_script("""
                        return {
                            cookies: document.cookie,
                            token: document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
                            localStorage: Object.entries(localStorage).reduce((obj, [key, val]) => {
                                obj[key] = val;
                                return obj;
                            }, {})
                        }
                    """)
                    print(f"Network analysis results: {network_data}")

                    if network_data.get('token'):
                        xsrf_token = network_data.get('token')
                        headers["X-XSRF-TOKEN"] = xsrf_token
                        cookies["XSRF-TOKEN"] = xsrf_token
                        print(f"Updated XSRF token: {xsrf_token}")
                except Exception as e:
                    print(f"Error analyzing network: {e}")

    except Exception as e:
        print(f"Error during request: {e}")

    time.sleep(5)  # Wait between requests to avoid rate limiting

# Clean up
data_manager.driver.quit()
