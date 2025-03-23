import hashlib
from collections import deque

from services.data_manager import data_manager
from services.logger_service import logger
from utils import compare_times, remove_duplicates_from_list, get_city
from utils import format_seconds


class FlightFinderService:
    """Filters and processes the scrapped data to find suitable flights"""

    def __init__(self, config=None):
        self.config = data_manager.config if not config else config
        logger.debug('FlightFinderService initialized')
        self.database_airports = data_manager.get_all_airports()
        self.departure_airports = self.config.flight_data.departure_airports or self.database_airports
        self.destination_airports = self.config.flight_data.destination_airports or self.database_airports

    def find_possible_roundtrip_flights_from_airport(self, airport, save_data=True):
        """
        Find possible roundtrip flights from a given airport and return flights to list of departure airports.
        only direct flights are considered.
        """
        flights = []
        destinations = data_manager.get_airport_destinations(airport)

        # Filter destinations to only include airports in the destination_airports list
        destinations = [destination for destination in destinations if destination in self.destination_airports]

        for destination in destinations:
            destination_destinations = data_manager.get_airport_destinations(destination)

            for departure_airport in self.departure_airports:
                if departure_airport in destination_destinations:
                    # Create hash for outward flight
                    outward_hash = hashlib.sha256(f"{airport}-{destination}".encode()).hexdigest()

                    # Create hash for return flight
                    return_hash = hashlib.sha256(f"{destination}-{departure_airport}".encode()).hexdigest()

                    flight = {
                        'outward_flight': {
                            'hash': outward_hash,  # Unique hash for the outward flight
                            'type': 'direct',
                            'airport': airport,
                            'destination': destination
                        },
                        'return_flight': {
                            'hash': return_hash,  # Unique hash for the return flight
                            'type': 'direct',
                            'airport': destination,
                            'destination': departure_airport
                        }
                    }
                    flights.append(flight)

        logger.info(f'Found {len(flights)} possible flights from {airport} to departure airports')
        data_manager.add_possible_flights(flights, save_data)

    def find_possible_roundtrip_flights_from_departure_airports(self, save_data=True):
        """
        Finds possible roundtrip flights from all departure airports.
        Only direct flights are considered.
        """
        for airport in self.departure_airports:
            self.find_possible_roundtrip_flights_from_airport(airport, save_data)

        possible_flights = data_manager.get_possible_flights()['possible_flights']
        estimated_time = self.get_estimated_checking_time(possible_flights)
        logger.info(f'Found a total of {len(possible_flights)} possible roundtrip flights from all departure airports')
        logger.info(f'Estimated scraping time: {estimated_time}')

    def find_possible_one_stop_flights(self, max_stops=1, save_data=True):
        """
        Finds possible direct and one-stop oneway flights from departure airports to destination airports.
        Uses BFS to find possible destinations from departure airports.

        Parameters:
            max_stops (int): Maximum number of stops to consider. 0 for direct flights, 1 for one-stop flights.
            save_data (bool): Whether to save the possible flights into a YAML
        """
        flights = []  # List to hold both direct and one-stop flights

        if max_stops > 1:
            max_stops = 1  # Only consider direct and one-stop flights

        for airport in self.departure_airports:
            visited = set()  # Keep track of visited airports to avoid cycles
            queue = deque([(airport, 0)])  # Start BFS with (airport, depth)

            while queue:
                current_airport, depth = queue.popleft()

                if depth > max_stops:  # Stop searching if we exceed the allowed number of stops
                    continue

                visited.add(current_airport)
                destinations = data_manager.get_airport_destinations(current_airport)

                for destination in destinations:
                    if destination in visited and depth == 0:
                        continue

                    # Direct flight (depth 1)
                    if depth == 0 and destination in self.destination_airports:
                        outward_hash = hashlib.sha256(f"{airport}-{destination}".encode()).hexdigest()

                        flight = {
                            'first_flight': {
                                'hash': outward_hash,  # Unique hash for the direct flight
                                'airport': airport,
                                'destination': destination
                            },
                            'second_flight': None  # No second flight for direct flights
                        }
                        flights.append(flight)

                    # One-stop flight (depth 1) - only if max_stops > 0
                    elif depth == 1 and destination in self.destination_airports and max_stops > 0:
                        first_hash = hashlib.sha256(f"{airport}-{current_airport}".encode()).hexdigest()
                        second_hash = hashlib.sha256(f"{current_airport}-{destination}".encode()).hexdigest()

                        flight = {
                            'first_flight': {
                                'hash': first_hash,  # Unique hash for the first leg
                                'airport': airport,
                                'destination': current_airport
                            },
                            'second_flight': {
                                'hash': second_hash,  # Unique hash for the second leg
                                'airport': current_airport,
                                'destination': destination
                            }
                        }
                        flights.append(flight)

                    # Add to queue for further exploration
                    queue.append((destination, depth + 1))

        estimated_time = self.get_estimated_checking_time(flights)
        logger.info(f'Found {len(flights)} possible flights (direct and one-stop) from departure airports to destination '
                    f'airports with max stops: {max_stops}')
        logger.info(f'Estimated scraping time: {estimated_time}')
        data_manager.add_possible_flights(flights, save_data)

    def get_estimated_checking_time(self, possible_flights):
        # Handle multiple cases for flight keys
        first_flights = []
        second_flights = []

        for flight in possible_flights:
            if 'first_flight' in flight and 'second_flight' in flight:
                # Case with first_flight and second_flight keys
                first_flights.append(flight['first_flight']['hash'])
                if flight['second_flight']:
                    second_flights.append(flight['second_flight']['hash'])
            elif 'outward_flight' in flight and 'return_flight' in flight:
                # Case with outward_flight and return_flight keys
                first_flights.append(flight['outward_flight']['hash'])
                if flight['return_flight']:
                    second_flights.append(flight['return_flight']['hash'])

        # Combine unique flight hashes and calculate estimated time
        number_unique_flights = len(set(first_flights + second_flights))
        estimated_time = number_unique_flights * 5 * 4 + 20  # 5s per flight check and checked four times + 20s setup
        return format_seconds(estimated_time)

    def find_available_oneway_flights(self):
        """
        Finds available oneway flights from possible_flights if they exist in checked_flights,
        including direct flights, and ensures valid sequencing for connecting flights.
        """

        logger.info('Processing checked flights to find available flights...')
        possible_flights = data_manager.get_possible_flights()
        checked_flights = data_manager.get_checked_flights()

        available_flights = {"available_flights": []}

        # Loop through each set of possible flights
        for flight_set in possible_flights["possible_flights"]:
            first_flight = flight_set["first_flight"]
            second_flight = flight_set.get("second_flight")  # Can be None

            # Find all checked details for the first flight
            matching_first_flights = []
            for flights in checked_flights['checked_flights'].values():
                if flights:
                    for flight in flights:
                        if (
                                flight["departure"]["city"] == get_city(first_flight["airport"])
                                and flight["arrival"]["city"] == get_city(first_flight["destination"])
                        ):
                            matching_first_flights.append(flight)

            # Check if it's a direct flight (second_flight is None)
            if second_flight is None:
                if matching_first_flights:
                    for matched_first in matching_first_flights:
                        available_flights["available_flights"].append(
                            {"first_flight": [matched_first], "second_flight": None}
                        )
                continue

            # If it's not a direct flight, find all checked details for the second flight
            matching_second_flights = []
            for flights in checked_flights['checked_flights'].values():
                if flights:
                    for flight in flights:
                        if (
                                flight["departure"]["city"] == get_city(second_flight["airport"])
                                and flight["arrival"]["city"] == get_city(second_flight["destination"])
                        ):
                            matching_second_flights.append(flight)

            # Combine matching flights while ensuring valid sequencing
            for first_checked_flight in matching_first_flights:
                for second_checked_flight in matching_second_flights:
                    if compare_times(
                            second_checked_flight["departure"]["time"],
                            first_checked_flight["arrival"]["time"],
                            second_checked_flight["date"],
                            first_checked_flight["date"],
                    ):
                        available_flights["available_flights"].append(
                            {
                                "first_flight": [first_checked_flight],
                                "second_flight": [second_checked_flight],
                            }
                        )
        available_flights["available_flights"] = remove_duplicates_from_list(available_flights["available_flights"])
        logger.info(f'Found {len(available_flights["available_flights"])} available flights')
        return available_flights

    def find_available_roundtrip_flights(self):
        """
        Finds available roundtrip flights from possible_flights if they exist in checked_flights.
        Ensures valid sequencing and flight conditions.
        """
        possible_flights = data_manager.get_possible_flights()
        checked_flights = data_manager.get_checked_flights()

        available_flights = {"available_flights": []}

        for flight_set in possible_flights["possible_flights"]:
            outward_flight = flight_set["outward_flight"]
            return_flight = flight_set.get("return_flight")  # Can be None

            # Find all matching checked details for the outward flight
            matching_outward_flights = []
            for flights in checked_flights['checked_flights'].values():
                if flights:
                    for flight in flights:
                        if (
                                flight["departure"]["city"] == get_city(outward_flight["airport"])
                                and flight["arrival"]["city"] == get_city(outward_flight["destination"])
                        ):
                            matching_outward_flights.append(flight)

            # If no outward flights found, skip this set
            if not matching_outward_flights:
                continue

            # Find all matching checked details for the return flight
            matching_return_flights = []
            if return_flight:
                for flights in checked_flights['checked_flights'].values():
                    if flights:
                        for flight in flights:
                            if (
                                    flight["departure"]["city"] == get_city(return_flight["airport"])
                                    and flight["arrival"]["city"] == get_city(return_flight["destination"])
                            ):
                                matching_return_flights.append(flight)

            # Combine matching outward and return flights while ensuring valid sequencing
            for outward_checked in matching_outward_flights:
                if not return_flight:
                    # If no return flight is specified, consider only outward flights
                    available_flights["available_flights"].append(
                        {
                            "outward_flight": [outward_checked],
                            "return_flight": None,
                        }
                    )
                    continue

                for return_checked in matching_return_flights:
                    if compare_times(
                            return_checked["departure"]["time"],
                            outward_checked["arrival"]["time"],
                            return_checked["date"],
                            outward_checked["date"],
                    ):
                        available_flights["available_flights"].append(
                            {
                                "outward_flight": [outward_checked],
                                "return_flight": [return_checked],
                            }
                        )
        available_flights["available_flights"] = remove_duplicates_from_list(available_flights["available_flights"])
        logger.info(f'Found {len(available_flights["available_flights"])} available roundtrip flights')
        return available_flights
