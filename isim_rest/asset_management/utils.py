from configparser import ConfigParser

from isim_rest.neo4j_rest.settings import BASE_DIR


def get_password() -> str:
    config_parser = ConfigParser()
    config_parser.read(BASE_DIR / "neo4j_rest/conf.ini")
    return config_parser["dashboard_rest"]["neo4j_password"]
