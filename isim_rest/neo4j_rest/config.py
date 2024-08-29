from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

from isim_rest.neo4j_rest.settings import BASE_DIR

CONF_DIR = BASE_DIR.parent / "config"


@dataclass
class Neo4jConfig:
    password: str
    bolt: str = "bolt://localhost:7687"
    user: str = "neo4j"


@dataclass
class Config:
    neo4j_config: Neo4jConfig


class AppConfig:
    _config: Config | None = None

    @classmethod
    def get(cls, config_path: Path | None = None) -> Config:
        config_parser = ConfigParser()
        if cls._config is None:
            if config_path is None:  # pragma: no cover
                config_path = CONF_DIR / "conf.ini"
            config_parser.read(config_path)
            cls._config = Config(neo4j_config=Neo4jConfig(**dict(config_parser["neo4j_config"])))
        return cls._config
