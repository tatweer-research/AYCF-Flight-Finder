import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options

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

        self.config = None
        self.load_config()
        logger.info('Configuration file loaded successfully')

        self.driver = None
        self._setup_logging()
        self._reset_databases()
        if self.config.scraper.initialize_driver:
            self._setup_edge_driver()

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

    def _reset_databases(self):
        self.__airports_destinations = self.load_data(self.config.data_manager.airport_database_path)

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
