import copy
import datetime as dt
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from email_validator import validate_email, EmailNotValidError
from streamlit_folium import st_folium

from services import FlightFinderService
from services.data_manager import data_manager

logger = logging.getLogger(__name__)


class NoDepartureAirportsSelected(Exception):
    pass


class NoDestinationAirportsSelected(Exception):
    pass


class DuplicateJobError(Exception):
    pass


# Set page configuration
st.set_page_config(page_title="Wizz Flight Finder", page_icon="✈️")

# Create tabs
tab1, tab2 = st.tabs(["Custom Search", "Live Flight Browser"])

# --- Tab 1: Custom Search (Existing Functionality) ---
with tab1:
    st.title("All You Can Fly Pass - WizzAir")
    st.write("\n")

    # Checkbox to enable/disable date selection
    all_possible_dates = st.checkbox("Check all possible dates (next 3 days)")

    # Date input field (only shown if checkbox is unchecked)
    if not all_possible_dates:
        selected_date = st.date_input(
            "Select your departure date (only applicable for **one-way** flights):",
            dt.date.today(),
            min_value=dt.date.today(),
            max_value=dt.date.today() + dt.timedelta(days=3),
            format="DD-MM-YYYY",
        )
    else:
        selected_date = st.date_input(
            "Select your departure date (only applicable for one-way flights):",
            None,
            min_value=dt.date.today(),
            max_value=dt.date.today() + dt.timedelta(days=3),
            format="DD-MM-YYYY",
            disabled=True,
        )

    # Add an option to choose between direct or ones-stop flights
    stops = st.radio("Stops:", ('Direct', 'One-Stop'))

    # Add an option to choose between one-way or round trip
    trip_type = st.radio("Trip Type:", ('One Way', 'Round Trip'))

    # Define the list of options
    options = sorted(data_manager.get_all_airports())

    departure_airports = st.multiselect(
        'Departure Airports:',
        options,
        max_selections=5
    )

    arrival_airports = st.multiselect(
        'Destination Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5
    )

    # Prompt user for email input
    email = st.text_input('Enter your email address (it is needed to send you the pdf report):')

    def get_new_config():
        config = copy.deepcopy(system_config)
        config.flight_data.departure_airports = departure_airports
        config.flight_data.destination_airports = arrival_airports
        config.emailer.recipient = email
        config.general.mode = trip_type.lower().replace(' ', '')
        config.general.time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        config.flight_data.max_stops = 1 if stops == 'One-Stop' else 0
        config.flight_data.departure_date = selected_date.strftime("%d-%m-%Y") if selected_date else None
        return config

    def get_scraping_time():
        config = get_new_config()
        flight_finder = FlightFinderService(config)
        data_manager._reset_databases()
        if trip_type == 'Round Trip':
            flight_finder.find_possible_roundtrip_flights_from_departure_airports()
        else:
            flight_finder.find_possible_one_stop_flights(max_stops=config.flight_data.max_stops)
        estimated_time = flight_finder.get_estimated_checking_time(data_manager.get_possible_flights()['possible_flights'])
        return estimated_time

    def check_for_duplicate_jobs():
        directory = Path('jobs')
        yaml_files = list(directory.rglob('*.yaml')) + list(directory.rglob('*.yml'))
        for file in yaml_files:
            job = data_manager.load_data(file)
            departure_date = selected_date.strftime("%d-%m-%Y") if selected_date else None
            if (job['flight_data']['departure_airports'] == departure_airports and
                job['flight_data']['destination_airports'] == arrival_airports and
                job['general']['mode'] == trip_type.lower().replace(' ', '') and
                job['emailer']['recipient'] == email and
                job['flight_data']['max_stops'] == (1 if stops == 'One-Stop' else 0) and
                job['flight_data']['departure_date'] == departure_date):
                raise DuplicateJobError()


    # Validate email when the user submits the form
    if st.button('Submit'):
        try:
            if not departure_airports:
                raise NoDepartureAirportsSelected()
            if not arrival_airports and stops == 'One-Stop':
                raise NoDestinationAirportsSelected()

            # Validate the email
            valid = validate_email(email)
            email = valid.email
            check_for_duplicate_jobs()

            file_name = f'{uuid.uuid4()}.yaml'
            data_manager.save_data(get_new_config(), f'jobs/{file_name}')
            estimated_time = get_scraping_time()
            st.success(f'Your request has been received. I will notify you with the results at {email} and will be done '
                       f'in about {estimated_time} 😎')
        except EmailNotValidError as e:
            st.error(f'Invalid email address: {e}')
            logger.error(f'Invalid email address: {e}')
        except NoDepartureAirportsSelected:
            st.error('Please select at least one departure airport.')
            logger.error('No departure airports selected.')
        except DuplicateJobError:
            st.error("A similar job has already been submitted. Please wait until you receive the results via email.")
            logger.error('Duplicate job detected.')
        except NoDestinationAirportsSelected:
            st.error('In the case of one-stop flights you need to select at least one destination airport.')
            logger.error('No destination airports selected.')

    st.write("**Note**: this website is only useful if you possess the [*WizzAir All You Can Fly Pass*]("
             "https://www.wizzair.com/en-gb/information-and-services/memberships/all-you-can-fly). If you don’t, "
             "please use the [regular WizzAir website](https://www.wizzair.com/en-gb).")

# --- Tab 2: Live Flight Browser (New Functionality) ---
with tab2:
    # TODO: use https://github.com/ip2location/ip2location-iata-icao/blob/master/iata-icao.csv to get the airport coordinates
    # TODO: use the functions find_available_roundtrip_flights and find_available_oneway_flights to get the available flights
    # TODO: instead of the table, implement small banners (like every other flight site)
    st.header("Live Flight Browser")
    st.write("Explore all available WizzAir flights for the next few days. Select airports and dates to filter the results.")

    # Load checked flights YAML
    checked_flights_path = "data/checked_flights_oneway.yaml"
    checked_flights = data_manager.load_data(checked_flights_path)['checked_flights']

    # Parse YAML into a list of flights
    flights_list = []
    for key, value in checked_flights.items():
        if value is not None:
            for flight in value:
                date_str = flight['date']
                flight_date = datetime.strptime(date_str, "%a %d, %B %Y")
                flights_list.append({
                    "departure_city": flight["departure"]["city"],
                    "arrival_city": flight["arrival"]["city"],
                    "date": flight_date,
                    "departure_time": flight["departure"]["time"],
                    "arrival_time": flight["arrival"]["time"],
                    "flight_code": flight["flight_code"],
                    "price": flight["price"],
                    "duration": flight["duration"]
                })

    # Convert to DataFrame
    flights_df = pd.DataFrame(flights_list)

    # Unique airports for filters
    departure_options = sorted(flights_df["departure_city"].unique())
    arrival_options = sorted(flights_df["arrival_city"].unique())

    # Filters
    selected_departures = st.multiselect("Select departure airports:", departure_options, default=departure_options[:1])
    selected_arrivals = st.multiselect("Select destination airports (optional):", arrival_options)
    min_date = flights_df["date"].min().date()
    max_date = flights_df["date"].max().date()
    date_range = st.date_input("Select date range:", [min_date, max_date], min_value=min_date, max_value=max_date)

    # Filter DataFrame
    filtered_df = flights_df[
        (flights_df["departure_city"].isin(selected_departures)) &
        (flights_df["arrival_city"].isin(selected_arrivals) if selected_arrivals else True) &
        (flights_df["date"].dt.date >= date_range[0]) &
        (flights_df["date"].dt.date <= date_range[1])
    ]

    # Map Visualization
    m = folium.Map(location=[30, 30], zoom_start=3)  # Centered on Europe/Middle East

    # Airport coordinates (replace with actual data from data_manager if available)
    # Example format: {"London Luton": (51.8747, -0.3683), "Amman": (31.7226, 35.9932)}
    airport_coords = {
        "London Luton": (51.8747, -0.3683),
        "Amman": (31.7226, 35.9932),
        "Abu Dhabi": (24.4539, 54.3773),
        "Malé (Malediven)": (4.1755, 73.5093)
        # Add more airports as needed
    }

    # Group flights by route
    routes = filtered_df.groupby(["departure_city", "arrival_city"])
    for (dep, arr), group in routes:
        if dep in airport_coords and arr in airport_coords:
            dep_coords = airport_coords[dep]
            arr_coords = airport_coords[arr]
            # Draw route line
            folium.PolyLine(
                locations=[dep_coords, arr_coords],
                color="blue",
                weight=2.5,
                opacity=0.3
            ).add_to(m)
            # Create popup content
            popup_content = "<table style='width:200px'><tr><th>Date</th><th>Code</th><th>Price</th></tr>"
            for _, row in group.iterrows():
                popup_content += f"<tr><td>{row['date'].strftime('%d-%m-%Y')}</td><td>{row['flight_code']}</td><td>{row['price']}</td></tr>"
            popup_content += "</table>"
            # Add popup at route midpoint
            midpoint = [(dep_coords[0] + arr_coords[0]) / 2, (dep_coords[1] + arr_coords[1]) / 2]
            folium.Marker(
                location=midpoint,
                popup=folium.Popup(popup_content, max_width=300),
                icon=folium.Icon(color="white", icon_color="white", opacity=0.1)  # Hidden marker
            ).add_to(m)

    # Display map
    st_folium(m, width=700, height=400)

    # Display filtered flights table
    st.subheader("Flight Details")
    st.dataframe(filtered_df[["departure_city", "arrival_city", "date", "departure_time", "arrival_time", "flight_code", "price", "duration"]])

    # Data freshness
    last_updated = time.ctime(os.path.getmtime(checked_flights_path))
    st.write(f"*Data last updated: {last_updated}*")
