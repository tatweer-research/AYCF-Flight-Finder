import json
import time

import yaml
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from services.data_manager import data_manager, logger

AIRPORTS_WITH_NAME_CLASHES = ['Basel-Mulhouse-Freiburg']

from stem.control import Controller
import socks
import socket
import requests


def change_tor_ip():
    """Signals Tor to switch to a new exit node (new IP)."""
    try:
        with Controller.from_port(port=9051) as controller:
            controller.authenticate(password="your_password")  # Change to your Tor password
            controller.signal("NEWNYM")
            logger.info("Tor IP changed successfully.")
    except Exception as e:
        logger.error(f"Failed to change Tor IP: {e}")


def set_tor_proxy():
    """Configures the Selenium driver to use the Tor network."""
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
    socket.socket = socks.socksocket
    logger.info("Tor proxy settings applied.")


class ScraperService:
    """Scraps flight data from the WizzAir website"""

    def __init__(self, config_override=None):
        # If user passes a config_override, use it; else fall back to data_manager.config
        if config_override:
            self.config = config_override
        else:
            self.config = data_manager.config
        self.driver = data_manager.driver
        logger.debug("ScraperService initialized with provided driver and config.")
        self.__first_run = None
        self.__browser_ready = False
        self.__use_cache = self.config['data_manager']['use_cache']

    def click_anmelden(self):
        """Clicks the 'Anmelden' button to open the login form."""
        logger.debug("Attempting to locate and click the 'Anmelden' button.")
        anmelden_button = self.driver.find_element(By.XPATH,
                                                   "//button[contains(@class, 'CvoHeader-loginButton') and contains(text(), 'Anmelden')]")
        anmelden_button.click()
        logger.info("'Anmelden' button clicked successfully.")
        time.sleep(self.config['general']['page_loading_time'])

    def fill_in_login_info(self):
        """Fills in login information and submits the form."""
        logger.debug("Filling in login credentials.")
        username_input = self.driver.find_element(By.ID, "username")
        username_input.send_keys(self.config['account']['username'])
        logger.debug("Username entered.")

        password_input = self.driver.find_element(By.ID, "password")
        password_input.send_keys(self.config['account']['password'])
        logger.debug("Password entered.")

        login_button = self.driver.find_element(By.ID, "kc-login")
        login_button.click()
        logger.info("Login form submitted.")
        time.sleep(self.config['general']['page_loading_time'])

    def select_abflugdatum(self, flight_date):
        """Sets the departure date."""
        logger.debug(f"Setting departure date to {flight_date}.")
        try:
            abflugdatum_input = self.driver.find_element(By.ID, "Abflugdatum")
            abflugdatum_input.clear()
            abflugdatum_input.send_keys(flight_date)
            abflugdatum_input.send_keys(u'\ue007')
            logger.info(f"Departure date set to {flight_date}.")
            time.sleep(self.config['general']['action_wait_time'])
        except Exception as e:
            logger.error(f"Failed to set departure date: {e}")
            raise

    def select_start_airport(self, desired_airport):
        """Selects the departure airport."""
        logger.debug(f"Selecting start airport: {desired_airport}.")
        try:
            airport_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'Autocomplete-inputWrapper')]/input"))
            )
            airport_input.clear()
            airport_input.send_keys(desired_airport)

            suggestions_list = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//ul[contains(@class, 'autocomplete-result-list') and not(contains(@style, 'visibility: hidden'))]"))
            )
            first_suggestion = suggestions_list.find_element(By.XPATH, ".//li[1]")
            first_suggestion.click()
            logger.info(f"Start airport selected: {desired_airport}.")
            time.sleep(self.config['general']['action_wait_time'])
        except Exception as e:
            logger.error(f"Failed to select start airport: {e}")
            raise

    def select_destination_airport(self, desired_airport):
        """Selects the destination airport."""
        logger.debug(f"Selecting destination airport: {desired_airport}.")
        try:
            airport_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.visibility_of_element_located
                ((By.XPATH, "//input[@role='combobox' and contains(@id, 'autocomplete-destination')]"))
            )
            airport_input.clear()
            airport_input.send_keys(desired_airport)

            suggestions_list = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//ul[contains(@class, 'autocomplete-result-list') and not(contains(@style, 'visibility: hidden'))]"))
            )
            first_suggestion = suggestions_list.find_element(By.XPATH, ".//li[1]")
            first_suggestion.click()
            logger.info(f"Destination airport selected: {desired_airport}.")
            time.sleep(self.config['general']['action_wait_time'])
        except Exception as e:
            logger.error(f"Failed to select destination airport: {e}")
            raise

    def click_flug_suchen(self):
        """Clicks the 'Flug suchen' button."""
        logger.debug("Locating 'Flug suchen' button to perform a search.")
        flug_suchen_button = self.driver.find_element(By.XPATH,
                                                      "//button[contains(@class, 'button') and contains(text(), 'Flug suchen')]")
        flug_suchen_button.click()
        logger.info("'Flug suchen' button clicked.")
        time.sleep(self.config['general']['action_wait_time'])

    def click_suchen(self):
        """Clicks the 'SUCHEN' button."""
        try:
            logger.debug("Attempting to locate and click the 'SUCHEN' button.")
            suchen_button = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//button[contains(@class, 'ActionButton SearchCombo-submit button ActionButton--primary ActionButton--md') and contains(text(), 'Suchen')]"))
            )
            suchen_button.click()
            logger.info("'SUCHEN' button clicked successfully.")
            time.sleep(self.config['general']['action_wait_time'])
        except Exception as e:
            logger.error(f"Failed to click 'SUCHEN' button: {e}")

    def select_availability_abflugdatum(self, new_date):
        """
        Selects a new date in the date picker identified by the input with ID "Abflugdatum".

        :param new_date: The new date to be entered as a string (format: "YYYY-MM-DD" or as required by the input field).
        """
        try:
            # Locate the date input field using XPath
            date_input = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[@class='CvoDatepicker-input-wrapper']/input[@id='Abflugdatum']"))
            )
            logger.info("Date input located successfully using XPath.")

            # Clear the input text using Keys
            date_input.send_keys(Keys.CONTROL + "a")  # Select all text
            date_input.send_keys(Keys.DELETE)  # Delete the selected text
            logger.info("Existing text cleared successfully.")

            # Enter the new date
            date_input.send_keys(new_date)
            logger.info(f"New date '{new_date}' entered successfully.")

            # Optionally, press Enter to confirm
            date_input.send_keys(Keys.RETURN)
            logger.info("Date change confirmed.")

        except Exception as e:
            logger.error(f"An error occurred while changing the date: {e}")
            raise

    def click_availability_suchen(self):
        """Clicks the 'Suchen' button and waits for the page to load."""
        try:
            logger.debug("Attempting to locate and click the 'Suchen' button.")
            suchen_button = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.element_to_be_clickable((By.XPATH,
                                            "//button[contains(@class, 'CvoSearchFlight-submit button') and contains(text(), 'Suchen')]"))
            )
            suchen_button.click()
            logger.info("'Suchen' button clicked successfully.")

            # Wait for the page to load completely
            WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            logger.info("Page loaded successfully after clicking 'Suchen' button.")
        except Exception as e:
            logger.error(f"Failed to click 'Suchen' button: {e}")

    def select_availability_start_airport(self, desired_airport):
        """
        Sets the start airport for availability search, clears the destination airport, and clears the departure date.

        :param desired_airport: The start airport to select.
        """
        logger.debug(f"Selecting start airport for availability: {desired_airport}.")
        try:
            # Clear the destination airport input field
            logger.debug("Clearing destination airport field before selecting start airport.")
            destination_airport_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//input[@role='combobox' and contains(@id, 'autocomplete-destination')]"))
            )
            destination_airport_input.clear()
            logger.info("Destination airport field cleared.")

            # Clear the departure date input field
            logger.debug("Clearing departure date field before selecting start airport.")
            departure_date_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//div[contains(@class, 'CvoDatepicker-input-wrapper')]//input[@id='Abflugdatum']"))
            )
            departure_date_input.clear()
            logger.info("Departure date field cleared.")

            # Locate the start airport input field
            logger.debug("Locating start airport input field.")
            airport_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//input[@role='combobox' and contains(@id, 'autocomplete-origin')]"))
            )
            airport_input.clear()
            airport_input.send_keys(desired_airport)
            logger.debug(f"Entered '{desired_airport}' into the start airport input field.")

            # Wait for suggestions list to appear
            suggestions_list = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//ul[contains(@class, 'autocomplete-result-list') and not(contains(@style, 'visibility: hidden'))]"))
            )
            first_suggestion = suggestions_list.find_element(By.XPATH, ".//li[1]")
            first_suggestion.click()
            logger.info(f"Start airport selected: {desired_airport}.")
            time.sleep(self.config['general']['action_wait_time'])
        except Exception as e:
            logger.error(f"Failed to select start airport: {e}")

    def select_availability_destination_airport(self, desired_airport):
        """Sets the destination airport for availability search."""
        logger.debug(f"Selecting destination airport for availability: {desired_airport}.")
        try:
            # Locate the destination airport input field
            airport_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//input[@role='combobox' and contains(@id, 'autocomplete-destination')]"))
            )
            airport_input.clear()
            airport_input.send_keys(desired_airport)
            logger.debug(f"Entered '{desired_airport}' into the destination airport input field.")

            # Wait for suggestions list to appear
            suggestions_list = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//ul[contains(@class, 'autocomplete-result-list') and not(contains(@style, 'visibility: hidden'))]"))
            )
            first_suggestion = suggestions_list.find_element(By.XPATH, ".//li[1]")
            first_suggestion.click()
            logger.info(f"Destination airport selected: {desired_airport}.")
            time.sleep(self.config['general']['action_wait_time'])
        except Exception as e:
            logger.error(f"Failed to select destination airport: {e}")

    def list_destinations(self):
        """Lists available destinations."""
        try:
            logger.debug("Fetching destination suggestions.")
            bis_input = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.visibility_of_element_located
                ((By.XPATH, "//input[@role='combobox' and contains(@id, 'autocomplete-destination')]"))
            )
            bis_input.click()
            time.sleep(2)

            suggestions_list = WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH,
                                                "//ul[contains(@class, 'autocomplete-result-list') and not(contains(@style, 'visibility: hidden'))]"))
            )
            suggestions = suggestions_list.find_elements(By.XPATH, ".//li")
            if not suggestions:
                logger.warning("No destination suggestions available.")
                return []

            logger.info("Fetched destination suggestions successfully.")
            suggestions = [suggestion.text[:-6] for suggestion in suggestions]
            logger.debug(json.dumps(suggestions, ensure_ascii=False, indent=4))
            return suggestions

        except Exception as e:
            logger.error(f"Error while fetching destination suggestions: {e}")
            return []

    def read_flight_information(self):
        """Reads flight information and outputs it as JSON."""
        try:
            logger.debug("Waiting for the page to load.")
            WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                lambda driver: self.driver.execute_script("return document.readyState") == "complete"
            )

            logger.debug("Reading flight information.")
            no_results_message = "//h1[contains(text(), 'Leider wurden keine Ergebnisse gefunden')]"
            found_flight_xpath = "//div[contains(@class, 'CvoCollapsibleDirectFlightRow-content')]"

            WebDriverWait(self.driver, self.config['general']['action_wait_time']).until(
                EC.presence_of_element_located((By.XPATH, f"{no_results_message} | {found_flight_xpath}"))
            )

            if self.driver.find_elements(By.XPATH, no_results_message):
                logger.error(
                    json.dumps({"error": "No flights found for the selected date."}, ensure_ascii=False, indent=4))
                return

            flights = self.driver.find_elements(By.XPATH, found_flight_xpath)
            flight_data = []

            for flight in flights:
                flight_data.append({
                    "date": flight.find_element(By.XPATH,
                                                ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-date')]/span").text,
                    "departure": {
                        "time": flight.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-departure')]//span[@class='hour']").text,
                        "timezone": flight.find_element(By.XPATH,
                                                        ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-departure')]//span[@class='timezone']").text,
                        "city": flight.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-departure')]//span[@class='CvoCollapsibleDirectFlightRow-city']").text
                    },
                    "duration": flight.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-citiesSeparator')]//span[contains(@class, 'CvoCollapsibleDirectFlightRow-duration')]").text,
                    "arrival": {
                        "time": flight.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-arrival')]//span[@class='hour']").text,
                        "timezone": flight.find_element(By.XPATH,
                                                        ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-arrival')]//span[@class='timezone']").text,
                        "city": flight.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-arrival')]//span[@class='CvoCollapsibleDirectFlightRow-city']").text
                    },
                    "flight_code": flight.find_element(By.XPATH,
                                                       ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-carrierContainer')]//span[@class='CvoCollapsibleDirectFlightRow-flightCode']").text,
                    "carrier": flight.find_element(By.XPATH,
                                                   ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-carrierContainer')]//p[@class='CvoCollapsibleDirectFlightRow-carrier']").text,
                    "price": flight.find_element(By.XPATH,
                                                 ".//div[contains(@class, 'CvoCollapsibleDirectFlightRow-priceWrapper')]//span[@class='CvoCollapsibleDirectFlightRow-price']").text
                })

            logger.info(f"Successfully fetched flight information")
            logger.info(f"{flight_data[0]['departure']['city']} ({flight_data[0]['departure']['time']}) -> "
                        f"{flight_data[0]['arrival']['city']} ({flight_data[0]['arrival']['time']})")
            logger.debug(json.dumps(flight_data, ensure_ascii=False, indent=4))
            return flight_data if flight_data else None
        except Exception as e:
            logger.error(f"Error reading flight information: {e}")
            logger.info("Rotating IP via Tor and retrying...")

            # Change Tor IP and retry
            change_tor_ip()
            time.sleep(5)  # Give it time to switch IP
            set_tor_proxy()  # Reapply Tor proxy settings

    def setup_browser(self):
        # services/scraper.py
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service
        from selenium.webdriver.edge.options import Options
        from services.data_manager import data_manager, logger

        try:
            driver_path = self.config['general']['driver_path']
            options = Options()
            headless = data_manager.config['general'].get('headless', False)  # Default to False if not specified

            if headless:
                options.add_argument("--headless")  # Ensure headless mode
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")

            service = Service(driver_path)
            self.driver = webdriver.Edge(service=service, options=options)
            self.driver.set_page_load_timeout(60)  # Set a reasonable timeout

            logger.info("Browser initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

        logger.debug("Setting up the browser for scraping.")
        # Open the Wizz Air Multipass German website
        self.driver.get(self.config['account']['wizzair_url'])
        self.driver.maximize_window()
        logger.info("WizzAir All You Can Fly website is opened.")
        time.sleep(self.config['general']['page_loading_time'])

        self.click_anmelden()
        self.fill_in_login_info()
        self.click_flug_suchen()
        logger.info("Website is ready for further operations.")
        self.__browser_ready = True
        self.__first_run = True

    def is_browser_ready(self):
        """Returns the readiness status of the browser."""
        return self.__browser_ready

    def scrape_airport_destinations(self, airport):
        """Gathers the destination information for all airports in the configuration."""
        logger.debug(f"Gathering destination data for {airport}.")
        if data_manager.is_airport_in_database(airport) and self.config['data_manager']['use_cache']:
            logger.debug(f"Airport {airport} is already in the database.")
            return

        try:
            self.select_start_airport(airport)
            destinations = self.list_destinations()
            data_manager.set_airport_destinations(airport, destinations, overwrite=not self.__use_cache)
        except Exception as e:
            logger.error(f"Error while gathering destination data for {airport} - {e}")

    def scrape_airport_destinations_destinations(self, airport):
        """The destinations are added to database and return flights are checked to departure airports."""
        logger.info(f"Gathering destinations for {airport} and the destinations of those destinations.")
        self.scrape_airport_destinations(airport)
        destinations = data_manager.get_airport_destinations(airport)
        for destination in destinations:
            self.scrape_airport_destinations(destination)

    def scrape_departure_airports_destinations_destinations(self):
        """The destinations are added to database and return flights are checked to departure airports."""
        logger.info("Gathering destinations for each departure airport and the destinations of those destinations.")
        airports = self.config['flight_data']['departure_airports']
        for airport in airports:
            self.scrape_airport_destinations_destinations(airport)
        logger.info("All departure airports have been successfully processed and added to the database.")

    def update_airport_database(self):
        """Updates the airport database with the latest data."""
        logger.info("Updating the airport database.")
        logger.info("Gathering destinations for each airport in the database and the destinations of those "
                    "destinations.")
        airports = data_manager.get_all_airports()
        for airport in airports:
            self.scrape_airport_destinations_destinations(airport)
        logger.info("All airports have been successfully processed and added to the database.")

    def check_direct_flight_availability(self, flight, flight_date):
        """Checks if the given flight is available."""
        logger.debug(f"Checking flight availability for {flight} on {flight_date}.")
        if data_manager.is_flight_already_checked(flight, flight_date):
            logger.info(f"Flight {flight['airport']} -> {flight['destination']} on {flight_date} has already been "
                        f"checked.")
            return data_manager.get_checked_flight(flight, flight_date)

        if not self.is_browser_ready():
            self.setup_browser()

        start_time = time.time()
        start_airport = flight['airport']
        destination = flight['destination']
        try:
            if self.__first_run:
                self.select_start_airport(start_airport)
                self.select_destination_airport(destination)
                self.select_abflugdatum(flight_date)
                self.click_suchen()
                self.__first_run = False
                time.sleep(self.config['general']['action_wait_time'])
            else:
                self.select_availability_start_airport(start_airport)
                self.select_availability_destination_airport(destination)
                self.select_availability_abflugdatum(flight_date)
                self.click_availability_suchen()
                time.sleep(self.config['general']['action_wait_time'])
            result = self.read_flight_information()
            data_manager.add_checked_flight(flight, result, flight_date)
            end_time = time.time()
            logger.info(f"Flight availability checked in {end_time - start_time:.2f} seconds.")
            return result
        except Exception as e:
            logger.error(f"Error checking flight availability: {e}")
            return
