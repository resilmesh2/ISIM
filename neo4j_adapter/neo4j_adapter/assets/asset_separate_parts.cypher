WITH apoc.convert.fromJsonMap($json_string) AS input_
// HOSTS PROCESSING
CALL (input_) {
  UNWIND input_.hosts AS hosts
  MERGE (ip:IP {address: hosts.ip_address})
    ON CREATE SET ip.tag = hosts.tag
    ON MATCH SET ip.tag = apoc.coll.toSet(ip.tag + hosts.tag)
  SET ip.status = "known"
  SET ip.version = hosts.version
  WITH hosts, ip
  // get or create HAS_ASSIGNED relationship without timestamps
  MERGE (node:Node)-[r1:HAS_ASSIGNED]->(ip)
  WITH hosts, ip, node
  OPTIONAL MATCH (node)-[tmp_r1:HAS_ASSIGNED]->(ip) WHERE tmp_r1.start IS NULL
  FOREACH(r IN CASE WHEN tmp_r1 IS NULL THEN [tmp_r1] ELSE [] END |
      CREATE (node)-[:HAS_ASSIGNED]->(ip)
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
    ON CREATE SET domain.tag = hosts.tag
    ON MATCH SET domain.tag = apoc.coll.toSet(domain.tag + hosts.tag)
  SET domain.status = "known"
  WITH ip, domain
  OPTIONAL MATCH (ip)-[r2:RESOLVES_TO]-(domain) WHERE r2.start IS NULL
  FOREACH(r IN CASE WHEN r2 IS NULL THEN [r2] ELSE [] END |
    CREATE (ip)-[:RESOLVES_TO]->(domain)
  )
}

// SOFTWARE VERSIONS
CALL (input_) {
UNWIND input_.software_versions AS sw_versions
  CALL apoc.do.case([
    sw_versions.port is not null and sw_versions.protocol is not null and sw_versions.version is not null and sw_versions.service is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    MERGE (ns:NetworkService {port: sw_versions.port, protocol: sw_versions.protocol, service: sw_versions.service})
    SET ns.tag = sw_versions.tag
    MERGE (sw)-[:PROVIDES]-(ns)
    WITH sw, ns, sw_versions
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[:HAS_ASSIGNED]->(ip)
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT sw, ns, h
    MERGE (sw)-[r3:ON]->(h)
    WITH DISTINCT sw, ns, h
    OPTIONAL MATCH (sw)-[r3:ON]->(h) WHERE r3.start IS NULL
    FOREACH(r in CASE WHEN r3 IS NULL THEN [r3] ELSE [] END |
      CREATE (sw)-[sw_h:ON]->(h)
    )
    // set known status to all relationships including timestamped ones
    MERGE (ns)-[ns_h:ON]->(h)
      SET ns_h.status = "known"
    WITH DISTINCT ns, h
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.start IS NULL
    FOREACH(r in CASE WHEN r4 IS NULL THEN [r4] ELSE [] END |
      CREATE (ns)-[ns_h:ON {status: "known"}]->(h)
    )
    ',
    sw_versions.version is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    WITH sw_versions, sw
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[:HAS_ASSIGNED]->(ip)
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT sw, h
    OPTIONAL MATCH (sw)-[r3:ON]->(h) WHERE r3.start IS NULL
    FOREACH(r in CASE WHEN r3 IS NULL THEN [r3] ELSE [] END |
      CREATE (sw)-[sw_h:ON]->(h)
    )
    ',
    sw_versions.port is not null and sw_versions.protocol is not null and sw_versions.service is not null,
    '
    MERGE (ns:NetworkService {port: sw_versions.port, protocol: sw_versions.protocol, service: sw_versions.service})
    SET ns.tag = sw_versions.tag
    WITH ns, sw_versions
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[:HAS_ASSIGNED]->(ip)
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT ns, h
    // set known status to all relationships including timestamped ones
    MERGE (ns)-[ns_h:ON]->(h)
      SET ns_h.status = "known"
    WITH ns, h
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.start IS NULL
    FOREACH(r in CASE WHEN r4 IS NULL THEN [r4] ELSE [] END |
      CREATE (ns)-[ns_h:ON {status: "known"}]->(h)
    )
    '
    ],
    '',
    {sw_versions: sw_versions}
  )
  yield value as versions
  RETURN versions

}
RETURN input_