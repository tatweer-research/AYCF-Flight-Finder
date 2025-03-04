import copy

import yaml
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer
from reportlab.platypus.flowables import HRFlowable

from services.data_manager import data_manager, logger
from utils import compare_times, calculate_waiting_time, sum_flight_durations, calculate_arrival_date


class ReportService:
    """Generates visual reports from the found flights"""

    def __init__(self):
        """
        Initialize the ReportService with a data manager and logger.
        """
        self.config = data_manager.config
        self.report_path = self.config.reporter.report_path
        self.available_flights_path = self.config.data_manager.available_flights_path
        self.logo_path = self.config.reporter.logo_path

    def add_second_flight(self, elements, flight, outward, styles):
        try:
            return_flight = flight.get('second_flight', [])[0]

            waiting_time = self.add_waiting_time(elements, outward, return_flight, styles)

            self.add_total_duration(elements, outward, return_flight, styles, waiting_time)

            # Second flight
            elements.append(Paragraph("<b>Second Flight:</b>", styles['Normal']))
            flight_path = f"{return_flight['departure']['city']} → {return_flight['arrival']['city']}"
            elements.append(Paragraph(flight_path, styles['Heading4']))
            return_details = Paragraph(
                f"Date: {return_flight['date']}<br/>"
                f"Departure: {return_flight['departure']['city']} ({return_flight['departure']['time']} {return_flight['departure']['timezone']})<br/>"
                f"Arrival: {return_flight['arrival']['city']} ({return_flight['arrival']['time']} {return_flight['arrival']['timezone']})<br/>"
                f"Duration: {return_flight['duration']}<br/>"
                f"Flight Code: {return_flight['flight_code']}<br/>"
                f"Carrier: {return_flight['carrier']}<br/>"
                f"Price: {return_flight['price']}",
                styles['Normal']
            )
            elements.append(return_details)
        except Exception as e:
            logger.warning(f"Error adding second flight details: {e}")

    def add_waiting_time(self, elements, outward, return_flight, styles, text="Waiting Time:"):
        arrival_date = calculate_arrival_date(outward)
        waiting_time = calculate_waiting_time(outward['arrival']['time'],
                                              return_flight['departure']['time'],
                                              arrival_date,
                                              return_flight['date'])
        # Make the waiting time bold and centered
        centered_style = copy.deepcopy(styles['Normal'])
        centered_style.alignment = 1  # Center alignment
        # centered_style.fontSize = 14  # Adjust the font size if needed
        centered_style.leading = 18  # Adjust line spacing if needed
        elements.append(Paragraph(f"<b>{text} {waiting_time}</b>", centered_style))
        return waiting_time

    def add_total_duration(self, elements, outward, return_flight, styles, waiting_time):
        # Make the waiting time bold and centered
        centered_style = copy.deepcopy(styles['Normal'])
        centered_style.alignment = 1  # Center alignment
        # centered_style.fontSize = 14  # Adjust the font size if needed
        centered_style.leading = 18  # Adjust line spacing if needed
        total_duration = sum_flight_durations([outward['duration'],
                                               waiting_time,
                                               return_flight['duration']])
        elements.append(Paragraph(f"<b>Total Duration: {total_duration}</b>", centered_style))

    def add_first_flight(self, elements, flight, outward, styles):
        try:
            outward = flight.get('first_flight', [])[0]

            # First flight
            elements.append(Paragraph("<b>First Flight:</b>", styles['Normal']))
            flight_path = f"{outward['departure']['city']} → {outward['arrival']['city']}"
            elements.append(Paragraph(flight_path, styles['Heading4']))
            outward_details = Paragraph(
                f"Date: {outward['date']}<br/>"
                f"Departure: {outward['departure']['city']} ({outward['departure']['time']} {outward['departure']['timezone']})<br/>"
                f"Arrival: {outward['arrival']['city']} ({outward['arrival']['time']} {outward['arrival']['timezone']})<br/>"
                f"Duration: {outward['duration']}<br/>"
                f"Flight Code: {outward['flight_code']}<br/>"
                f"Carrier: {outward['carrier']}<br/>"
                f"Price: {outward['price']}",
                styles['Normal']
            )
            elements.append(outward_details)

            # Add a horizontal line between first and second flights
            elements.append(Spacer(1, 10))  # Add some space before the line
            elements.append(HRFlowable(width="30%", thickness=1, color="black"))
            elements.append(Spacer(1, 10))  # Add some space after the line
        except Exception as e:
            logger.warning(f"Error adding first flight details: {e}")
        return outward

    def load_flights_and_setup_document(self):
        # Load the YAML file
        with open(self.available_flights_path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        # Extract available flights
        available_flights = data.get('available_flights', [])
        # Create the PDF document
        pdf = SimpleDocTemplate(str(self.report_path), pagesize=letter)
        elements = []
        # Add logo
        try:
            logo = Image(self.logo_path)
            # Scale the logo to fit within the desired dimensions while maintaining the aspect ratio
            logo._restrictSize(1.5 * inch, 1 * inch)  # Max dimensions (width, height)
            logo.hAlign = 'RIGHT'
            elements.append(logo)
        except Exception as e:
            logger.error(f"Error adding logo: {e}")
        # Add title
        styles = getSampleStyleSheet()
        title = Paragraph("Flight Report", styles['Title'])
        elements.append(title)
        return available_flights, elements, pdf, styles

    def add_near_and_destination_airports(self, elements, styles):
        # Add a line space
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
        elements.append(Paragraph("<b>Destination Airports:</b>", styles['Normal']))
        symbol = "✈ "
        destination_airports = data_manager.config.flight_data.destination_airports
        if destination_airports:
            for airport in data_manager.config.flight_data.destination_airports:
                elements.append(Paragraph(symbol + airport, styles['Normal']))
        else:
            elements.append(Paragraph("No destination airports specified.", styles['Normal']))
        elements.append(Paragraph("<br/><br/>", styles['Normal']))

        elements.append(Paragraph("<b>departure Airports:</b>", styles['Normal']))
        departure_airports = data_manager.config.flight_data.departure_airports
        if departure_airports:
            for airport in data_manager.config.flight_data.departure_airports:
                elements.append(Paragraph(symbol + airport, styles['Normal']))
        else:
            elements.append(Paragraph("No departure airports specified.", styles['Normal']))
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
        elements.append(HRFlowable(width="80%", thickness=1, color="black"))
        elements.append(Paragraph("<br/><br/>", styles['Normal']))

    def add_roundtrip(self, elements, flight, styles):
        outward = flight.get('outward_flight', [])[0]
        return_flight = flight.get('return_flight', [])[0]
        # Outward flight
        elements.append(Paragraph("<b>Outward Flight:</b>", styles['Normal']))
        flight_path = f"{outward['departure']['city']} → {outward['arrival']['city']}"
        elements.append(Paragraph(flight_path, styles['Heading4']))
        outward_details = Paragraph(
            f"Date: {outward['date']}<br/>"
            f"Departure: {outward['departure']['city']} ({outward['departure']['time']} {outward['departure']['timezone']})<br/>"
            f"Arrival: {outward['arrival']['city']} ({outward['arrival']['time']} {outward['arrival']['timezone']})<br/>"
            f"Duration: {outward['duration']}<br/>"
            f"Flight Code: {outward['flight_code']}<br/>"
            f"Carrier: {outward['carrier']}<br/>"
            f"Price: {outward['price']}",
            styles['Normal']
        )
        elements.append(outward_details)
        # Add a horizontal line between outward and return flights
        elements.append(Spacer(1, 10))  # Add some space before the line
        elements.append(HRFlowable(width="30%", thickness=1, color="black"))
        elements.append(Spacer(1, 10))  # Add some space after the line

        self.add_waiting_time(elements, outward, return_flight, styles, text="Vacation Time :-) ")

        # Return flight
        elements.append(Paragraph("<b>Return Flight:</b>", styles['Normal']))
        flight_path = f"{return_flight['departure']['city']} → {return_flight['arrival']['city']}"
        elements.append(Paragraph(flight_path, styles['Heading4']))
        return_details = Paragraph(
            f"Date: {return_flight['date']}<br/>"
            f"Departure: {return_flight['departure']['city']} ({return_flight['departure']['time']} {return_flight['departure']['timezone']})<br/>"
            f"Arrival: {return_flight['arrival']['city']} ({return_flight['arrival']['time']} {return_flight['arrival']['timezone']})<br/>"
            f"Duration: {return_flight['duration']}<br/>"
            f"Flight Code: {return_flight['flight_code']}<br/>"
            f"Carrier: {return_flight['carrier']}<br/>"
            f"Price: {return_flight['price']}",
            styles['Normal']
        )
        elements.append(return_details)
        # Add space between flights
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
        # Add a horizontal line between flights
        elements.append(HRFlowable(width="80%", thickness=1, color="black"))
        elements.append(Spacer(1, 10))  # Add some space after the line

    def generate_roundtrip_flight_report(self):
        """
        Generates a flight report as a PDF.
        """
        try:
            available_flights, elements, pdf, styles = self.load_flights_and_setup_document()

            self.add_near_and_destination_airports(elements, styles)

            # Represent each flight with text
            for flight in available_flights:
                try:
                    self.add_roundtrip(elements, flight, styles)
                except Exception as e:
                    logger.warning(f"Error adding flight details: {e}")
                    continue

            # Build the PDF
            pdf.build(elements)
            logger.info(f"Report generated: {self.report_path}")
        except Exception as e:
            logger.exception(f"Error generating report: {e}")

    def generate_oneway_flight_report(self):
        """
        Generates a flight report as a PDF.
        """
        try:
            available_flights, elements, pdf, styles = self.load_flights_and_setup_document()

            self.add_near_and_destination_airports(elements, styles)

            # Represent each flight with text
            for flight in available_flights:
                try:
                    outward = flight.get('first_flight', [])[0]
                    return_flight = flight.get('second_flight', [])[0]
                    if compare_times(outward['arrival']['time'],
                                     return_flight['departure']['time'],
                                     outward['date'],
                                     return_flight['date']):
                        continue
                except Exception as e:
                    logger.warning(f"Error extracting flight details: {e}")

                try:
                    outward = self.add_first_flight(elements, flight, outward, styles)
                    self.add_second_flight(elements, flight, outward, styles)

                except Exception as e:
                    logger.warning(f"Error adding flight details: {e}")
                    continue

                # Add space between flights
                elements.append(Paragraph("<br/><br/>", styles['Normal']))

                # Add a horizontal line between flights
                elements.append(HRFlowable(width="80%", thickness=1, color="black"))
                elements.append(Spacer(1, 10))  # Add some space after the line

            # Build the PDF
            pdf.build(elements)
            logger.info(f"Report generated: {self.report_path}")
        except Exception as e:
            logger.error(f"Error generating report: {e}")


# Usage Example
if __name__ == "__main__":
    reporter = ReportService()
    reporter.generate_oneway_flight_report()
