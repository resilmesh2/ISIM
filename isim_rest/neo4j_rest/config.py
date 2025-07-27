from configparser import ConfigParser
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
from pathlib import Path

import yaml
from dacite import from_dict

from isim_rest.neo4j_rest.settings import BASE_DIR

CONF_DIR = BASE_DIR.parent / "config"


@dataclass
class Neo4jConfig:
    password: str
    bolt: str = "bolt://localhost:7687"
    user: str = "neo4j"


@dataclass
class Host:
    ip_address: str
    domain_names: list[str] = field(default_factory=list)
    subnets: list[str] = field(default_factory=list)
    uris: list[str] = field(default_factory=list)
    version: int = 4

    def __post_init__(self) -> None:
        ip_interface_object = ip_address(self.ip_address)
        for s in self.subnets:
            if ip_interface_object not in (network_object := ip_network(s)):
                raise ValueError(f"Declared {ip_interface_object.compressed} is not in subnet {network_object.compressed}")
        self.version = ip_interface_object.version


@dataclass
class OrganizationConfig:
    name: str
    hosts: list[Host]


@dataclass
class Config:
    neo4j_config: Neo4jConfig
    org_config: OrganizationConfig


class AppConfig:
    _config: Config | None = None

    @classmethod
    def get(cls, config_path: Path | None = None, org_config_path: Path | None = None) -> Config:
        config_parser = ConfigParser()
        if cls._config is None:
            if config_path is None:  # pragma: no cover
                config_path = CONF_DIR / "conf.ini"
            config_parser.read(config_path)

            if org_config_path is None:
                org_config_path = CONF_DIR / "conf_organization.yaml"
            with Path.open(org_config_path, "r") as f:
                raw_config = yaml.safe_load(f)
            org_config = from_dict(OrganizationConfig, raw_config)
            cls._config = Config(neo4j_config=Neo4jConfig(**dict(config_parser["neo4j_config"])), org_config=org_config)
        return cls._config

    @classmethod
    def _get_org_config(cls) -> Neo4jConfig:
        return AppConfig.get().neo4j_config
