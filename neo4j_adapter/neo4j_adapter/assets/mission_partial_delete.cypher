WITH apoc.convert.fromJsonMap($json_string) as value
UNWIND value.nodes as nodes
UNWIND nodes.missions as missions
MATCH (mission:Mission {name: missions.name})
SET mission.delete = true
WITH mission
OPTIONAL MATCH (mission)<-[r_supports:SUPPORTS]-(component:Component)
WHERE NOT EXISTS {
    MATCH (component)-[:SUPPORTS]->(m:Mission)
    WHERE m.delete IS NULL
} AND NOT EXISTS {
    (component)<-[:TO]-(:MissionDependency)
}
SET component.delete = true
DELETE r_supports
WITH mission
OPTIONAL MATCH (component:Component {delete: true})<-[:FROM]-(dependency:MissionDependency)
WHERE NOT EXISTS {
    MATCH (c:Component)<-[:FROM]-(dependency)
    WHERE c.delete IS NULL
}
SET dependency.delete = true
WITH mission
OPTIONAL MATCH (dependency:MissionDependency {delete: true})
OPTIONAL MATCH (component:Component)<-[:TO]-(dependency)
WHERE NOT EXISTS {
    MATCH (component)-[:SUPPORTS]->(m:Mission)
    WHERE m.name <> mission.name AND m.delete IS NULL
}
SET component.delete = true
DETACH DELETE dependency
WITH mission
OPTIONAL MATCH (component:Component {delete: true})
OPTIONAL MATCH (component)-[r_provided:PROVIDED_BY]->(host:Host)
WHERE NOT EXISTS {
    MATCH (c:Component)-[:PROVIDED_BY]->(host)
    WHERE c.delete IS NULL
} AND NOT EXISTS {
    (host)<-[:ON]-()
}
SET host.delete = true
DETACH DELETE component
WITH mission
OPTIONAL MATCH (host:Host {delete: true})
OPTIONAL MATCH (host)<-[:IS_A]-(node:Node)
WHERE NOT EXISTS {
    (node)-[:IS_CONNECTED_TO]->(:Node)
}
SET node.delete = true
DETACH DELETE host
WITH mission
OPTIONAL MATCH (node:Node {delete: true})
OPTIONAL MATCH (node)-[:HAS_ASSIGNED]->(ip:IP)
WHERE ip.status IS NULL AND ip.tag IS NULL
DETACH DELETE node
DETACH DELETE ip