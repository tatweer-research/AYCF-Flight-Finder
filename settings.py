import os
from pathlib import Path
from typing import Optional, Literal, Union

from pydantic import BaseModel, HttpUrl, field_validator, conlist


class GeneralConfig(BaseModel):
    driver_path: Union[str, os.PathLike]
    page_loading_time: int
    action_wait_time: int
    headless: bool = False
    mode: Literal["oneway", "roundtrip"]

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
    destination_airports: Optional[conlist(str, max_length=5)] = None
    departure_airports: Optional[conlist(str, max_length=5)] = None


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
    airport_database_path: Union[str, os.PathLike]
    possible_flights_path: Union[str, os.PathLike]
    checked_flights_path: Union[str, os.PathLike]
    available_flights_path: Union[str, os.PathLike]
    use_cache: bool

    # noinspection PyNestedDecorators
    @field_validator("airport_database_path",
                     "possible_flights_path",
                     "checked_flights_path",
                     "available_flights_path",
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
