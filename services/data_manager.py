import logging
import os
import re
import threading
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yaml
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options

from services.wizzair_flight_connector_parser import WizzAirFlightConnectionParser
from settings import system_config

logger = logging.getLogger(__name__)


def split_words(name):
    """
    Split the given airport name into a list of lowercase words (no punctuation).
    E.g. "Abu Dhabi" -> ["abu", "dhabi"]
         "Basel/Mulhouse" -> ["basel", "mulhouse"]
    """
    return re.findall(r"[A-Za-z0-9]+", name.lower())


def is_complete_word_match(json_airport_name, csv_airport_name):
    """
    Checks if all words of 'json_airport_name' appear as whole words in 'csv_airport_name'.
    """
    # Split both into lists of words (lowercase).
    json_words = split_words(json_airport_name)
    csv_words  = split_words(csv_airport_name)

    # We want every word from json_airport_name to appear in the CSV name's list of words:
    return all(word in csv_words for word in json_words)


def find_possible_csv_matches(airport_name, df_csv):
    """
    Returns all rows of df_csv where 'airport' is a *complete-word match* for airport_name.
    If nothing found, returns an empty DataFrame.
    """
    matched_rows = df_csv[df_csv["airport"].apply(
        lambda x: is_complete_word_match(airport_name, x)
    )]
    return matched_rows


def parse_airport_line(line):
    """
    Given something like:
       'Aberdeen (ABZ):'
    return ('Aberdeen', 'ABZ')
    """
    # Regex to match:   Some Name (IATA):
    match = re.match(r"^(.*?) \((.*?)\):", line.strip())
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


def parse_destination_line(line):
    """
    Given something like:
       '- Danzig (GDN)'
    return ('Danzig', 'GDN')
    """
    match = re.match(r"^- (.*?) \((.*?)\)$", line.strip())
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


class IndentedDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(IndentedDumper, self).increase_indent(flow, False)


class DataManager:
    def __init__(self):
        self._write_lock = threading.Lock()

        # Load the YAML file

        logger.info('Configuration file loaded successfully')

        # Get the new airport destinations
        self.flight_connection_parser = WizzAirFlightConnectionParser(system_config.data_manager.flight_data_path)
        self.__airports_destinations = {}

        # Read the airport_iata_icao_path CSV into a DataFrame
        self.__orig_df_airport = None
        self.__df_airport = None
        self._setup_df_airports()

        self.driver = None
        self._reset_databases()
        if system_config.scraper.initialize_driver:
            self._setup_edge_driver()

    def _setup_df_airports(self):
        self.__orig_df_airport = pd.read_csv(system_config.data_manager.airport_iata_icao_path)
        self.__orig_df_airport = self.__orig_df_airport[self.__orig_df_airport['iata'].notna() & (self.__orig_df_airport['iata'] != '')]
        self.__orig_df_airport = self.__orig_df_airport.drop_duplicates(subset='iata', keep='first')
        # Create a dictionary mapping IATA codes to (latitude, longitude) tuples
        airport_coords = self.__orig_df_airport.set_index('iata')[['latitude', 'longitude']].to_dict(orient='index')
        self.__orig_df_airport["airport_coords"] = self.__orig_df_airport["iata"].map(
            lambda iata: (
                airport_coords[iata]["latitude"], airport_coords[iata]["longitude"]) if iata in airport_coords else None
        )

    # name_to_iata = {unidecode.unidecode(airport_name): iata for airport_name, iata in name_to_iata.items()}

    def _update_connections_in_df_airports(self):
        # Get possible IATA codes for airports in flight_connection_parser
        with open(system_config.data_manager.airport_name_special_cases_path, "r", encoding="utf-8") as f:
            special_name_map = yaml.safe_load(f)

        self.__airports_destinations = {}
        airport_to_iata = {}  # dictionary mapping e.g. {"Aalesund": [ "AES" ], "Aberdeen": [ "ABZ" ], ...}
        connections_dict = self.flight_connection_parser.get_flight_data()['connections']

        # Collect all departure & arrival names in one set
        all_airport_names = set()
        for dep_name, arr_list in connections_dict.items():
            all_airport_names.add(dep_name)  # the departure airport
            all_airport_names.update(arr_list)  # all arrival airports

        for json_airport in all_airport_names:
            matched_df = find_possible_csv_matches(json_airport, self.__orig_df_airport)

            # If no match, check special cases
            if matched_df.empty and json_airport in special_name_map:
                corrected_name = special_name_map[json_airport]
                matched_df = find_possible_csv_matches(corrected_name, self.__orig_df_airport)

            # If still none, raise an exception
            if matched_df.empty:
                raise ValueError(f"No CSV match found for '{json_airport}' (even after special cases).")

            # Gather unique IATA codes
            iata_codes = matched_df["iata"].dropna().unique().tolist()
            airport_to_iata[json_airport] = iata_codes

        # Parse airport_database.yaml
        routes_db = {}  # dictionary mapping, e.g. {"ABZ": ["GDN"], "AUH": ["HBE", "ALA", "AMM"], ...}
        current_departure_iata = None

        with open(system_config.data_manager.airport_database_path, "r", encoding="utf-8") as f:
            airport_db_raw = f.read()

        for raw_line in airport_db_raw.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Check if this line is a "Departure" line with a colon
            if line.endswith(":"):
                # e.g. "Abu Dhabi (AUH):"
                dep_name, dep_iata = parse_airport_line(line)
                if dep_iata:
                    current_departure_iata = dep_iata
                    routes_db[current_departure_iata] = []
            else:
                # arrival line
                arr_name, arr_iata = parse_destination_line(line)
                if arr_iata and current_departure_iata:
                    routes_db[current_departure_iata].append(arr_iata)

        # Cross-reference routes
        final_routes = {}  # e.g. { 'ABZ': ['GDN', 'ALA', ...], 'AUH': ['ALA', ...] }

        for dep_name, arr_names in connections_dict.items():
            dep_iatas = airport_to_iata[dep_name]  # e.g. ["ABZ", "???", ...]

            for dep_iata in dep_iatas:
                if dep_iata not in routes_db:
                    # means the YAML has no routes from that IATA => skip
                    continue

                # among the arrivals in flight_data.json, see which are possible in routes_db
                valid_arr_iatas = []
                for arr_name in arr_names:
                    arr_iatas = airport_to_iata[arr_name]  # e.g. ["GDN", "???"]
                    # Check each arr_iata to see if it's in the routes_db[dep_iata]
                    for a in arr_iatas:
                        if a in routes_db[dep_iata]:
                            valid_arr_iatas.append(a)

                # store in final_routes
                if dep_iata not in final_routes:
                    final_routes[dep_iata] = []
                final_routes[dep_iata].extend(valid_arr_iatas)

        # Add new column to self.__orig_df_airport
        def build_connections_list(iata_code):
            if iata_code in final_routes:
                return list(set(final_routes[iata_code]))  # or just final_routes[iata_code]
            else:
                return []

        self.__orig_df_airport["connections"] = self.__orig_df_airport["iata"].apply(build_connections_list)

        # Now drop any row that has an empty connections list:
        self.__df_airport = self.__orig_df_airport[self.__orig_df_airport["connections"].apply(len) > 0]
        self.__airports_destinations = final_routes

    def _reset_databases(self):
        # Update the connections in the dataframe
        self._update_connections_in_df_airports()

        # Remove available flights, checked and possible flights databases
        self.remove_file(system_config.data_manager.available_flights_path)
        self.remove_file(system_config.data_manager.checked_flights_path)
        self.remove_file(system_config.data_manager.possible_flights_path)
        self.remove_file(system_config.reporter.report_path)
        Path('jobs').mkdir(exist_ok=True)
        Path('cache').mkdir(exist_ok=True)

        # TODO: Write a dedicated class for flights
        self.__possible_flights = {'possible_flights': []}
        self.__checked_flights = {'checked_flights': {}}
        self.__available_flights = {'available_flights': []}

    def _setup_edge_driver(self):
        driver_path = system_config.general.driver_path
        headless = system_config.general.headless

        # Set up EdgeOptions for headless mode
        options = Options()
        if headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')  # Recommended for Windows compatibility
            options.add_argument('--disable-dev-shm-usage')  # Useful for resource-limited systems
            options.add_argument('--no-sandbox')  # Useful for Linux-based systems
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--disable-background-timer-throttling')  # Prevents slowing down in headless mode
            options.add_argument('--disable-backgrounding-occluded-windows')  # Keeps browser responsive

        service = Service(driver_path)
        self.driver = webdriver.Edge(service=service, options=options)
        self.driver.set_page_load_timeout(300)  # Set to 300 seconds
        self.driver.command_executor.set_timeout(1000)

    @staticmethod
    def save_data(data: Dict, path: str):
        with open(path, 'w', encoding='utf-8') as file:
            yaml.dump(data,
                      file,
                      indent=4,
                      allow_unicode=True,
                      Dumper=IndentedDumper,
                      default_flow_style=False)

    @staticmethod
    def load_data(path: str) -> Dict:
        try:
            with open(path, 'r', encoding='utf-8') as file:
                return yaml.load(file, Loader=yaml.FullLoader)
        except FileNotFoundError:
            logger.warning(f"Error: The file at path {path} was not found.")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error loading YAML data: {e}")
            return {}

    @staticmethod
    def remove_file(path: str):
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"The file {path} has been removed.")
        else:
            logger.info(f"The file {path} does not exist.")

    def get_airport_coord(self, airport_name):
        return self.__df_airport.set_index("iata")["airport_coords"].get(airport_name)

    def get_airport_print_name(self, airport_name):
        return self.__df_airport.set_index("iata")["airport"].get(airport_name) + " (" + airport_name + ")"

    def get_airport_database(self):
        return self.__airports_destinations

    def get_all_airports(self):
        airports = []
        for airport in self.__airports_destinations:
            airports += self.__airports_destinations[airport]
        return list(set(airports))

    def is_airport_in_database(self, airport_name):
        return airport_name in self.__airports_destinations

    def get_airport_destinations(self, airport_name: str) -> List[str]:
        if airport_name in self.__airports_destinations:
            return self.__airports_destinations[airport_name]
        else:
            return []

    def set_airport_destinations(self, airport_name, destinations, overwrite=False):
        if self.is_airport_in_database(airport_name) and not overwrite:
            logger.warning(f"Airport {airport_name} is already in the database. "
                           f"Use the 'use_cache' parameter to overwrite the data.")
            return
        self.__airports_destinations[airport_name] = destinations
        self.save_data(self.__airports_destinations, system_config.data_manager.airport_database_path)
        logger.info(f"Airport {airport_name} has been added to the database.")

    def get_possible_flights(self):
        return self.__possible_flights

    def add_possible_flights(self, flights: List[List]):
        self.__possible_flights['possible_flights'] += flights
        self.save_data(self.__possible_flights, system_config.data_manager.possible_flights_path)

    def add_checked_flight(self, flight: Dict, result: Dict, date: str):
        """Thread-safe addition of a single flight check result."""
        with self._write_lock:
            key = f"{flight['hash']}-{date}"
            self.__checked_flights['checked_flights'][key] = result
            self.save_data(self.__checked_flights,
                           system_config.data_manager.checked_flights_path)

    def add_checked_flights(self, flights: Dict):
        self.__checked_flights = flights
        self.save_data(self.__checked_flights, system_config.data_manager.checked_flights_path)

    def get_checked_flight(self, flight: Dict, date: str):
        return self.__checked_flights['checked_flights'][f"{flight['hash']}-{date}"]

    def get_checked_flights(self):
        return self.__checked_flights

    def is_flight_already_checked(self, flight: Dict, date: str):
        return f"{flight['hash']}-{date}" in self.__checked_flights['checked_flights']

    def add_available_flight(self, flight: Dict):
        self.__available_flights['available_flights'].append(flight)
        self.save_data(self.__available_flights, system_config.data_manager.available_flights_path)

    def add_available_flights(self, flights: Dict):
        self.__available_flights = flights
        self.save_data(self.__available_flights, system_config.data_manager.available_flights_path)


# A singleton used to manage data across all services
data_manager = DataManager()
