import copy
import uuid
from datetime import datetime
from pathlib import Path
import datetime as dt
import streamlit as st

from services import FlightFinderService
from services.data_manager import data_manager, logger
from email_validator import validate_email, EmailNotValidError


class NoDepartureAirportsSelected(Exception):
    pass


class NoDestinationAirportsSelected(Exception):
    pass


class DuplicateJobError(Exception):
    pass


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
    except NoDepartureAirportsSelected as e:
        st.error(f'Please select at least one departure airport.')
        logger.error(f'No departure airports selected.')
    except DuplicateJobError as e:
        st.error("A similar job has already been submitted. Please wait until you receive the results via email.")
        logger.error(f'Duplicate job detected.')
    except NoDestinationAirportsSelected as e:
        st.error(f'In the case of one-stop flights you need to select at least one destination airport.')
        logger.error(f'No destination airports selected.')


st.write("**Note**: this website is only useful if you possess the [*WizzAir All You Can Fly Pass*]("
         "https://www.wizzair.com/en-gb/information-and-services/memberships/all-you-can-fly). If you don't, "
         "please use the [regular WizzAir website](https://www.wizzair.com/en-gb).")

