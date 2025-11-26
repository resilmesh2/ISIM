WITH apoc.convert.fromJsonMap($json_string) AS input_, datetime.truncate('second', datetime.fromepochmillis(TIMESTAMP())) as scan_dt
// HOSTS PROCESSING
CALL (input_, scan_dt) {
  UNWIND input_.hosts AS hosts
  MERGE (ip:IP {address: hosts.ip_address})
    ON CREATE SET ip.tag = ["CASM"] + hosts.tag
    ON CREATE SET ip.status = "unknown"
    ON MATCH SET ip.tag = apoc.coll.toSet(ip.tag + hosts.tag)
    SET ip.version = hosts.version
  WITH hosts, ip
  // get or create HAS_ASSIGNED relationship without timestamps
  MERGE (node:Node)-[r1:HAS_ASSIGNED]->(ip)
    ON CREATE SET r1.start = scan_dt, r1.end = scan_dt
  WITH hosts, ip, node
  OPTIONAL MATCH (node)-[tmp_r1:HAS_ASSIGNED]->(ip) WHERE tmp_r1.start IS NOT NULL
  FOREACH(r IN CASE WHEN tmp_r1 IS NULL THEN [tmp_r1] ELSE [] END |
      MERGE (node)-[:HAS_ASSIGNED {start: scan_dt, end: scan_dt}]->(ip)
  )
  FOREACH(r IN CASE WHEN tmp_r1 IS NOT NULL THEN [tmp_r1] ELSE [] END |
      FOREACH (inner_r IN CASE WHEN scan_dt - duration($rediscovery_time) > r.end AND ip.status = "known" THEN [r] ELSE [] END |
        SET ip.status = "rediscovered"
      )
      SET r.end = scan_dt
  )
  MERGE (host:Host)<-[:IS_A]-(node) // MATCH NEW HOST BY IP ADDRESS
  FOREACH (s IN hosts.subnets |     // UPSERT SUBNETS THE IP IS PART OF, UPSERT RELATIONSHIPS
    MERGE (subnet:Subnet {range: s})
    MERGE (ip)-[:PART_OF]->(subnet)
  )
  FOREACH (u IN hosts.uris |   // UPSERT URIS RELATED TO IP, UPSERT RELATIONSHIPS
    MERGE (uri:URI {identifier: u})
    MERGE (ip)-[:IDENTIFIES]-(uri)
  )
  WITH hosts, ip
  UNWIND hosts.domain_names AS d // UPSERT DOMAINS RELATED TO IP, UPSERT RELATIONSHIPS
  MERGE (domain:DomainName {domain_name: d})
    ON CREATE SET domain.status = "unknown"
    ON CREATE SET domain.tag = ["CASM"] + hosts.tag
    ON MATCH SET domain.tag = apoc.coll.toSet(domain.tag + hosts.tag)
  WITH ip, domain
  OPTIONAL MATCH (ip)-[r2:RESOLVES_TO]-(domain) WHERE r2.start IS NOT NULL
  FOREACH(r IN CASE WHEN r2 IS NULL THEN [r2] ELSE [] END |
    MERGE (ip)-[:RESOLVES_TO {start: scan_dt, end: scan_dt}]-(domain)
  )
  FOREACH(r IN CASE WHEN r2 IS NOT NULL THEN [r2] ELSE [] END |
    FOREACH (inner_r IN CASE WHEN scan_dt - duration($rediscovery_time) > r.end AND domain.status = "known" THEN [r] ELSE [] END |
        SET domain.status = "rediscovered"
      )
    SET r.end = scan_dt
  )
}

// SOFTWARE VERSIONS
CALL (input_, scan_dt) {
UNWIND input_.software_versions AS sw_versions
  CALL apoc.do.case([
    sw_versions.port is not null and sw_versions.protocol is not null and sw_versions.version is not null and sw_versions.service is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    MERGE (ns:NetworkService {port: sw_versions.port, protocol: sw_versions.protocol, service: sw_versions.service})
    SET ns.tag = ["CASM"] + sw_versions.tag
    MERGE (sw)-[:PROVIDES]-(ns)
    WITH sw, ns, sw_versions, scan_dt
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[r1:HAS_ASSIGNED]->(ip)
      ON CREATE SET r1.start = scan_dt, r1.end = scan_dt
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT sw, ns, h, scan_dt
    OPTIONAL MATCH (sw)-[r3:ON]->(h) WHERE r3.start IS NOT NULL
    FOREACH(r in CASE WHEN r3 IS NULL THEN [r3] ELSE [] END |
      MERGE (sw)-[sw_h:ON {start: scan_dt, end:scan_dt}]->(h)
    )
    FOREACH(r IN CASE WHEN r3 IS NOT NULL THEN [r3] ELSE [] END |
      SET r.end = scan_dt
    )
    WITH DISTINCT ns, h, scan_dt
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.start IS NOT NULL
    FOREACH(r in CASE WHEN r4 IS NULL THEN [r4] ELSE [] END |
      MERGE (ns)-[ns_h:ON {start: scan_dt, end:scan_dt}]->(h)
        ON CREATE SET ns_h.status = "unknown"
    )
    FOREACH(r IN CASE WHEN r4 IS NOT NULL THEN [r4] ELSE [] END |
      FOREACH (inner_r IN CASE WHEN scan_dt - duration($rediscovery_time) > r.end AND r.status = "known" THEN [r] ELSE [] END |
        MERGE (ns)-[inner_r4:ON]->(h)
          SET inner_r4.status = "rediscovered"
      )
      SET r.end = scan_dt
    )
    ',
    sw_versions.version is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    WITH sw_versions, sw, scan_dt
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[r1:HAS_ASSIGNED]->(ip)
      ON CREATE SET r1.start = scan_dt, r1.end = scan_dt
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT sw, h, scan_dt
    OPTIONAL MATCH (sw)-[r3:ON]->(h) WHERE r3.start IS NOT NULL
    FOREACH(r in CASE WHEN r3 IS NULL THEN [r3] ELSE [] END |
      MERGE (sw)-[sw_h:ON {start: scan_dt, end:scan_dt}]->(h)
    )
    FOREACH(r IN CASE WHEN r3 IS NOT NULL THEN [r3] ELSE [] END |
      SET r.end = scan_dt
    )
    ',
    sw_versions.port is not null and sw_versions.protocol is not null and sw_versions.service is not null,
    '
    MERGE (ns:NetworkService {port: sw_versions.port, protocol: sw_versions.protocol, service: sw_versions.service})
    SET ns.tag = ["CASM"] + sw_versions.tag
    WITH ns, sw_versions, scan_dt
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[r1:HAS_ASSIGNED]->(ip)
      ON CREATE SET r1.start = scan_dt, r1.end = scan_dt
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT ns, h, scan_dt
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.start IS NOT NULL
    FOREACH(r in CASE WHEN r4 IS NULL THEN [r4] ELSE [] END |
      MERGE (ns)-[ns_h:ON {start: scan_dt, end:scan_dt}]->(h)
        ON CREATE SET ns_h.status = "unknown"
    )
    FOREACH(r IN CASE WHEN r4 IS NOT NULL THEN [r4] ELSE [] END |
      FOREACH (inner_r IN CASE WHEN scan_dt - duration($rediscovery_time) > r.end AND r.status = "known" THEN [r] ELSE [] END |
        MERGE (ns)-[inner_r4:ON]->(h)
          SET inner_r4.status = "rediscovered"
      )
      SET r.end = scan_dt
    )
    '
    ],
    '',
    {sw_versions: sw_versions, scan_dt: scan_dt}
  )
  yield value as versions
  RETURN versions

}
RETURN input_