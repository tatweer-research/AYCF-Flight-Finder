import unittest
from PyPDF2 import PdfReader
from pathlib import Path

from services.data_manager import data_manager
from services.reporter import ReportService


class TestReporterService(unittest.TestCase):

    def compare_pdfs(self, generated_path: Path, expected_path: Path):
        def extract_text(path):
            with open(path, "rb") as f:
                return "\n".join([page.extract_text() or "" for page in PdfReader(f).pages])

        self.assertTrue(generated_path.exists(), f"Generated report not found: {generated_path}")
        self.assertTrue(expected_path.exists(), f"Expected report not found: {expected_path}")

        actual_text = extract_text(generated_path)
        expected_text = extract_text(expected_path)

        self.assertEqual(actual_text, expected_text,
                         f"PDF content does not match.\nGenerated: {generated_path}\nExpected: {expected_path}")

    def test_generate_direct_report(self):
        data_manager._reset_databases()
        data_manager.load_config("tests/resources/direct/configuration.yaml")

        # Load available flights
        available = data_manager.load_data(data_manager.config.data_manager.available_flights_path)
        data_manager.add_available_flights(available)

        reporter = ReportService()
        reporter.generate_oneway_flight_report()

        self.compare_pdfs(Path(data_manager.config.reporter.report_path),
                          Path("tests/resources/direct/report.pdf"))

    def test_generate_onestop_report(self):
        data_manager._reset_databases()
        data_manager.load_config("tests/resources/onestop/configuration.yaml")

        available = data_manager.load_data(data_manager.config.data_manager.available_flights_path)
        data_manager.add_available_flights(available)

        reporter = ReportService()
        reporter.generate_oneway_flight_report()

        self.compare_pdfs(Path(data_manager.config.reporter.report_path),
                          Path("tests/resources/onestop/report.pdf"))

    def test_generate_roundtrip_report(self):
        data_manager._reset_databases()
        data_manager.load_config("tests/resources/roundtrip/configuration.yaml")

        available = data_manager.load_data(data_manager.config.data_manager.available_flights_path)
        data_manager.add_available_flights(available)

        reporter = ReportService()
        reporter.generate_roundtrip_flight_report()

        self.compare_pdfs(Path(data_manager.config.reporter.report_path),
                          Path("tests/resources/roundtrip/report.pdf"))


if __name__ == '__main__':
    unittest.main()
