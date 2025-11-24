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
    SET r.end = scan_dt
  )
}

// SUBNETS PROCESSING
CALL (input_) {
  UNWIND input_.subnets AS subnets
  MERGE (subnet: Subnet {range: subnets.ip_range})
  SET subnet.note = subnets.note
  SET subnet.version = subnets.version
  FOREACH (p IN subnets.parents |
    MERGE (parent:Subnet {range: p})
    MERGE (subnet)-[:PART_OF]->(parent)
  )
  FOREACH (c IN subnets.contacts |
    MERGE (contact: Contact {name: c})
    MERGE (subnet)-[:HAS]->(contact)
  )
  FOREACH (ou IN subnets.org_units |
    MERGE (org_unit: OrganizationUnit {name: ou})
    MERGE (subnet)-[:PART_OF]->(org_unit)
  )
}
// OU PROCESSING
CALL (input_) {
  UNWIND input_.org_units AS org_units
  MERGE (org_unit:OrganizationUnit {name: org_units.name})
  FOREACH (p IN org_units.parents |
    MERGE (ou_parent:OrganizationUnit {name: p})
    MERGE (org_unit)-[:PART_OF]->(ou_parent)
  )
  FOREACH (l IN org_units.locations |
    MERGE (loc:PhysicalEnvironment {location: l})
    MERGE (loc)<-[:TENANTS]-(org_unit)
  )
}
// APPLICATIONS PROCESSING
CALL (input_) {
  UNWIND input_.applications AS applications
  MERGE (app:Application {name: applications.name})
  MERGE (device:Device {name: applications.device})
  MERGE (app)-[:RUNNING_ON]->(device)
}
// DEVICES
CALL (input_) {
  UNWIND input_.devices AS devices
  MERGE (device:Device {name:devices.name})
  SET device.power = devices.power, device.state = device.state
  FOREACH (ou IN devices.org_units |
      MERGE (org_unit:OrganizationUnit {name: ou})
      MERGE (device)-[:PART_OF]->(org_unit)
  )
  WITH devices
  CALL (devices) {
    CALL apoc.do.when(
    NOT devices.ip_address IS NULL,
    '
    MERGE (device {name: devices.name})
    MERGE (ip_address:IP {address: devices.ip_address})
    MERGE (h:Host)<-[:IS_A]-(n:Node)-[:HAS_ASSIGNED]->(ip_address)
    MERGE (device)<-[:HAS_IDENTITY]-(h)',
    '',
    {devices:devices}
    )
    YIELD value
    RETURN count(value) AS ip_val
  }
  WITH devices
  CALL (devices) {
    CALL apoc.do.when(
      NOT (devices.manufacturer IS NULL OR devices.model IS NULL),
      '
      MERGE (device {name: devices.name})
      MERGE (h_v: HardwareVersion {manufacturer: devices.manufacturer, model: devices.model})
      MERGE (h_v)<-[:HAS]-(device)
      ',
      '',
      {devices: devices}
    )
    YIELD value
    RETURN count(value) AS hv_val
  }

  RETURN devices // discarded value

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
    MERGE (n:Node)-[:HAS_ASSIGNED]->(ip)
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
      SET r.end = scan_dt
    )
    WITH DISTINCT ns, h
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.status = "known"
    FOREACH(r IN CASE WHEN r4 IS NOT NULL THEN [r4] ELSE [] END |
      MERGE (ns)-[r4:ON]->(h)
        SET r4.status = "known"
    )
    ',
    sw_versions.version is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    WITH sw_versions, sw, scan_dt
    UNWIND sw_versions.ip_addresses AS ip_address
    MERGE (ip:IP {address: ip_address})
    MERGE (n:Node)-[:HAS_ASSIGNED]->(ip)
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
    MERGE (n:Node)-[:HAS_ASSIGNED]->(ip)
    MERGE (h:Host)<-[:IS_A]-(n)
    WITH DISTINCT ns, h, scan_dt
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.start IS NOT NULL
    FOREACH(r in CASE WHEN r4 IS NULL THEN [r4] ELSE [] END |
      MERGE (ns)-[ns_h:ON {start: scan_dt, end:scan_dt}]->(h)
        ON CREATE SET ns_h.status = "unknown"
    )
    FOREACH(r IN CASE WHEN r4 IS NOT NULL THEN [r4] ELSE [] END |
      SET r.end = scan_dt
    )
    WITH DISTINCT ns, h
    OPTIONAL MATCH (ns)-[r4:ON]->(h) WHERE r4.status = "known"
    FOREACH(r IN CASE WHEN r4 IS NOT NULL THEN [r4] ELSE [] END |
      MERGE (ns)-[r4:ON]->(h)
        SET r4.status = "known"
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