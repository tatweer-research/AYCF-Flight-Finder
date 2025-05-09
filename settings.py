import os
from pathlib import Path
from typing import Optional, Literal, Union, List

from pydantic import BaseModel, HttpUrl, field_validator


class GeneralConfig(BaseModel):
    driver_path: Union[str, os.PathLike]
    page_loading_time: int
    action_wait_time: int
    rate_limit_wait_time: int
    headless: bool = False
    mode: Literal["oneway", "roundtrip"]
    time_stamp: Optional[str] = None

    # noinspection PyNestedDecorators
    @field_validator("driver_path", mode="before")
    @classmethod
    def convert_to_pathlib(cls, v):
        return Path(v)


class AccountConfig(BaseModel):
    username: str
    password: str
    wizzair_url: HttpUrl


class FlightDataConfig(BaseModel):
    max_stops: Literal[0, 1]
    departure_date: Optional[str] = None
    return_date: Optional[str] = None

    # We only need to limit the length of the airports to 5 in the front end.
    # Keep it unlimited here for testing purposes.
    destination_airports: Optional[List[str]] = None
    departure_airports: Optional[List[str]] = None


class LoggingConfig(BaseModel):
    log_level_file: str
    log_level_console: str
    log_file: Union[str, os.PathLike]
    date_format: str
    log_format: str

    # noinspection PyNestedDecorators
    @field_validator("log_file", mode="before")
    @classmethod
    def convert_to_pathlib(cls, v):
        return Path(v)


class DataManagerConfig(BaseModel):
    airport_iata_icao_path: Union[str, os.PathLike]
    flight_data_path: Union[str, os.PathLike]
    airport_name_special_cases_path: Union[str, os.PathLike]
    map_iata_to_german_name_path: Union[str, os.PathLike]
    airport_database_dynamic_path: Union[str, os.PathLike]
    airport_database_path: Union[str, os.PathLike]
    possible_flights_path: Union[str, os.PathLike]
    checked_flights_path: Union[str, os.PathLike]
    available_flights_path: Union[str, os.PathLike]
    multi_scraper_output_path: Union[str, os.PathLike]
    use_cache: bool
    reset_databases: bool
    use_wizz_availability_pdf: bool
    usage_logs_path: Union[str, os.PathLike]

    # noinspection PyNestedDecorators
    @field_validator("airport_iata_icao_path",
                     "flight_data_path",
                     "airport_name_special_cases_path",
                     "map_iata_to_german_name_path",
                     "airport_database_dynamic_path",
                     "airport_database_path",
                     "possible_flights_path",
                     "checked_flights_path",
                     "available_flights_path",
                     "multi_scraper_output_path",
                     "usage_logs_path",
                     mode="before")
    @classmethod
    def convert_to_pathlib(cls, v):
        return Path(v)


class ReporterConfig(BaseModel):
    report_path: Union[str, os.PathLike]
    logo_path: Union[str, os.PathLike]

    # noinspection PyNestedDecorators
    @field_validator("*", mode="before")
    @classmethod
    def convert_to_pathlib(cls, v):
        return Path(v)


class ScraperConfig(BaseModel):
    initialize_driver: bool
    session_uuid: str = "0ee15f1c-1bbf-41de-b89b-95c4e7040a46"  # Default value
    xsrf_token: str = "eyJpdiI6ImhXWmJZNG5VSEVuR1I1cnRzQ1RWaVE9PSIsInZhbHVlIjoic3Y4VThiQnJhUldxM0hjeXllM0NubHd5Z2ZTZlEzVys3N05rY3I5aGJsZExFVjk5NnNQYjNyUUVlMXRWRWdQVFBkaVhvYzlIdHBIRlZ3WStTemFheXc9PSIsIm1hYyI6IjAxOThiYjQ3MWMzNDQzZDVkMDJkYjkyODkyYjU5MTJiNjU0ZTIzNzk5ZTY5NmQ2MGEyMmUyMDgzM2Y2YzgyMTYifQ=="  # Default value


class EmailerConfig(BaseModel):
    recipient: str


class ConfigSchema(BaseModel):
    general: GeneralConfig
    account: AccountConfig
    flight_data: FlightDataConfig
    logging: LoggingConfig
    data_manager: DataManagerConfig
    reporter: ReporterConfig
    scraper: ScraperConfig
    emailer: EmailerConfig
