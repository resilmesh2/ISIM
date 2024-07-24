import json
from pathlib import Path
from typing import Any

from neo4j_adapter.general_adapter import GeneralAdapter

BASE_DIR = Path(__file__).parent


class RESTAdapter(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)

    def get_all_mission(self, limit: int) -> list[Any]:
        """
        Returns all missions from the database.
        :param limit: self explanatory
        :return: Missions
        """
        return self._run_query(
            "MATCH (m:Mission) RETURN {name: m.name, description: m.description, \
                                criticality: m.criticality, \
                                structure: m.structure} AS mission LIMIT $limit",
            limit=limit,
        )

    def create_missions_and_components_string(self, json_string: str) -> None:
        """
        A method for creating missions, components, additional required nodes and relationships directly from
        JSON-formatted string.
        :param json_string: a string obtained from JSON file
        :return: None
        """
        query = (
            "WITH apoc.convert.fromJsonMap($json_string) as value "
            "UNWIND value.nodes as nodes "
            "UNWIND nodes.missions as missions "
            "MERGE (mission:Mission {criticality: missions.criticality, "
            "name: missions.name, description: missions.description, structure: apoc.convert.toJson(value)}) "
            "WITH nodes, value "
            "UNWIND nodes.services as components "
            "MERGE (component:Component {name: components.name}) "
            "WITH nodes, value "
            "UNWIND nodes.hosts as host "
            "MERGE (ip:IP {address: host.ip}) "
            "MERGE (ip)<-[:HAS_ASSIGNED]-(nod:Node) "
            "MERGE (nod)-[:IS_A]->(hos:Host {hostname: host.hostname}) "
            "WITH value "
            "UNWIND value.relationships as relationships "
            "WITH relationships "
            "UNWIND relationships.supports as supports "
            "MATCH (mission:Mission {name: supports.from}) "
            "MATCH (component:Component {name: supports.to}) "
            "MERGE(mission)<-[:SUPPORTS]-(component) "
        )

        params = {"json_string": json_string}

        self._run_query(query, **params)

        json_data = json.loads(json_string)
        for identity in json_data["relationships"]["has_identity"]:
            for host in json_data["nodes"]["hosts"]:
                if identity["to"] == host["hostname"]:
                    self._run_query(
                        "MATCH (component:Component {name: $identity_from}) "
                        "MATCH (host:Host {hostname: $identity_to})<-[:IS_A]-(nod:Node)-[:HAS_ASSIGNED]->(ip:IP {address: $host_ip}) "
                        "MERGE (component)-[:PROVIDED_BY]->(host)",
                        identity_from=identity["from"],
                        identity_to=identity["to"],
                        host_ip=host["ip"],
                        host_hostname=host["hostname"],
                    )

        for dependency in json_data["relationships"]["dependencies"]:
            for component1 in json_data["nodes"]["services"]:
                for component2 in json_data["nodes"]["services"]:
                    if component1["id"] == dependency["from"] and component2["id"] == dependency["to"]:
                        self._run_query(
                            "MATCH (src_component:Component {name: $component1_name}), (dst_component:Component {name: $component2_name}) "
                            "MERGE (src_component)<-[:FROM]-(dep:MissionDependency) "
                            "MERGE (dep)-[:TO]->(dst_component)",
                            component1_name=component1["name"],
                            component2_name=component2["name"],
                        )

    def get_organization_units(self, limit: int = 50, offset: int = 0) -> list[Any]:
        query = """
        MATCH (ou: OrganizationUnit)
        OPTIONAL MATCH (ou)-[:TENANTS]-(pe:PhysicalEnvironment)
        OPTIONAl MATCH (s:Subnet)-[:PART_OF]-(ou)
        RETURN ou, s, pe
        ORDER BY ou.name
        SKIP $offset
        LIMIT $limit
        """
        return self._run_query(query, limit=limit, offset=offset)

    def get_subnets(self, limit: int = 50, offset: int = 0) -> list[Any]:
        query = """
        MATCH (s:Subnet)
        OPTIONAL MATCH (s)-[:PART_OF]-(p_s: Subnet)
        OPTIONAL MATCH (s)-[:PART_OF]-(ou: OrganizationUnit)
        OPTIONAL MATCH (s)-[:HAS]-(c: Contact)
        OPTIONAL MATCH (s)-[:PART_OF]-(ip: IP)
        RETURN s, p_s, ou, c, ip
        ORDER BY s.range
        SKIP $offset
        LIMIT $limit
        """
        return self._run_query(query, limit=limit, offset=offset)

    def get_ip_assets(self, limit: int = 50, offset: int = 0) -> list[Any]:
        query = """
        MATCH (ip:IP)
        OPTIONAL MATCH (ip)-[:PART_OF]-(s:Subnet)-[:PART_OF]-(ou:OrganizationUnit)
        OPTIONAL MATCH (ip)-[:RESOLVES_TO]-(d:Domain)
        OPTIONAL MATCH (ip)-[:IDENTIFIES]-(u:URI)
        RETURN ip, s, d, u, ou
        ORDER BY ip.address
        SKIP $offset
        LIMIT $limit
        """
        return self._run_query(query, limit=limit, offset=offset)

    def get_devices(self, limit: int = 50, offset: int = 0) -> list[Any]:
        query = """
        MATCH (dev:Device)
        OPTIONAL MATCH (dev)-[:PART_OF]-(ou:OrganizationUnit)
        OPTIONAL MATCH (dev)-[:HAS]-(h_v:HardwareVersion)
        OPTIONAL MATCH (dev)-[:HAS_IDENTITY]-(h:Host)-[:IS_A]-(n:Node)-[:HAS_ASSIGNED]-(ip:IP)
        RETURN dev, ou, h_v, h, n, ip
        ORDER BY dev.name
        SKIP $offset
        LIMIT $limit
        """
        return self._run_query(query, limit=limit, offset=offset)

    def get_applications(self, limit: int = 50, offset: int = 0) -> list[Any]:
        query = """
        MATCH (app:Application)
        OPTIONAL MATCH (app)-[:RUNNING_ON]-(dev:Device)
        RETURN app, dev
        ORDER BY app.name
        SKIP $offset
        LIMIT $limit
        """
        return self._run_query(query, limit=limit, offset=offset)

    def store_assets(self, json_string: str) -> None:
        query = Path(BASE_DIR / "assets/asset_update_query.cypher").read_text()
        params = {"json_string": json_string}
        self._run_query(query, **params)
        self._default_ip_address_parent_subnets_constraint()
        self._default_subnet_parent_subnets_constraint()

    def _default_ip_address_parent_subnets_constraint(self) -> None:
        query_ipv4_without_parents = r"""
        MATCH (ip:IP) WHERE NOT EXISTS ((ip)-[:PART_OF]->(:Subnet)) AND ip.address =~ ".+\..+"
        MATCH (s:Subnet {range: "0.0.0.0/0"})
        MERGE (ip)-[:PART_OF]->(s)
        """
        query_ipv6_without_parents = """
        MATCH (ip:IP) WHERE NOT EXISTS ((ip)-[:PART_OF]->(:Subnet)) AND ip.address =~ ".+:.+"
        MATCH (s:Subnet {range: "::/0"})
        MERGE (ip)-[:PART_OF]->(s)
        """
        query_ipv4_delete_internet_relict = """
        MATCH (internet:Subnet {range: "0.0.0.0/0"})
        MATCH (subnet:Subnet) WHERE subnet.range <> "0.0.0.0/0"
        MATCH (ip:IP) WHERE EXISTS ((ip)-[:PART_OF]->(internet)) AND EXISTS ((ip)-[:PART_OF]->(subnet))
        MATCH (ip)-[r:PART_OF]->(internet)
        DELETE r
        """
        query_ipv6_delete_internet_relict = """
        MATCH (internet:Subnet {range: "::/0"})
        MATCH (subnet:Subnet) WHERE subnet.range <> "::/0"
        MATCH (ip:IP) WHERE EXISTS ((ip)-[:PART_OF]->(internet)) AND EXISTS ((ip)-[:PART_OF]->(subnet))
        MATCH (ip)-[r:PART_OF]->(internet)
        DELETE r
        """
        self._run_query(query_ipv4_without_parents)
        self._run_query(query_ipv4_delete_internet_relict)
        self._run_query(query_ipv6_without_parents)
        self._run_query(query_ipv6_delete_internet_relict)

    def _default_subnet_parent_subnets_constraint(self) -> None:
        query_ipv4_without_parents = r"""
        MATCH (s:Subnet) WHERE NOT EXISTS ((s)-[:PART_OF]->(:Subnet)) AND s.range =~ ".+\..+" AND s.range <> "0.0.0.0/0"
        MATCH (internet:Subnet {range: "0.0.0.0/0"})
        MERGE (s)-[:PART_OF]->(internet)
        """
        query_ipv6_without_parents = """
        MATCH (s:Subnet) WHERE NOT EXISTS ((s)-[:PART_OF]->(:Subnet)) AND s.range =~ ".+:.+" AND s.range <> "::/0"
        MATCH (internet:Subnet {range: "::/0"})
        MERGE (s)-[:PART_OF]->(internet)
        """
        query_ipv4_delete_internet_relict = """
        MATCH (internet:Subnet {range: "0.0.0.0/0"})
        MATCH (parent:Subnet) WHERE parent.range <> "0.0.0.0/0"
        MATCH (subnet:Subnet) WHERE EXISTS ((subnet)-[:PART_OF]->(internet)) AND EXISTS ((subnet)-[:PART_OF]->(parent))
        MATCH (subnet)-[r:PART_OF]->(internet)
        DELETE r
        """
        query_ipv6_delete_internet_relict = """
        MATCH (internet:Subnet {range: "::/0"})
        MATCH (parent:Subnet) WHERE parent.range <> "::/0"
        MATCH (subnet:Subnet) WHERE EXISTS ((subnet)-[:PART_OF]->(internet)) AND EXISTS ((subnet)-[:PART_OF]->(parent))
        MATCH (subnet)-[r:PART_OF]->(internet)
        DELETE r
        """
        self._run_query(query_ipv4_without_parents)
        self._run_query(query_ipv4_delete_internet_relict)
        self._run_query(query_ipv6_without_parents)
        self._run_query(query_ipv6_delete_internet_relict)
