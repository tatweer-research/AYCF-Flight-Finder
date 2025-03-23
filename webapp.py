import copy
import datetime as dt
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from email_validator import validate_email, EmailNotValidError

from main import check_possible_flights_workflow, check_available_flights
from services import FlightFinderService, logger
from services.data_manager import data_manager
from settings import ConfigSchema
from utils import render_flight_banner, get_last_modification_datetime, create_footer


class NoAirportsSelected(Exception):
    pass


class OneAirportNotSelected(Exception):
    pass


class DuplicateJobError(Exception):
    pass


st.set_page_config(page_title="Wizz Flight Finder", page_icon="✈️")
st.title("Wizz AYCF Scanner 🚀")
st.markdown(
    '<small>An app by <a href="https://tatweer.network/" target="_blank" style="text-decoration: none; color: #4A90E2;">Tatweer®</a></small>',
    unsafe_allow_html=True
)

# Create tabs
tab1, tab2 = st.tabs(["PDF Report", "Immediate Results (Beta)"])


def get_new_config(no_email=False) -> ConfigSchema:
    config = copy.deepcopy(data_manager.config)
    config.flight_data.departure_airports = departure_airports
    config.flight_data.destination_airports = arrival_airports
    if not no_email:
        config.emailer.recipient = email
    config.general.mode = trip_type.lower().replace(' ', '')
    config.general.time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config.flight_data.max_stops = 1 if stops == 'One-Stop' else 0
    config.flight_data.departure_date = selected_date.strftime("%d-%m-%Y") if selected_date else None
    return config


# --- Tab 1: Custom Search (Existing Functionality) ---
with tab1:
    st.header("Get a Fresh Flight Report by Email")
    st.write(
        "This option goes directly to the WizzAir website and checks flights based on your settings. "
        "It takes a bit longer but gives you the most accurate and up-to-date results. "
        "You'll receive a full PDF report by email once it's done."
    )

    # Checkbox to enable/disable date selection
    all_possible_dates = st.checkbox("Check all possible dates (next 3 days)", key="tab1_checkbox")

    # Date input field (only shown if checkbox is checked)
    if not all_possible_dates:
        selected_date = st.date_input(
            "Select your departure date (only applicable for **one-way** flights):",
            dt.date.today(),
            min_value=dt.date.today(),
            max_value=dt.date.today() + dt.timedelta(days=3),
            format="DD-MM-YYYY",
            key="tab1_date1"
        )
    else:
        selected_date = st.date_input(
            "Select your departure date (only applicable for one-way flights):",
            None,
            min_value=dt.date.today(),
            max_value=dt.date.today() + dt.timedelta(days=3),
            format="DD-MM-YYYY",
            disabled=True,
            key="tab1_date2"
        )

    # Add an option to choose between direct or ones-stop flights
    stops = st.radio(
        "Max Stops:",
        ('Direct', 'One-Stop'),
        key="tab1_radio_stops"
    )

    # Add an option to choose between one-way or round trip
    trip_type = st.radio(
        "Trip Type:",
        ('One Way', 'Round Trip'),
        key="tab1_radio_trip_type"
    )

    # Define the list of options
    options = sorted(data_manager.get_all_airports())

    departure_airports = st.multiselect(
        'Departure Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5,
        key="tab1_multiselect_depair"
    )

    arrival_airports = st.multiselect(
        'Destination Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5,
        key="tab1_multiselect_arrair"
    )

    # Prompt user for email input
    email = st.text_input('Enter your email address (it is needed to send you the pdf report):')


    def get_scraping_time():
        config = get_new_config()
        flight_finder = FlightFinderService(config)
        data_manager._reset_databases()
        if trip_type == 'Round Trip':
            flight_finder.find_possible_roundtrip_flights_from_departure_airports()
        else:
            flight_finder.find_possible_one_stop_flights(max_stops=config.flight_data.max_stops)
        estimated_time = flight_finder.get_estimated_checking_time(
            data_manager.get_possible_flights()['possible_flights'])
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


    def validate_user_inputs():
        if not departure_airports and not arrival_airports:
            raise NoAirportsSelected()

        if (not arrival_airports or not departure_airports) and stops == 'One-Stop':
            raise OneAirportNotSelected()

        try:
            valid = validate_email(email)
        except EmailNotValidError as e:
            raise EmailNotValidError(f"Invalid email address: {e}")

        check_for_duplicate_jobs()
        return valid.email


    # Validate email when the user submits the form
    if st.button('Submit', key="tab1_button_submit"):
        try:
            email = validate_user_inputs()

            file_name = f'{uuid.uuid4()}.yaml'
            data_manager.save_config(get_new_config(), f'jobs/{file_name}')
            estimated_time = get_scraping_time()
            st.success(
                f'Your request has been received. I will notify you with the results at {email} and will be done '
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

# --- Tab 2: Static Flight Browser ---
with tab2:
    st.header("See Saved Flights Instantly")
    st.write(
        "This shows you flights that were fetched in the last 2.5 hours. It's super fast, but some results "
        "might be outdated or no longer available. Use it if you want a quick overview without waiting."
    )

    # Load checked flights YAML
    latest_scraper_output_mod_time = get_last_modification_datetime(
        data_manager.config.data_manager.multi_scraper_output_path
    )

    if "last_scraper_output_mod_time" not in st.session_state or \
            ("last_scraper_output_mod_time" in st.session_state and
             st.session_state.last_scraper_output_mod_time < latest_scraper_output_mod_time) or \
            "checked_flights" not in st.session_state:
        # Update the session state with the latest modification time
        st.session_state.last_scraper_output_mod_time = latest_scraper_output_mod_time

        # Load the latest multi-scraper output data
        scraper_output_data = data_manager.load_data(data_manager.config.data_manager.multi_scraper_output_path)

        # Store checked flights
        checked_flights = scraper_output_data
        st.session_state.checked_flights = checked_flights

    # Checkbox to enable/disable date selection
    all_possible_dates = st.checkbox("Check all possible dates (next 3 days)", key="tab2_checkbox")

    # Date input field (only shown if checkbox is checked)
    if not all_possible_dates:
        selected_date = st.date_input(
            "Select your departure date:",
            dt.date.today(),
            min_value=dt.date.today(),
            max_value=dt.date.today() + dt.timedelta(days=3),
            format="DD-MM-YYYY",
            key="tab2_date1"
        )
    else:
        selected_date = st.date_input(
            "Select your departure date:",
            None,
            min_value=dt.date.today(),
            max_value=dt.date.today() + dt.timedelta(days=3),
            format="DD-MM-YYYY",
            disabled=True,
            key="tab2_date2"
        )

    # Add an option to choose between direct or ones-stop flights
    stops = st.radio(
        "Max Stops:",
        ('Direct', 'One-Stop'),
        key="tab2_radio_stops"
    )

    # Add an option to choose between one-way or round trip
    trip_type = st.radio(
        "Trip Type:",
        ('One Way', 'Round Trip'),
        key="tab2_radio_trip_type"
    )

    # Define the list of options
    options = sorted(data_manager.get_all_airports())

    departure_airports = st.multiselect(
        'Departure Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5,
        key="tab2_multiselect_depair"
    )

    arrival_airports = st.multiselect(
        'Destination Airports (If nothing is selected, I will check for all airports):',
        options,
        max_selections=5,
        key="tab2_multiselect_arrair"
    )

    st.info(f"Data last updated: {st.session_state.last_scraper_output_mod_time.strftime('%Y-%m-%d %H:%M:%S')}",
            icon="ℹ️")

    if st.button('Search', key="tab2_button_submit"):

        # Refresh the data manager config
        data_manager._reset_databases()
        data_manager.load_config()
        data_manager.config = get_new_config(no_email=True)

        # Re-set checked_flights in data_manager
        if selected_date:
            checked_flights = {}
            for hash_str, flight_obj in st.session_state.checked_flights['checked_flights'].items():
                if flight_obj:  # Ensure flight_obj is not empty or None
                    flight_date = datetime.strptime(flight_obj[0]['date'], "%a %d, %B %Y").date()
                    if flight_date == selected_date:
                        checked_flights[hash_str] = flight_obj
            checked_flights = {"checked_flights": checked_flights}
            data_manager.add_checked_flights(checked_flights, save_data=False)
        else:
            data_manager.add_checked_flights(st.session_state.checked_flights, save_data=False)

        # Check possible flights out of the data_manager.__airport_destinations
        check_possible_flights_workflow(data_manager.config.general.mode,
                                        save_data=False,
                                        max_stops=data_manager.config.flight_data.max_stops)

        # Check available flights output of possible flights and checked flights
        check_available_flights(data_manager.config.general.mode, save_data=False)
        available_flights = data_manager.get_available_flights()
        flight_list = available_flights.get("available_flights", [])


        # Function to extract the departure date based on trip type
        def get_departure_date(itinerary):
            # Determine which flight key to use based on trip type
            if data_manager.config.general.mode == "oneway":
                initial_flight = itinerary.get("first_flight", [])
            elif data_manager.config.general.mode == "roundtrip":
                initial_flight = itinerary.get("outward_flight", [])
            else:
                return None  # Return None for unrecognized modes

            # Extract the date from the first segment of the initial flight
            if initial_flight:
                first_segment = initial_flight[0]
                date_str = first_segment.get("date", "")
                try:
                    # Parse the date string (e.g., "Sun 16, March 2025")
                    return dt.datetime.strptime(date_str, "%a %d, %B %Y")
                except ValueError:
                    return None  # Return None if the date format is invalid
            return None  # Return None if there are no segments


        # Sort the flight list by departure date
        flight_list.sort(key=lambda x: get_departure_date(x) or dt.datetime.max)

        # Update the session state with the sorted list
        st.session_state.flight_list = flight_list

    # If there's no data, show a warning
    if 'flight_list' not in st.session_state or \
            ('flight_list' in st.session_state and not st.session_state.flight_list):
        st.warning("No flights found. Try changing some of the filters.")
    else:
        is_round_trip = (data_manager.config.general.mode == "roundtrip")

        # Now display each itinerary
        for idx, itinerary in enumerate(st.session_state.flight_list, start=1):
            # st.subheader(f"Option #{idx}")  # - {'Round Trip' if is_round_trip else 'One Way'}")

            if is_round_trip:
                st.write("-" * 50)
                # For round trip: outward segments + return segments
                outward_segments = itinerary["outward_flight"]
                return_segments = itinerary["return_flight"]

                st.markdown("<strong>Outward Flight</strong>", unsafe_allow_html=True)
                for seg in outward_segments:
                    banner_html = render_flight_banner(seg)
                    st.html(banner_html)

                st.markdown("<strong>Return Flight</strong>", unsafe_allow_html=True)
                for seg in return_segments:
                    banner_html = render_flight_banner(seg)
                    st.html(banner_html)

            else:
                st.write("-" * 50)
                # One-way can have first_flight + second_flight if there's a connection
                first_segments = itinerary.get("first_flight", [])
                second_segments = itinerary.get("second_flight", None)

                # Display first_flight segments
                for seg in first_segments:
                    banner_html = render_flight_banner(seg)
                    st.html(banner_html)

                # If there's a connecting flight
                if second_segments:
                    st.markdown("<em>Connecting Flight</em>", unsafe_allow_html=True)
                    for seg in second_segments:
                        banner_html = render_flight_banner(seg)
                        st.html(banner_html)

create_footer()
