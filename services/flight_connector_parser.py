import io
import yaml
import logging
import re
from datetime import datetime

import pandas as pd
import pdfplumber
import requests

log = logging.getLogger(__name__)


class FlightConnectionParser:
    def __init__(self, yaml_path='data/flight_data.yaml'):
        """Initialize the parser with a path to save/load yaml data."""
        self.url = "https://multipass.wizzair.com/aycf-availability.pdf"
        self.yaml_path = yaml_path

    def load_saved_data(self):
        """Load previously saved flight data from the yaml file."""
        try:
            with open(self.yaml_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return None

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

    def extract_metadata(self, pdf):
        """Extract 'last run' and 'departure period' from the first page of the PDF."""
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \((\w+)\) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \((\w+)\)'
        first_page = pdf.pages[0]
        text = first_page.extract_text()
        lines = text.split('\n')
        metadata = {}
        metadata["departure_period"] = dict()
        metadata["last_run"] = dict()
        for line in lines:
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
                break
        return metadata

    def extract_connections(self, pdf):
        """
        Extract airport connections from a PDF and return a dictionary mapping departure cities to arrival cities.
        """
        if not pdf.pages:
            log.warning("No pages found in the PDF.")
            return {}

        table_dataframes = []
        for page in pdf.pages:
            log.info(f"Parsing page number: {page.page_number}")
            try:
                tables = page.extract_tables(table_settings={})
            except Exception as e:
                log.error(f"Error extracting tables on page {page.page_number}: {e}")
                tables = []

            # Skip the first table on the first page if it contains metadata (e.g., header info)
            if page.page_number == 1 and len(tables) == 3:
                tables = tables[1:]  # Assume first table is not flight data
            elif len(tables) != 2:
                log.error(f'There were more than 2 tables detected in page number {page.page_numer}!'
                          f'Returning empty dir since it is unclear why this happened.')
                return {}

            for table in tables:
                # Convert table to DataFrame, using first row as headers
                df = pd.DataFrame(table[1:], columns=table[0])
                table_dataframes.append(df)

        if not table_dataframes:
            log.warning("No valid tables extracted from the PDF.")
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

    def parse_pdf(self, pdf):
        """Parse the PDF to extract metadata and airport connections."""
        metadata = self.extract_metadata(pdf)
        connections = self.extract_connections(pdf)
        return {
            "last_run": metadata.get("last_run"),
            "departure_period": metadata.get("departure_period"),
            "connections": connections
        }

    def get_flight_data(self):
        """Retrieve flight data, using saved data if 'last run' matches, otherwise parse the PDF."""
        saved_data = self.load_saved_data()
        pdf_content = self.download_pdf()
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            extracted_metadata = self.extract_metadata(pdf)
            if saved_data and saved_data.get("last_run") == extracted_metadata.get("last_run"):
                return saved_data
            else:
                data = self.parse_pdf(pdf)
                self.save_data(data)
                return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = FlightConnectionParser()
    flight_data = parser.get_flight_data()
    print(f"Last run: {flight_data['last_run']}")
    print(f"Departure period: {flight_data['departure_period']}")
    for airport, connections in flight_data['connections'].items():
        print(f"{airport}: {', '.join(connections)}")
