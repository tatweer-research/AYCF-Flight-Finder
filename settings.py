import os
from pathlib import Path
from typing import Optional, Literal, Union

from pydantic import BaseModel, field_validator, conlist


class GeneralConfig(BaseModel):
    driver_path: str
    page_loading_time: int
    action_wait_time: int
    rate_limit_wait_time: int
    headless: bool = False
    mode: Literal["oneway", "roundtrip"]
    time_stamp: Optional[str] = None


class AccountConfig(BaseModel):
    username: str
    password: str
    wizzair_url: str


class FlightDataConfig(BaseModel):
    max_stops: Literal[0, 1]
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    destination_airports: Optional[conlist(str, max_length=5)] = None
    departure_airports: Optional[conlist(str, max_length=5)] = None


class LoggingConfig(BaseModel):
    log_level_file: str
    log_level_console: str
    log_file: str
    date_format: str
    log_format: str


class DataManagerConfig(BaseModel):
    airport_database_path: str
    possible_flights_path: str
    checked_flights_path: str
    available_flights_path: str
    use_cache: bool


class ReporterConfig(BaseModel):
    report_path: str
    logo_path: str


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
