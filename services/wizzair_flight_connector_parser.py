import io
import logging
import re
from datetime import datetime, timedelta

import pandas as pd
import pdfplumber
import pytz
from pdfplumber.pdf import PDF
import requests
import yaml

from settings import system_config

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


if __name__ == "__main__":
    parser = WizzAirFlightConnectionParser(system_config.data_manager.flight_data_path)
    flight_data, _ = parser.get_flight_data()
    print(f"Last run: {flight_data['last_run']}")
    print(f"Departure period: {flight_data['departure_period']}")
    for airport, connections in flight_data['connections'].items():
        print(f"{airport}: {', '.join(connections)}")
