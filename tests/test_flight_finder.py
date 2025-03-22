import unittest
from services.flight_finder import FlightFinderService
from services.data_manager import data_manager


class TestFlightFinderService(unittest.TestCase):

    def setUp(self):
        data_manager._reset_databases()
        self.service = FlightFinderService()

    def test_find_possible_one_stop_flights_direct(self):
        data_manager.load_config("tests/resources/direct/configuration.yaml")
        expected = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)

        self.service.find_possible_one_stop_flights(max_stops=data_manager.config.flight_data.max_stops)
        generated = data_manager.get_possible_flights()

        self.assertEqual(generated, expected, "Generated direct flights do not match expected")

    def test_find_possible_one_stop_flights_one_stop(self):
        data_manager.load_config("tests/resources/onestop/configuration.yaml")
        expected = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)

        self.service.find_possible_one_stop_flights(max_stops=data_manager.config.flight_data.max_stops)
        generated = data_manager.get_possible_flights()

        self.assertEqual(generated, expected, "Generated one-stop flights do not match expected")

    def test_find_possible_roundtrip_flights(self):
        data_manager.load_config("tests/resources/roundtrip/configuration.yaml")
        expected = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)

        self.service.find_possible_roundtrip_flights_from_departure_airports()
        generated = data_manager.get_possible_flights()

        self.assertEqual(generated, expected, "Generated roundtrip flights do not match expected")

    def test_find_available_oneway_flights_direct(self):
        data_manager._reset_databases()
        data_manager.load_config("tests/resources/direct/configuration.yaml")

        # Load mock flight data and expected checked results
        possible = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)
        checked = data_manager.load_data(data_manager.config.data_manager.checked_flights_path)
        expected = data_manager.load_data(data_manager.config.data_manager.available_flights_path)

        data_manager.add_possible_flights(possible["possible_flights"])
        data_manager.add_checked_flights(checked)

        generated = self.service.find_available_oneway_flights()

        self.assertEqual(generated, expected, "Available one-way flights don't match expected results")

    def test_find_available_oneway_flights_one_stop(self):
        data_manager._reset_databases()
        data_manager.load_config("tests/resources/onestop/configuration.yaml")

        # Load mock flight data and expected checked results
        possible = data_manager.load_data(data_manager.config.data_manager.possible_flights_path)
        checked = data_manager.load_data(data_manager.config.data_manager.checked_flights_path)
        expected = data_manager.load_data(data_manager.config.data_manager.available_flights_path)

        data_manager.add_possible_flights(possible["possible_flights"])
        data_manager.add_checked_flights(checked)

        generated = self.service.find_available_oneway_flights()

        self.assertEqual(generated, expected, "Available one-way flights don't match expected results")



if __name__ == '__main__':
    unittest.main()
