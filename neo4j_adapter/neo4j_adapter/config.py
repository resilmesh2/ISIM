from dataclasses import dataclass
from functools import cached_property
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path

import yaml
from dacite import from_dict

from isim_rest.neo4j_rest.settings import BASE_DIR

CONF_DIR = BASE_DIR.parent / "config"


@dataclass
class OrganizationConfig:
    name: str
    domain_names: list[str]
    ip_ranges: list[str]

    def __post_init__(self) -> None:
        [ip_network(subnet) for subnet in self.ip_ranges]  # IP validation.

    @cached_property
    def ipv4_subnets(self) -> list[IPv4Network]:
        return [IPv4Network(subnet) for subnet in self.ip_ranges if ip_network(subnet).version == 4]

    @cached_property
    def ipv6_subnets(self) -> list[IPv6Network]:
        return [IPv6Network(subnet) for subnet in self.ip_ranges if ip_network(subnet).version == 6]


@dataclass
class Config:
    org_config: OrganizationConfig


class OrgConfig:
    _config: Config | None = None

    @classmethod
    def get(cls) -> Config:
        if cls._config is None:
            config_file = BASE_DIR / "config/config.yaml"
            with Path.open(config_file, "r") as f:
                raw_config = yaml.safe_load(f)
            cls._config = from_dict(Config, raw_config)
        return cls._config
