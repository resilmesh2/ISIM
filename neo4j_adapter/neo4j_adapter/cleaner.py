from typing import Any

from neo4j_adapter.general_adapter import GeneralAdapter


class Cleaner(GeneralAdapter):
    """
    Cleaner class responsible for cleaning up old entities from the database.
    Its methods are responsible only for selected entities.
    """

    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)
        self.duration = "P21D"

    def clean_old_vulnerabilities(self) -> None:
        """
        This method deletes relationships between vulnerabilities and
        software versions.
        :return: None
        """
        query = """CALL apoc.periodic.commit('
                WITH datetime() - duration($duration) AS popTime
                MATCH (vul:Vulnerability)-[r:IN]->(s:SoftwareVersion)
                WHERE r.end < popTime
                WITH r LIMIT $limit
                DELETE r
                RETURN count(*)', {limit:1000, duration: $duration})"""

        params = {"duration": self.duration}

        self._run_query(query, **params)

    def clean_host_layer(self) -> None:
        """
        This method deletes old relationships between hosts and network
        services and hosts and software versions.
        :return: None
        """
        query = (
            "CALL apoc.periodic.commit('"
            "WITH datetime() - duration($duration) AS popTime "
            "MATCH (ns:NetworkService)-[r1:ON]->(h1:Host) "
            "WHERE r1.end < popTime "
            "WITH r1, popTime LIMIT $limit "
            "MATCH (sv:SoftwareVersion)-[r2:ON]->(h2:Host) "
            "WHERE r2.end < popTime "
            "WITH r1, r2 LIMIT $limit "
            "DELETE r1, r2 "
            "RETURN count(*)', {limit:1000, duration: $duration})"
        )

        params = {"duration": self.duration}

        self._run_query(query, **params)

    def clean_network_layer(self) -> None:
        """
        This method deletes old relationships between IP addresses and
        domain names, nodes and IP addresses, and two nodes.
        :return: None
        """
        query = (
            "CALL apoc.periodic.commit('"
            "WITH datetime() - duration($duration) AS popTime "
            "MATCH (ip:IP)-[r1:RESOLVES_TO]->(d:DomainName) "
            "WHERE r1.end < popTime "
            "WITH r1, popTime LIMIT $limit "
            "MATCH (n:Node)-[r2:HAS_ASSIGNED]->(ip:IP) "
            "WHERE r2.end < popTime "
            "WITH r1, r2, popTime LIMIT $limit "
            "MATCH (n1:Node)-[r3:IS_CONNECTED_TO]->(n2:Node) "
            "WHERE r3.end < popTime "
            "WITH r1, r2, r3 LIMIT $limit "
            "DELETE r1, r2, r3 "
            "RETURN count(*)', {limit:1000, duration: $duration})"
        )

        params = {"duration": self.duration}

        self._run_query(query, **params)

    def clean_security_events(self) -> None:
        """
        This method deletes old security events.
        :return: None
        """
        query = (
            "CALL apoc.periodic.commit('"
            "WITH datetime() - duration($duration) AS popTime "
            "MATCH (secEvent:SecurityEvent) "
            "WHERE secEvent.detection_time < popTime "
            "WITH secEvent LIMIT $limit "
            "DETACH DELETE secEvent "
            "RETURN count(*)', {limit:1000, duration: $duration})"
        )

        params = {"duration": self.duration}

        self._run_query(query, **params)
