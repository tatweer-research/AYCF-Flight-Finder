import re
from datetime import datetime, timedelta

import pytz
import streamlit as st


def increment_date(date_str, days=1):
    """
    Increment a given date in the format DD-MM-YYYY by a predefined number of days.

    :param date_str: str, date in DD-MM-YYYY format
    :param days: int, number of days to increment (default is 1)
    :return: str, incremented date in DD-MM-YYYY format
    """
    # Parse the input date string into a datetime object
    date_format = "%d-%m-%Y"
    date_obj = datetime.strptime(date_str, date_format)

    # Increment the date by the specified number of days
    next_date = date_obj + timedelta(days=days)

    # Return the new date formatted as DD-MM-YYYY
    return next_date.strftime(date_format)


def is_date_in_range(date_str, start_date_str, end_date_str):
    """
    Check if a given date is within a specified date range.

    :param date_str: str, date to check in DD-MM-YYYY format
    :param start_date_str: str, start of the range in DD-MM-YYYY format
    :param end_date_str: str, end of the range in DD-MM-YYYY format
    :return: bool, True if the date is within the range, False otherwise
    """
    # Define the date format
    date_format = "%d-%m-%Y"

    # Convert strings to datetime objects
    date = datetime.strptime(date_str, date_format)
    start_date = datetime.strptime(start_date_str, date_format)
    end_date = datetime.strptime(end_date_str, date_format)

    # Check if the date is within the range (inclusive)
    return start_date <= date <= end_date


def compare_times(time1, time2, date1=None, date2=None):
    """
    Compare two times, optionally with dates.

    :param time1: First time as a string in HH:MM format
    :param time2: Second time as a string in HH:MM format
    :param date1: First date as string in format "Sat 28, December 2024" (optional)
    :param date2: Second date as string in format "Fri 27, December 2024" (optional)
    :return: True if time1 > time2, False otherwise
    """
    # If dates are provided, compare full datetime
    if date1 and date2:
        # Convert date strings to datetime objects
        datetime1 = datetime.strptime(f"{date1} {time1}", "%a %d, %B %Y %H:%M")
        datetime2 = datetime.strptime(f"{date2} {time2}", "%a %d, %B %Y %H:%M")
        if not datetime1 == datetime2:
            return datetime1 > datetime2

    # If no dates, just compare times
    hours1, minutes1 = map(int, time1.split(":"))
    hours2, minutes2 = map(int, time2.split(":"))

    if hours1 > hours2:
        return True
    elif hours1 == hours2 and minutes1 > minutes2:
        return True
    else:
        return False


def get_timezone_name(tz_str):
    """
    Convert UTC+X format to timezone name.

    Args:
        tz_str (str): Timezone string in UTC+X format

    Returns:
        str: Standard timezone name
    """
    if tz_str == "UTC":
        return "UTC"

    # Extract offset from UTC+X or UTC-X format
    offset = int(tz_str.replace("UTC", "").replace("+", ""))

    # Create timezone string
    if offset >= 0:
        return f"Etc/GMT-{offset}"  # Note: Etc/GMT uses opposite sign
    else:
        return f"Etc/GMT+{abs(offset)}"


def calculate_arrival_date(flight_data: dict) -> str:
    """
    Calculate the arrival date and time given flight departure and duration information.

    Args:
        flight_data (dict): Dictionary containing flight information

    Returns:
        str: Arrival date in the format 'Day DD, Month YYYY'
    """
    # Parse departure date and time
    dep_date_str = flight_data['date']
    dep_time_str = flight_data['departure']['time']

    # Combine date and time strings
    dep_datetime_str = f"{dep_date_str} {dep_time_str}"

    # Parse departure datetime
    departure_datetime = datetime.strptime(dep_datetime_str, "Wed %d, %B %Y %H:%M")

    # Get timezone objects
    dep_tz = pytz.timezone(get_timezone_name(flight_data['departure']['timezone']))
    arr_tz = pytz.timezone(get_timezone_name(flight_data['arrival']['timezone']))

    # Localize departure datetime
    departure_datetime = dep_tz.localize(departure_datetime)

    # Parse duration
    duration_str = flight_data['duration']
    hours, minutes = map(int, duration_str.replace('h ', ':').replace('m', '').split(':'))
    duration = timedelta(hours=hours, minutes=minutes)

    # Calculate arrival datetime in departure timezone
    arrival_datetime = departure_datetime + duration

    # Convert to arrival timezone
    arrival_datetime = arrival_datetime.astimezone(arr_tz)

    # Format arrival date
    return arrival_datetime.strftime("%a %d, %B %Y")


def calculate_waiting_time(start_time, end_time, start_date=None, end_date=None):
    """
    Calculate the waiting time between two times, optionally with dates.

    :param start_time: The start time as a string in HH:MM format
    :param end_time: The end time as a string in HH:MM format
    :param start_date: Start date as string in format "Sat 28, December 2024" (optional)
    :param end_date: End date as string in format "Fri 27, December 2024" (optional)
    :return: The duration as a string in the format "duration: XXh XXm"
    """
    if start_date and end_date:
        # Convert datetime strings to datetime objects
        start_datetime = datetime.strptime(f"{start_date} {start_time}", "%a %d, %B %Y %H:%M")
        end_datetime = datetime.strptime(f"{end_date} {end_time}", "%a %d, %B %Y %H:%M")

        # Calculate time difference in minutes
        time_diff = end_datetime - start_datetime
        waiting_minutes = int(time_diff.total_seconds() / 60)

    else:
        # Original time-only logic
        start_hours, start_minutes = map(int, start_time.split(":"))
        end_hours, end_minutes = map(int, end_time.split(":"))

        start_total_minutes = start_hours * 60 + start_minutes
        end_total_minutes = end_hours * 60 + end_minutes

        if end_total_minutes < start_total_minutes:
            end_total_minutes += 24 * 60

        waiting_minutes = end_total_minutes - start_total_minutes

    # Convert the waiting time to hours and minutes
    waiting_hours = abs(waiting_minutes) // 60
    waiting_remaining_minutes = abs(waiting_minutes) % 60

    # Format the output
    return f"{waiting_hours:02}h {waiting_remaining_minutes:02}m"


def calculate_waiting_time_deprecated(start_time, end_time, start_timezone="UTC", end_timezone="UTC",
                                      start_date=None, end_date=None):
    """
    Calculate the waiting time between two times, considering different timezones.

    Args:
        start_time (str): The start time as a string in HH:MM format
        end_time (str): The end time as a string in HH:MM format
        start_timezone (str): Timezone for start time (default: "UTC")
        end_timezone (str): Timezone for end time (default: "UTC")
        start_date (str): Start date as string in format "Sat 28, December 2024" (optional)
        end_date (str): End date as string in format "Fri 27, December 2024" (optional)

    Returns:
        str: The duration as a string in the format "XXh XXm"
    """
    # Convert timezone strings to pytz timezone objects
    start_tz = pytz.timezone(get_timezone_name(start_timezone))
    end_tz = pytz.timezone(get_timezone_name(end_timezone))

    if start_date and end_date:
        # Convert datetime strings to datetime objects with timezone
        start_datetime = datetime.strptime(f"{start_date} {start_time}", "%a %d, %B %Y %H:%M")
        end_datetime = datetime.strptime(f"{end_date} {end_time}", "%a %d, %B %Y %H:%M")

        # Localize the datetime objects
        start_datetime = start_tz.localize(start_datetime)
        end_datetime = end_tz.localize(end_datetime)

        # Convert both times to UTC for comparison
        start_datetime_utc = start_datetime.astimezone(pytz.UTC)
        end_datetime_utc = end_datetime.astimezone(pytz.UTC)

        # Calculate time difference in minutes
        time_diff = end_datetime_utc - start_datetime_utc
        waiting_minutes = int(time_diff.total_seconds() / 60)

    else:
        # Create today's date for both times
        today = datetime.now().date()

        # Create datetime objects with timezone
        start_datetime = start_tz.localize(
            datetime.combine(today, datetime.strptime(start_time, "%H:%M").time())
        )
        end_datetime = end_tz.localize(
            datetime.combine(today, datetime.strptime(end_time, "%H:%M").time())
        )

        # Convert both times to UTC for comparison
        start_datetime_utc = start_datetime.astimezone(pytz.UTC)
        end_datetime_utc = end_datetime.astimezone(pytz.UTC)

        # If end time is earlier than start time, add one day to end time
        if end_datetime_utc < start_datetime_utc:
            end_datetime = end_tz.localize(
                datetime.combine(today + timedelta(days=1),
                                 datetime.strptime(end_time, "%H:%M").time())
            )
            end_datetime_utc = end_datetime.astimezone(pytz.UTC)

        # Calculate time difference in minutes
        time_diff = end_datetime_utc - start_datetime_utc
        waiting_minutes = int(time_diff.total_seconds() / 60)

    # Convert the waiting time to hours and minutes
    waiting_hours = abs(waiting_minutes) // 60
    waiting_remaining_minutes = abs(waiting_minutes) % 60

    # Format the output
    return f"{waiting_hours:02}h {waiting_remaining_minutes:02}m"


def format_seconds(seconds):
    days = seconds // (24 * 3600)
    seconds %= 24 * 3600
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60

    result = ""
    if days > 0:
        result += f"{days} day{'s' if days > 1 else ''}, "
    if hours > 0:
        result += f"{hours} hour{'s' if hours > 1 else ''}, "
    if minutes > 0:
        result += f"{minutes} minute{'s' if minutes > 1 else ''}, "
    if seconds > 0:
        result += f"{seconds} second{'s' if seconds > 1 else ''}"

    return result


def sum_flight_durations(durations):
    total_minutes = 0

    for duration in durations:
        parts = duration.split('h ')
        if len(parts) == 1:
            hours = 0
            minutes = int(parts[0].split('m')[0])
        else:
            hours = int(parts[0])
            minutes = int(parts[1].split('m')[0])

        total_minutes += hours * 60 + minutes

    total_hours = total_minutes // 60
    total_minutes %= 60

    return f"{total_hours:02d}h {total_minutes:02d}m"


def get_current_date():
    """Returns the current date in DD-MM-YYYY format."""
    return datetime.now().strftime('%d-%m-%Y')


def make_hashable(item):
    """
    Recursively converts a dictionary, list, or other structure into a hashable equivalent.
    - Lists are converted to tuples.
    - Dictionaries are converted to frozensets of (key, value) pairs, where values are also made hashable.
    """
    if isinstance(item, dict):
        return frozenset((key, make_hashable(value)) for key, value in item.items())
    elif isinstance(item, list):
        return tuple(make_hashable(sub_item) for sub_item in item)
    else:
        return item  # Return the item directly if it's already hashable


def remove_duplicates_from_list(data_list, key_extractor=None):
    """
    Removes duplicate dictionaries from a list based on a unique key.

    :param data_list: List of dictionaries to remove duplicates from.
    :param key_extractor: Optional function to extract a unique key from each dictionary.
                          If None, the entire dictionary is used as the key.
    :return: A list with duplicates removed.
    """
    seen = set()
    unique_list = []

    for item in data_list:
        # Use the key extractor or make the dictionary hashable
        unique_key = key_extractor(item) if key_extractor else make_hashable(item)

        if unique_key not in seen:
            seen.add(unique_key)
            unique_list.append(item)

    return unique_list


def paypal_support():
    # Support
    st.write("""
------------------------------------
**Support This Web App** 💙  

I created this web app as a free tool for everyone to use. As the server and development costs grow, your support can help keep it running and improve it further.  

If you find this app helpful and would like to contribute, you can support it via PayPal

Thank you for your support! 🙌  
""")
    import base64
    # Path to your image
    image_path = "data/paypalme.png"

    # Function to encode image as Base64
    def get_base64_encoded_image(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()

    # Get the encoded image
    base64_image = get_base64_encoded_image(image_path)
    # PayPal donation link
    paypal_link = "https://www.paypal.com/donate/?hosted_button_id=K9493GVFLSYFY"
    # HTML code for the clickable image button
    button_html = f"""
    <style>
        .image-button {{
            display: inline-block;
            border: 1px solid black;  /* Black border */
            padding: 5px;
            border-radius: 15px; /* Rounded corners */
            text-align: center;
            text-decoration: none;
        }}
        .image-button img {{
            width: 200px; /* Adjust size */
            height: auto;
            border-radius: 10px; /* Rounded corners for image too */
        }}
    </style>

    <a class="image-button" href="{paypal_link}" target="_blank">
        <img src="data:image/png;base64,{base64_image}" alt="Pay Now">
    </a>
"""
    # Render in Streamlit
    st.markdown(button_html, unsafe_allow_html=True)


def get_iata_code(airport_name):
    """
    Get the IATA code for a given airport name.

    Args:
        airport_name (str): Name of the airport

    Returns:
        str: IATA code for the airport
    """
    return airport_name.split(" ")[-1].replace("(", "").replace(")", "")


def get_city(airport_name):
    """
    Get the city name from the airport name.

    Args:
        airport_name (str): Name of the airport

    Returns:
        str: City name
    """
    return airport_name.split(" (")[0]


def create_custom_yamls():
    """
    This is the script used to create the files airport_database_iata.yaml and map_iata_to_german_name.yaml
    """
    routes_db = {}  # dictionary mapping, e.g. {"ABZ": ["GDN"], "AUH": ["HBE", "ALA", "AMM"], ...}
    current_departure_iata = None
    map_german_name_to_iata = set()

    with open("data/airport_database.yaml", "r", encoding="utf-8") as f:
        airport_db_raw = f.read()

    for raw_line in airport_db_raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Check if this line is a "Departure" line with a colon
        if line.endswith(":"):
            # e.g. "Abu Dhabi (AUH):"
            dep_name, dep_iata = parse_airport_line(line)
            if dep_iata:
                current_departure_iata = dep_iata
                routes_db[current_departure_iata] = []
                map_german_name_to_iata.add((dep_iata, dep_name))
        else:
            # arrival line
            arr_name, arr_iata = parse_destination_line(line)
            if arr_iata and current_departure_iata:
                routes_db[current_departure_iata].append(arr_iata)
                map_german_name_to_iata.add((arr_iata, arr_name))

    iata_to_german = {iata: name for iata, name in map_german_name_to_iata}
    # save_data(iata_to_german, 'data/map_iata_to_german_name.yaml')  # Save as YAML
    # save_data(routes_db, 'data/airport_database_iata.yaml')  # Save as YAML


def split_words(name):
    """
    Split the given airport name into a list of lowercase words (no punctuation).
    E.g. "Abu Dhabi" -> ["abu", "dhabi"]
         "Basel/Mulhouse" -> ["basel", "mulhouse"]
    """
    return re.findall(r"[A-Za-z0-9]+", name.lower())


def is_complete_word_match(json_airport_name, csv_airport_name):
    """
    Checks if all words of 'json_airport_name' appear as whole words in 'csv_airport_name'.
    """
    # Split both into lists of words (lowercase).
    json_words = split_words(json_airport_name)
    csv_words = split_words(csv_airport_name)

    # We want every word from json_airport_name to appear in the CSV name's list of words:
    return all(word in csv_words for word in json_words)


def find_possible_csv_matches(airport_name, df_csv):
    """
    Returns all rows of df_csv where 'airport' is a *complete-word match* for airport_name.
    If nothing found, returns an empty DataFrame.
    """
    matched_rows = df_csv[df_csv["airport"].apply(
        lambda x: is_complete_word_match(airport_name, x)
    )]
    return matched_rows


def parse_airport_line(line):
    """
    Given something like:
       'Aberdeen (ABZ):'
    return ('Aberdeen', 'ABZ')
    """
    # Regex to match:   Some Name (IATA):
    match = re.match(r"^(.*?) \(([^()]+)\):$", line.strip())
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


def parse_destination_line(line):
    """
    Given something like:
       '- Danzig (GDN)'
    return ('Danzig', 'GDN')
    """
    match = re.match(r"^- (.*?) \(([^()]+)\)$", line.strip())
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


if __name__ == '__main__':
    name = "Budapest (BUD)"
    print(get_iata_code(name))  # Output: BUD
