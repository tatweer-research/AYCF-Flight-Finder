import copy
import datetime as dt
import uuid
from datetime import datetime
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from email_validator import validate_email, EmailNotValidError
from streamlit_folium import st_folium

from services import FlightFinderService
from services.data_manager import data_manager, logger
from settings import ConfigSchema


class NoAirportsSelected(Exception):
    pass


class OneAirportNotSelected(Exception):
    pass


class DuplicateJobError(Exception):
    pass


# Create tabs
tab1, tab2 = st.tabs(["Custom Search", "Live Flight Browser"])


# --- Tab 1: Custom Search (Existing Functionality) ---
with tab1:
    st.set_page_config(page_title="Wizz Flight Finder", page_icon="✈️")

    st.title("All You Can Fly Pass - WizzAir")
    st.write("\n")

    # Checkbox to enable/disable date selection
    all_possible_dates = st.checkbox("Check all possible dates (next 3 days)")

    # Date input field (only shown if checkbox is checked)
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
    stops = st.radio(
        "Stops:",
        ('Direct', 'One-Stop')
    )

    # Add an option to choose between one-way or round trip
    trip_type = st.radio(
        "Trip Type:",
        ('One Way', 'Round Trip')
    )

    # Define the list of options
    options = sorted(data_manager.get_all_airports())

    departure_airports = st.multiselect(
        'Departure Airports (If nothing is selected, I will check for all airports):',
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


    def get_new_config() -> ConfigSchema:
        config = copy.deepcopy(data_manager.config)
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
            if job['flight_data']['departure_airports'] == departure_airports \
                    and job['flight_data']['destination_airports'] == arrival_airports \
                    and job['general']['mode'] == trip_type.lower().replace(' ', '') \
                    and job['emailer']['recipient'] == email \
                    and job['flight_data']['max_stops'] == (1 if stops == 'One-Stop' else 0) \
                    and job['flight_data']['departure_date'] == departure_date:
                raise DuplicateJobError()


    # Validate email when the user submits the form
    if st.button('Submit'):
        try:
            if not departure_airports and not arrival_airports:
                raise NoAirportsSelected()

            if (not arrival_airports or not departure_airports) and stops == 'One-Stop':
                raise OneAirportNotSelected()

            # Validate the email
            valid = validate_email(email)
            email = valid.email
            check_for_duplicate_jobs()

            file_name = f'{uuid.uuid4()}.yaml'
            data_manager.save_config(get_new_config(), f'jobs/{file_name}')
            estimated_time = get_scraping_time()
            st.success(f'Your request has been received. I will notify you with the results at {email} and will be done '
                       f'in about {estimated_time} 😎')
        except EmailNotValidError as e:
            st.error(f'Invalid email address: {e}')
            logger.error(f'Invalid email address: {e}')
        except NoAirportsSelected as e:
            st.error(f'Please select at least one departure or one destination airport.')
            logger.error(f'No departure airports selected.')
        except DuplicateJobError as e:
            st.error("A similar job has already been submitted. Please wait until you receive the results via email.")
            logger.error(f'Duplicate job detected.')
        except OneAirportNotSelected as e:
            st.error(f'In the case of one-stop flights you need to select both departure and destination airports.')
            logger.error(f'No destination airports selected.')


    st.write("**Note**: this website is only useful if you possess the [*WizzAir All You Can Fly Pass*]("
             "https://www.wizzair.com/en-gb/information-and-services/memberships/all-you-can-fly). If you don't, "
             "please use the [regular WizzAir website](https://www.wizzair.com/en-gb).")


# --- Tab 2: Static Flight Browser ---
with tab2:
    # TODO: use the functions find_available_roundtrip_flights and find_available_oneway_flights to get the available flights
    # TODO: instead of the table, implement small banners (like every other flight site)
    st.header("Static Flight Browser")
    st.write("Explore all available WizzAir flights for the next few days based on a static scraper. "
             "Be aware that these flights were calculated based on our scraper that runs every day at 7am, "
             "when WizzAir publishes their available flight connections."
             "So some connections may no be available anymore. Use with caution ;)")

    # Load checked flights YAML
    multi_scraper_output = data_manager.config.data_manager.multi_scraper_output_path
    checked_flights = data_manager.load_data(multi_scraper_output)['checked_flights']


    # Checkbox to enable/disable date selection
    all_possible_dates = st.checkbox("Check all possible dates (next 3 days)")

    # Date input field (only shown if checkbox is checked)
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
    stops = st.radio(
        "Stops:",
        ('Direct', 'One-Stop')
    )

    # Add an option to choose between one-way or round trip
    trip_type = st.radio(
        "Trip Type:",
        ('One Way', 'Round Trip')
    )

    # Define the list of options
    options = sorted(data_manager.get_all_airports())

    departure_airports = st.multiselect(
        'Departure Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5
    )

    arrival_airports = st.multiselect(
        'Destination Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5
    )

    if st.button('Submit'):
        # Refresh the data manager config
        data_manager.load_config()
        data_manager.config.flight_data.departure_airports = departure_airports
        data_manager.config.flight_data.destination_airports = arrival_airports
        data_manager.config.general.mode = trip_type.lower().replace(' ', '')
        data_manager.config.general.time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_manager.config.flight_data.max_stops = 1 if stops == 'One-Stop' else 0
        data_manager.config.flight_data.departure_date = selected_date.strftime("%d-%m-%Y") if selected_date else None

        # TODO: marker

        # Map Visualization
        m = folium.Map(location=[30, 30], zoom_start=3)  # Centered on Europe/Middle East

        # Airport coordinates
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
