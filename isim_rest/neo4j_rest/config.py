from dataclasses import dataclass
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
class Config:
    neo4j: Neo4jConfig


class AppConfig:
    _config: Config | None = None

    @classmethod
    def get(cls, config_path: Path | None = None) -> Config:
        if cls._config is not None:
            return cls._config

        if config_path is None:
            config_path = CONF_DIR / "config.yaml"

        with config_path.open() as f:
            raw_config = yaml.safe_load(f)

        cls._config = from_dict(Config, raw_config)
        return cls._config
