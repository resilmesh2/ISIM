from neo4j_adapter.GeneralAdapter import GeneralAdapter
import json


class RESTAdapter(GeneralAdapter):
    def __init__(self, password, **kwargs):
        super().__init__(password=password, **kwargs)

    def get_all_mission(self, limit):
        """
        Returns all missions from the database.
        :param limit: self explanatory
        :return: Missions
        """
        return self._run_query("MATCH (m:Mission) RETURN {name: m.name, description: m.description, \
                                criticality: m.criticality, \
                                structure: m.structure} AS mission LIMIT $limit",
                               **{'limit': limit})

    def create_missions_and_components_string(self, json_string):
        """
        A method for creating missions, components, additional required nodes and relationships directly from
        JSON-formatted string.
        :param json_string: a string obtained from JSON file
        :return: None
        """
        query = "WITH apoc.convert.fromJsonMap($json_string) as value " \
                "UNWIND value.nodes as nodes " \
                "UNWIND nodes.missions as missions " \
                "MERGE (mission:Mission {criticality: missions.criticality, " \
                "name: missions.name, description: missions.description, structure: apoc.convert.toJson(value)}) " \
                "WITH nodes, value " \
                "UNWIND nodes.services as components " \
                "MERGE (component:Component {name: components.name}) " \
                "WITH nodes, value " \
                "UNWIND nodes.hosts as host " \
                "MERGE (ip:IP {address: host.ip}) " \
                "MERGE (ip)<-[:HAS_ASSIGNED]-(nod:Node) " \
                "MERGE (nod)-[:IS_A]->(hos:Host {hostname: host.hostname}) " \
                "WITH value " \
                "UNWIND value.relationships as relationships " \
                "WITH relationships " \
                "UNWIND relationships.supports as supports " \
                "MATCH (mission:Mission {name: supports.from}) " \
                "MATCH (component:Component {name: supports.to}) " \
                "MERGE(mission)<-[:SUPPORTS]-(component) " \
                # "WITH relationships " \
                # "UNWIND relationships.has_identity as identity " \
                # "MATCH (component:Component {name: identity.from}) " \
                # "MATCH (host:Host {hostname: identity.to}) " \
                # "MERGE(component)-[:PROVIDED_BY]->(host)"

        params = {'json_string': json_string}

        self._run_query(query, **params)

        json_data = json.loads(json_string)
        for identity in json_data["relationships"]["has_identity"]:
            for host in json_data["nodes"]["hosts"]:
                if identity["to"] == host["hostname"]:
                    self._run_query("MATCH (component:Component {name: $identity_from}) "
                                    "MATCH (host:Host {hostname: $identity_to})<-[:IS_A]-(nod:Node)-[:HAS_ASSIGNED]->(ip:IP {address: $host_ip}) "
                                    "MERGE (component)-[:PROVIDED_BY]->(host)",
                                    **{"identity_from": identity["from"], "identity_to": identity["to"],
                                       "host_ip": host["ip"], "host_hostname": host["hostname"]})

        for dependency in json_data["relationships"]["dependencies"]:
            for component1 in json_data["nodes"]["services"]:
                for component2 in json_data["nodes"]["services"]:
                    if component1["id"] == dependency["from"] and component2["id"] == dependency["to"]:
                        self._run_query(
                                "MATCH (src_component:Component {name: $component1_name}), (dst_component:Component {name: $component2_name}) "
                                "MERGE (src_component)<-[:FROM]-(dep:MissionDependency) "
                                "MERGE (dep)-[:TO]->(dst_component)",
                                **{"component1_name": component1["name"], "component2_name": component2["name"]})
