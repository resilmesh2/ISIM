CALL apoc.trigger.add(
    "setInRelationshipEndOnClose",
    "
    UNWIND coalesce($assignedNodeProperties['status'], []) AS prop
    WITH prop, prop.node AS vuln,
         CASE
             WHEN prop.new IS NULL THEN []
             WHEN valueType(prop.new) STARTS WITH 'LIST' THEN [x IN prop.new | toString(x)]
             ELSE [toString(prop.new)]
         END AS new_status_values
    WHERE vuln:Vulnerability
        AND prop.old <> prop.new
        AND 'closed' IN new_status_values
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
