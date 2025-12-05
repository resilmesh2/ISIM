import yaml
from dataclasses import dataclass
from pathlib import Path

from isim_rest.neo4j_rest.settings import BASE_DIR

CONF_DIR = BASE_DIR.parent / "config"


@dataclass
class Neo4jConfig:
    password: str
    bolt: str = "bolt://resilmesh_sap_neo4j:7687"
    user: str = "neo4j"


@dataclass
class Config:
    neo4j_config: Neo4jConfig


class AppConfig:
    _config: Config | None = None

    @classmethod
    def get(cls, config_path: Path | None = None) -> Config:
        if cls._config is None:
            if config_path is None:
                config_path = CONF_DIR / "conf.yaml"
            
            with open(config_path, 'r') as file:
                config_data = yaml.safe_load(file)
            
            cls._config = Config(neo4j_config=Neo4jConfig(**config_data["neo4j_config"]))
        return cls._config