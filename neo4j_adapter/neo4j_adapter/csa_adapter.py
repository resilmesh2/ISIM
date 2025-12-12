from pathlib import Path
from typing import Any, LiteralString, cast

from neo4j_adapter.general_adapter import GeneralAdapter

BASE_DIR = Path(__file__).parent


class CSAAdapter(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)

    def store_criticality(self, json_string: str) -> None:
        """
        This method stores criticality of nodes computed from their missions.
        :param json_string: contains list with items - IP, hostname, and criticality
        :return: None
        """
        query = (
            "WITH apoc.convert.fromJsonList($json_string) as value "
            "UNWIND value as result "
            "MATCH (ip:IP {address:result.ip}) "
            "MATCH (host:Host {hostname:result.hostname}) "
            "MATCH (host)<-[:IS_A]-(node:Node)-[:HAS_ASSIGNED]->(ip)"
            "SET node.mission_criticality = result.criticality "
        )

        query = cast("LiteralString", query)
        params = {"json_string": json_string}

        self._run_query(query, **params)

    def combine_criticality(self) -> None:
        """
        This method combines mission criticality, normalized degree centrality,
        and normalized betweenness centrality into one value stored for nodes.
        :return: None
        """
        query = """
        MATCH (n:Node)
        WITH max(n.topology_betweenness) AS max_betweenness, min(n.topology_betweenness) AS min_betweenness,
        count(n) AS count_of_nodes
        MATCH (n:Node)
        WITH n, max_betweenness, min_betweenness, count_of_nodes,
        CASE
          WHEN n.topology_degree IS NULL THEN 1
          ELSE 9*(n.topology_degree / count_of_nodes) + 1
        END AS topology_degree_norm,
        CASE
          WHEN n.topology_betweenness IS NULL THEN 1
          ELSE 9*((n.topology_betweenness - min_betweenness) / (max_betweenness - min_betweenness)) + 1
        END AS topology_betweenness_norm,
        CASE
          WHEN n.mission_criticality IS NULL THEN 1
          ELSE n.mission_criticality
        END AS mission_criticality
        SET n.topology_degree_norm = topology_degree_norm
        SET n.topology_betweenness_norm = topology_betweenness_norm
        SET n.mission_criticality = mission_criticality
        SET n.final_criticality = ((9*n.topology_degree_norm*n.topology_betweenness_norm / 100) + 1) * n.mission_criticality
                """
        query = cast("LiteralString", query)
        self._run_query(query)
