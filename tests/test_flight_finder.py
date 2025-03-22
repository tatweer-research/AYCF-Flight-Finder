from services.flight_finder import FlightFinderService
from services.data_manager import data_manager


class TestFlightFinderService:

    def setup_method(self):
        data_manager._reset_databases()
        self.service = FlightFinderService()

    def test_find_possible_one_stop_flights_direct(self):
        data_manager._reset_databases()

        data_manager.load_config(r"tests/resources/direct/configuration.yaml")
        expected = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)

        self.service.find_possible_one_stop_flights(max_stops=data_manager.config.flight_data.max_stops)
        generated = data_manager.get_possible_flights()

        assert generated == expected, "Generated possible flights do not match the expected ones"

    def test_find_possible_one_stop_flights_one_stop(self):
        data_manager._reset_databases()

        data_manager.load_config(r"tests/resources/onestop/configuration.yaml")
        expected = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)

        self.service.find_possible_one_stop_flights(max_stops=data_manager.config.flight_data.max_stops)
        generated = data_manager.get_possible_flights()

        assert generated == expected, "Generated possible flights do not match the expected ones"


if __name__ == '__main__':
    test = TestFlightFinderService()
    test.setup_method()
    test.test_find_possible_one_stop_flights_direct()
    test.test_find_possible_one_stop_flights_one_stop()
