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
    bolt: str = "bolt://resilmesh-sap-neo4j:7687"
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
                raise ValueError(
                    f"Declared {ip_interface_object.compressed} is not in subnet {network_object.compressed}"
                )
        self.version = ip_interface_object.version


@dataclass
class OrganizationConfig:
    name: str
    hosts: list[Host]
    cleaning_time: int
    rediscovery_time: int

LogFormatter = Literal["json", "colored", "key_value", "plain"]


@dataclass(unsafe_hash=True)
class LoggingConfig:
    level: str
    pretty_print_exceptions: bool = False
    verbose_origin: bool = True
    formatter: str = "key_value"
    endpoints_skip_list: list[str] = field(default_factory=list)

    @cached_property
    def level_const(self) -> int:
        return cast("int", getLevelName((self.level or "INFO").upper()))  # pyright: ignore[reportDeprecated]

    @cached_property
    def formatter_const(self) -> LogFormatter:
        return cast("LogFormatter", self.formatter)

    def __post_init__(self) -> None:
        resolved_level = getLevelName(self.level.upper())
        if not isinstance(resolved_level, int):
            msg = f"Invalid log level: {self.level}"
            raise ValueError(msg)

        if self.formatter not in get_args(LogFormatter):
            msg = f"Invalid formatter: {self.formatter}. Expected one of: {', '.join(get_args(LogFormatter))}"
            raise ValueError(msg)


@dataclass
class Config:
    neo4j: Neo4jConfig
    organization: OrganizationConfig
    logging: LoggingConfig


class AppConfig:
    _config: Config | None = None

    @classmethod
    def get(cls, config_path: Path | None = None, org_config_path: Path | None = None) -> Config:
        if cls._config is not None:
            return cls._config

        if config_path is None:
            config_path = CONF_DIR / "config.yaml"
        with config_path.open() as f:
            raw_config = yaml.safe_load(f)

        if org_config_path is None:
            org_config_path = CONF_DIR / "config_organization.yaml"
        with org_config_path.open() as f:
            raw_org_config = yaml.safe_load(f)

        raw_config["organization"] = raw_org_config

        cls._config = from_dict(Config, raw_config)

        return cls._config
