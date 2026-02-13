CALL apoc.trigger.add(
    "setInRelationshipEndOnClose",
    "
    UNWIND coalesce($assignedNodeProperties['status'], []) AS prop
    WITH prop, prop.node AS vuln
    WHERE vuln:Vulnerability
        AND prop.old <> prop.new
        AND (
            toString(prop.new) = 'closed'
            OR toString(prop.new) CONTAINS 'closed'
        )
    MATCH (vuln)-[rel:IN]->(:SoftwareVersion)
    SET rel.end = coalesce(rel.end, toString(datetime()))
    ",
    {phase: 'before'}
);

CALL apoc.trigger.add(
    "setInRelationshipStartOnCreate",
    "
    UNWIND $createdRelationships AS rel
    WITH rel
    WHERE type(rel) = 'IN'
        AND startNode(rel):Vulnerability
        AND endNode(rel):SoftwareVersion
    SET rel.start = coalesce(rel.start, toString(datetime()))
    ",
    {phase: 'before'}
);

CALL apoc.trigger.add(
    "updateSoftwareVersionCveTimestampOnVulnStatusChange",
    "
    UNWIND coalesce($assignedNodeProperties['status'], []) AS prop
    WITH prop, prop.node AS vuln
    WHERE vuln:Vulnerability
        AND prop.old <> prop.new
    MATCH (vuln)-[:IN]->(sv:SoftwareVersion)
    SET sv.cve_timestamp = toString(datetime())
    ",
    {phase: 'before'}
);
