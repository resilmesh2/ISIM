WITH apoc.convert.fromJsonMap($json_string) as value
UNWIND value.nodes as nodes
UNWIND nodes.missions as missions
MERGE (mission:Mission {name: missions.name})
SET mission.criticality = missions.criticality
SET mission.confidentiality_requirement = missions.confidentiality_requirement
SET mission.integrity_requirement = missions.integrity_requirement
SET mission.availability_requirement = missions.availability_requirement
SET mission.description = missions.description
SET mission.structure = apoc.convert.toJson(value)
WITH nodes, value
UNWIND nodes.services as components
MERGE (component:Component {name: components.name})
WITH nodes, value
UNWIND nodes.hosts as host
MERGE (ip:IP {address: host.ip})
MERGE (ip)<-[:HAS_ASSIGNED]-(nod:Node)
MERGE (nod)-[:IS_A]->(hos:Host {hostname: host.hostname})
WITH value
UNWIND value.relationships as relationships
WITH relationships
UNWIND relationships.supports as supports
MATCH (mission:Mission {name: supports.from})
MATCH (component:Component {name: supports.to})
MERGE(mission)<-[:SUPPORTS]-(component)