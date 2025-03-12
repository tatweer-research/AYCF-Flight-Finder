import logging
import logging.config
import os
from pathlib import Path
from typing import Optional, Literal, Union

import yaml
from pydantic import BaseModel, HttpUrl, field_validator, conlist


class GeneralConfig(BaseModel):
    driver_path: Union[str, os.PathLike]
    page_loading_time: int
    action_wait_time: int
    rate_limit_wait_time: int
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
    dictConfig: dict


class DataManagerConfig(BaseModel):
    airport_iata_icao_path: Union[str, os.PathLike]
    flight_data_path: Union[str, os.PathLike]
    airport_name_special_cases_path: Union[str, os.PathLike]
    airport_database_iata_path: Union[str, os.PathLike]
    map_iata_to_german_name_path: Union[str, os.PathLike]
    airport_database_path: Union[str, os.PathLike]
    possible_flights_path: Union[str, os.PathLike]
    checked_flights_path: Union[str, os.PathLike]
    available_flights_path: Union[str, os.PathLike]
    use_cache: bool

    # noinspection PyNestedDecorators
    @field_validator("airport_iata_icao_path",
                     "airport_database_path",
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
    logging_config: LoggingConfig
    data_manager: DataManagerConfig
    reporter: ReporterConfig
    scraper: ScraperConfig
    emailer: EmailerConfig


def is_logging_configured():
    root_logger = logging.getLogger()
    return len(root_logger.handlers) > 0


with open('configuration.yaml', 'r', encoding='utf-8') as file:
    config = yaml.safe_load(file)

system_config = ConfigSchema(**config)

if not is_logging_configured():
    logging.config.dictConfig(system_config.logging_config.dictConfig)
    logging.info('Configuration file loaded successfully')
