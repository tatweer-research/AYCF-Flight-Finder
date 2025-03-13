import io
import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pdfplumber
import pytz
import requests
import yaml
from pdfplumber.pdf import PDF
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options

from settings import ConfigSchema
from utils import find_possible_csv_matches, get_iata_code

logger = logging.getLogger(__name__)


class WizzAirFlightConnectionParser:
    def __init__(self, yaml_path):
        """Initialize the parser with a path to save/load yaml data."""
        self.url = "https://multipass.wizzair.com/aycf-availability.pdf"
        self.yaml_path = yaml_path

    def load_saved_data(self):
        """Load previously saved flight data from the yaml file."""
        try:
            with open(self.yaml_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return dict()

    def save_data(self, data):
        """Save the parsed flight data to the yaml file."""
        with open(self.yaml_path, 'w') as f:
            yaml.dump(data, f, indent=3, sort_keys=False)

    def download_pdf(self):
        """Download the PDF from the specified URL."""
        response = requests.get(self.url)
        if response.status_code == 200:
            return response.content
        else:
            raise Exception("Failed to download PDF")

    def extract_metadata(self, pdf: PDF):
        """Extract 'last run' and 'departure period' from the first page of the PDF."""
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \((\w+)\) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \((\w+)\)'
        first_page = pdf.pages[0]
        cropped = first_page.crop((40, 30, 550, 150))
        text = cropped.extract_text_simple()
        lines = text.split('\n')
        metadata = {'last_parsed': datetime.now(), "departure_period": dict(), "last_run": dict()}
        line = lines[1]
        match = re.match(pattern, line)
        if match:
            start_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            end_time = datetime.strptime(match.group(2), "%Y-%m-%d %H:%M:%S")
            timezone = match.group(3)
            last_run_time = datetime.strptime(match.group(4), "%Y-%m-%d %H:%M:%S")
            last_run_timezone = match.group(5)

            metadata["departure_period"] = {
                "start": start_time,
                "end": end_time,
                "timezone": timezone
            }
            metadata["last_run"] = {
                "time": last_run_time,
                "timezone": last_run_timezone
            }
        return metadata

    def extract_connections(self, pdf: PDF):
        """
        Extract airport connections from a PDF and return a dictionary mapping departure cities to arrival cities.
        """
        if not pdf.pages:
            logger.warning("No pages found in the PDF.")
            return {}

        table_dataframes = []
        pages = pdf.pages
        for page in pages:
            logger.info(f"Parsing page number: {page.page_number}")
            try:
                tables = page.extract_tables(table_settings={})
            except Exception as e:
                logger.error(f"Error extracting tables on page {page.page_number}: {e}")
                tables = []

            # Skip the first table on the first page if it contains metadata (e.g., header info)
            if page.page_number == 1 and len(tables) == 3:
                tables = tables[1:]  # Assume first table is not flight data
            elif page.page_number == len(pages) and len(tables) == 1:
                pass
            elif len(tables) != 2:
                logger.error(f'There were more than 2 tables detected in page number {page.page_number} '
                             f'(number of tables: {len(tables)})! '
                             f'Returning empty dir since it is unclear why this happened.')
                return {}

            for table in tables:
                # Convert table to DataFrame, using first row as headers
                df = pd.DataFrame(table[1:], columns=table[0])
                table_dataframes.append(df)

        if not table_dataframes:
            logger.warning("No valid tables extracted from the PDF.")
            return {}

        # Combine all tables into a single DataFrame
        all_connections = pd.concat(table_dataframes, ignore_index=True)

        # Group by departure city and aggregate arrival cities into lists
        connections_dict = (
            all_connections.groupby("Departure City")["Arrival City"]
            .agg(list)
            .to_dict()
        )
        return connections_dict

    def parse_pdf(self, pdf: PDF, extracted_metadata=None):
        """Parse the PDF to extract metadata and airport connections."""
        metadata = extracted_metadata or self.extract_metadata(pdf)
        connections = self.extract_connections(pdf)
        return {
            "connections": connections,
            **metadata
        }

    @staticmethod
    def has_passed_7am_since_last_parsed(metadata: dict):
        """
        Checks if at least one full 7 AM (CET) has passed since last_parsed datetime.
        """
        cet = pytz.timezone("Europe/Berlin")
        last_parsed = metadata.get("last_parsed")

        if not isinstance(last_parsed, datetime):
            logger.error("'last_parsed' must be a datetime object. Returning 'False'")
            return False

        # Ensure last_parsed is in CET timezone
        if last_parsed.tzinfo is None:
            last_parsed = cet.localize(last_parsed)  # Make it timezone-aware if naive
        else:
            last_parsed = last_parsed.astimezone(cet)  # Convert to CET if it's in another timezone

        # Get the next 7 AM after last_parsed
        next_7am = last_parsed.replace(hour=7, minute=0, second=0, microsecond=0)

        if last_parsed.hour >= 7:
            # If last_parsed is after 7 AM, the next 7 AM is tomorrow
            next_7am += timedelta(days=1)

        # Get current CET time
        now = datetime.now(cet)

        return now >= next_7am

    def get_flight_data(self) -> tuple[dict, bool]:
        """
        Retrieve flight data, either from cache or by parsing a new PDF.

        If an update is required (i.e., the last saved data is outdated based on a 7 AM threshold),
        the function downloads and parses the latest flight data from WizzAir PDF, saves it, and returns the new data
        along with `True` indicating an update occurred.

        Otherwise, it returns the previously saved flight data along with `False`, indicating no update was necessary.
        """
        saved_data = self.load_saved_data()

        if saved_data and not self.has_passed_7am_since_last_parsed(saved_data):
            logger.info('Using saved data of flight data')
            return saved_data, False
        else:
            logger.info('Refreshing flight data')
            pdf_content = self.download_pdf()
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                extracted_metadata = self.extract_metadata(pdf)
                data = self.parse_pdf(pdf, extracted_metadata)
                self.save_data(data)
                return data, True


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

        self.config: ConfigSchema = None  # noqa
        self.load_config()
        logger.info('Configuration file loaded successfully')

        self.driver = None

        self._setup_logging()

        # Get the new airport destinations
        self.flight_connection_parser = WizzAirFlightConnectionParser(self.config.data_manager.flight_data_path)
        self.__airports_destinations = {}

        # Read the airport_iata_icao_path CSV into a DataFrame
        self.__orig_df_airport = None
        self.__df_airport = None
        self._setup_df_airports()

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

    def load_config(self, path: str = 'configuration.yaml'):
        # Load the YAML file
        with open(path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        self.config = ConfigSchema(**config)

    @staticmethod
    def save_config(config: BaseModel, path: str):
        json_str = config.model_dump_json()
        obj_dict = json.loads(json_str)
        with open(path, 'w', encoding='utf-8') as file:
            yaml.dump(obj_dict,
                      file,
                      indent=4,
                      allow_unicode=True,
                      Dumper=IndentedDumper,
                      default_flow_style=False)

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


    def _update_connections_in_df_airports(self):
        # Get possible IATA codes for airports in flight_connection_parser
        with open(self.config.data_manager.airport_name_special_cases_path, "r", encoding="utf-8") as f:
            special_name_map = yaml.safe_load(f)

        self.__airports_destinations = {}
        airport_to_iata = {}  # dictionary mapping e.g. {"Aalesund": [ "AES" ], "Aberdeen": [ "ABZ" ], ...}
        flight_data, updated = self.flight_connection_parser.get_flight_data()
        connections_dict = flight_data['connections']

        if updated or not self.config.data_manager.airport_database_dynamic_path.exists():
            # Since the PDF changed, we have to re-do this logic
            logger.info('WizzAir updated its PDF. Updating internal database of flights.')

            # Collect all departure & arrival names in one set
            errors = []
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
                    errors.append(json_airport)

                # Gather unique IATA codes
                iata_codes = matched_df["iata"].dropna().unique().tolist()
                airport_to_iata[json_airport] = iata_codes

            if errors:
                raise ValueError(f"No CSV match found for '{errors}' (even after special cases).")

            # Read airport_database_iata.yaml
            routes_db = self.load_data(self.config.data_manager.airport_database_iata_path)
            iata_to_german = self.load_data(self.config.data_manager.map_iata_to_german_name_path)

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

            final_routes = {dep_iata: arr_iatas for dep_iata, arr_iatas in final_routes.items() if arr_iatas}

            # Add new column to self.__orig_df_airport
            def build_connections_list(iata_code):
                if iata_code in final_routes:
                    return list(set(final_routes[iata_code]))
                else:
                    return []

            self.__orig_df_airport["connections"] = self.__orig_df_airport["iata"].apply(build_connections_list)

            # Now drop any row that has an empty connections list:
            self.__df_airport = self.__orig_df_airport[self.__orig_df_airport["connections"].apply(len) > 0]
            self.__airports_destinations = {
                f"{iata_to_german.get(origin, origin)} ({origin})":
                    [f"{iata_to_german.get(dest, dest)} ({dest})" for dest in destinations]
                for origin, destinations in final_routes.items()
            }
            self.save_data(self.__airports_destinations, self.config.data_manager.airport_database_dynamic_path)
        else:
            # Read from the cache
            logger.info('Reading internal database of flights.')
            self.__airports_destinations = self.load_data(self.config.data_manager.airport_database_dynamic_path)

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
            print(f"The file {path} has been removed.")
        else:
            print(f"The file {path} does not exist.")

    def get_airport_coord(self, airport_name):
        airport_iata = get_iata_code(airport_name)
        return self.__df_airport.set_index("iata")["airport_coords"].get(airport_iata)

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
