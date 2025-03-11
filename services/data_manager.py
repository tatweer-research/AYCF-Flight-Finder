import logging
import os
import threading
from pathlib import Path
from typing import Dict, List
import unidecode

import pandas as pd
import yaml
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options

from services.flight_connector_parser import FlightConnectionParser
from settings import ConfigSchema

logger = logging.getLogger(__name__)


class IndentedDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(IndentedDumper, self).increase_indent(flow, False)


class ModulePathFormatter(logging.Formatter):
    def format(self, record):
        # Convert the file path to a module-like path
        content_root = os.getcwd()
        relative_path = os.path.relpath(record.pathname, content_root)
        module_path = relative_path.replace(os.sep, ".").rsplit(".py", 1)[0]
        record.module_path = module_path
        return super().format(record)


class DataManager:
    def __init__(self):
        self._write_lock = threading.Lock()

        # Load the YAML file
        with open('configuration.yaml', 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        self.config = ConfigSchema(**config)
        logger.info('Configuration file loaded successfully')

        # Get the new airport destinations
        self.flight_connection_parser = FlightConnectionParser()
        self.__airports_destinations = {}

        # Read the airport_iata_icao_path CSV into a DataFrame
        self.__orig_df_airport = None
        self.__df_airport = None
        self._setup_df_airports()

        self.driver = None
        self._setup_logging()
        self._reset_databases()
        if self.config.scraper.initialize_driver:
            self._setup_edge_driver()

    def _setup_df_airports(self):
        self.__orig_df_airport = pd.read_csv(self.config.data_manager.airport_iata_icao_path)
        self.__orig_df_airport = self.__orig_df_airport[self.__orig_df_airport['iata'].notna() & (self.__orig_df_airport['iata'] != '')]
        self.__orig_df_airport = self.__orig_df_airport.drop_duplicates(subset='iata', keep='first')
        # Create a dictionary mapping IATA codes to (latitude, longitude) tuples
        airport_coords = self.__orig_df_airport.set_index('iata')[['latitude', 'longitude']].to_dict(orient='index')
        self.__orig_df_airport["airport_coords"] = self.__orig_df_airport["iata"].map(
            lambda iata: (
                airport_coords[iata]["latitude"], airport_coords[iata]["longitude"]) if iata in airport_coords else None
        )

    def _update_connections_in_df_airports(self):
        # Read the YAML file
        with open(self.config.data_manager.airport_name_to_iata_path, "r", encoding="utf-8") as f:
            name_to_iata = yaml.safe_load(f)
        name_to_iata = {unidecode.unidecode(airport_name): iata for airport_name, iata in name_to_iata.items()}

        # Refresh (if necessary) the airport destinations/connections
        airports_destinations = self.flight_connection_parser.get_flight_data()['connections']
        self.__airports_destinations = {}

        # Validate & build connections dictionary mapping source IATA → list of destination IATAs.
        for source_name, destination_names in airports_destinations.items():
            # Convert source airport name to ASCII
            source_name_ascii = unidecode.unidecode(source_name)

            # Check that we have an IATA code for this source
            source_iata = name_to_iata.get(source_name_ascii)
            if not source_iata:
                raise ValueError(f"No IATA code found for airport: {source_name} (ASCII: {source_name_ascii})")

            # Collect all destination IATAs, also converting them to ASCII for lookup
            dest_iatas = []
            for dest_name in destination_names:
                dest_name_ascii = unidecode.unidecode(dest_name)

                if dest_name_ascii not in name_to_iata:
                    raise ValueError(
                        f"No IATA code found for destination airport: {dest_name} (ASCII: {dest_name_ascii})")

                dest_iata = name_to_iata[dest_name_ascii]
                dest_iatas.append(dest_iata)

            self.__airports_destinations[source_iata] = dest_iatas

        # Combine with csv data and check for missing iatas
        flight_data_iatas = set(self.__airports_destinations.keys())
        csv_iatas = set(self.__orig_df_airport["iata"])
        missing_in_csv = flight_data_iatas - csv_iatas
        if missing_in_csv:
            raise ValueError(
                f"The following IATA codes appear in flight_data but are not in the CSV: {missing_in_csv}"
            )

        # Create a new column in df_airports with the connections
        self.__orig_df_airport["connections"] = self.__orig_df_airport["iata"].map(self.__airports_destinations)

        # Remove airports without connections
        self.__df_airport = self.__orig_df_airport.dropna(subset=["connections"]).copy()

    def _setup_logging(self):
        """Setup logging with console and file handlers."""
        # Retrieve logger
        logger.setLevel(logging.DEBUG)

        # Create file handler
        file_handler = logging.FileHandler(self.config.logging.log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(ModulePathFormatter(
            self.config.logging.log_format,
            self.config.logging.date_format
        ))
        file_handler.setLevel(self.config.logging.log_level_console)

        # File handler for DEBUG logs (DEBUG only)
        file_handler_debug = logging.FileHandler(
            self.config.logging.log_file.stem + '-debug.log',
            mode='w',
            encoding='utf-8'
        )
        file_handler_debug.setLevel(self.config.logging.log_level_file)
        file_handler_debug.setFormatter(ModulePathFormatter(
            self.config.logging.log_format,
            self.config.logging.date_format
        ))

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ModulePathFormatter(
            self.config.logging.log_format,
            self.config.logging.date_format
        ))
        console_handler.setLevel(self.config.logging.log_level_console)

        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.addHandler(file_handler_debug)

        logger.debug('Logging has been configured with both console and file handlers.')

    def _reset_databases(self):
        # Update the connections in the dataframe
        self._update_connections_in_df_airports()

        # Remove available flights, checked and possible flights databases
        self.remove_file(self.config.data_manager.available_flights_path)
        self.remove_file(self.config.data_manager.checked_flights_path)
        self.remove_file(self.config.data_manager.possible_flights_path)
        self.remove_file(self.config.reporter.report_path)
        Path('jobs').mkdir(exist_ok=True)
        Path('cache').mkdir(exist_ok=True)

        # TODO: Write a dedicated class for flights
        self.__possible_flights = {'possible_flights': []}
        self.__checked_flights = {'checked_flights': {}}
        self.__available_flights = {'available_flights': []}

    def _setup_edge_driver(self):
        driver_path = self.config.general.driver_path
        headless = self.config.general.headless

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
        self.save_data(self.__airports_destinations, self.config.data_manager.airport_database_path)
        logger.info(f"Airport {airport_name} has been added to the database.")

    def get_possible_flights(self):
        return self.__possible_flights

    def add_possible_flights(self, flights: List[List]):
        self.__possible_flights['possible_flights'] += flights
        self.save_data(self.__possible_flights, self.config.data_manager.possible_flights_path)

    def add_checked_flight(self, flight: Dict, result: Dict, date: str):
        """Thread-safe addition of a single flight check result."""
        with self._write_lock:
            key = f"{flight['hash']}-{date}"
            self.__checked_flights['checked_flights'][key] = result
            self.save_data(self.__checked_flights,
                           self.config.data_manager.checked_flights_path)

    def add_checked_flights(self, flights: Dict):
        self.__checked_flights = flights
        self.save_data(self.__checked_flights, self.config.data_manager.checked_flights_path)

    def get_checked_flight(self, flight: Dict, date: str):
        return self.__checked_flights['checked_flights'][f"{flight['hash']}-{date}"]

    def get_checked_flights(self):
        return self.__checked_flights

    def is_flight_already_checked(self, flight: Dict, date: str):
        return f"{flight['hash']}-{date}" in self.__checked_flights['checked_flights']

    def add_available_flight(self, flight: Dict):
        self.__available_flights['available_flights'].append(flight)
        self.save_data(self.__available_flights, self.config.data_manager.available_flights_path)

    def add_available_flights(self, flights: Dict):
        self.__available_flights = flights
        self.save_data(self.__available_flights, self.config.data_manager.available_flights_path)


# A singleton used to manage data across all services
data_manager = DataManager()
