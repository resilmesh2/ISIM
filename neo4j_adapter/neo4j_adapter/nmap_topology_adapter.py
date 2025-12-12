from pathlib import Path
from typing import Any

from neo4j_adapter.general_adapter import GeneralAdapter

BASE_DIR = Path(__file__).parent


class NmapTopologyAdapter(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)

    def create_topology(self, nmap_result) -> None:
        """
        Create topology from nmap_result.

        :param nmap_result: JSON-like form of nmap results
        :return: None
        """
        query = (
            "WITH apoc.convert.fromJsonMap($nmap_result) as value "
            "UNWIND value.data as data "
            "UNWIND data.hops as hops "
            "MERGE (prev_ip:IP {address:hops.prev_ip}) "
            "MERGE (prev_node:Node)-[:HAS_ASSIGNED]->(prev_ip)"
            "MERGE (next_ip:IP {address:hops.next_ip}) "
            "MERGE (next_node:Node)-[:HAS_ASSIGNED]->(next_ip)"
            "MERGE (prev_node)-[rel:IS_CONNECTED_TO {hops:hops.hops}]->(next_node) "
            "ON MATCH SET rel.last_detection = datetime(value.time) "
            "ON CREATE SET rel.last_detection = datetime(value.time)"
        )

        params = {"nmap_result": nmap_result}

        self._run_query(query, **params)
