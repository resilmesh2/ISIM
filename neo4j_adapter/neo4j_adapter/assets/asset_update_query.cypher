WITH apoc.convert.fromJsonMap($json_string) AS input_
// HOSTS PROCESSING
WITH *
CALL {
  WITH input_
  UNWIND input_.hosts AS hosts
  MERGE (host:Host)-[:IS_A]-(node:Node)-[:ASSIGNED_TO]-(ip:IP {address: hosts.ip_address}) // MATCH NEW HOST BY IP ADDRESS
  WITH hosts, ip, input_
  FOREACH (s IN hosts.subnets |     // UPSERT SUBNETS THE IP IS PART OF, UPSERT RELATIONSHIPS
    MERGE (subnet:Subnet {range: s})
    MERGE (ip)-[:PART_OF]-(subnet)
  )
  WITH hosts, ip, input_
  FOREACH (u IN hosts.uris |   // UPSERT URIS RELATED TO IP, UPSERT RELATIONSHIPS
    MERGE (uri:URI {identifier: u})
    MERGE (ip)-[:IDENTIFIES]-(uri)
  )
  WITH hosts, ip, input_
  FOREACH (d IN hosts.domain_names | // UPSERT DOMAINS RELATED TO IP, UPSERT RELATIONSHIPS
    MERGE (domain:Domain {domain_name: d})
    SET domain.tag = hosts.tag
    MERGE (ip)-[:RESOLVES_TO]-(domain)
  )
}
// SUBNETS PROCESSING
CALL {
  WITH input_
  UNWIND input_.subnets AS subnets
  MERGE (subnet: Subnet {range: subnets.ip_range})
  SET subnet.note = subnets.note
  WITH subnets, subnet, input_
  FOREACH (p IN subnets.parents |
    MERGE (parent:Subnet {range: p})
    MERGE (subnet)-[:PART_OF]-(parent)
  )
  WITH subnets, subnet, input_
  FOREACH (c IN subnets.contacts |
    MERGE (contact: Contact {name: c})
    MERGE (subnet)-[:HAS]-(contact)
  )
  WITH subnets, subnet, input_
  FOREACH (ou IN subnets.org_units |
    MERGE (org_unit: OrganizationUnit {name: ou})
    MERGE (subnet)-[:PART_OF]-(org_unit)
  )
}
// OU PROCESSING
CALL {
  WITH input_
  UNWIND input_.org_units AS org_units
  MERGE (org_unit:OrganizationUnit {name: org_units.name})
  WITH org_units, org_unit, input_
  FOREACH (p IN org_units.parents |
    MERGE (ou_parent:OrganizationUnit {name: p})
    MERGE (org_unit)-[:PART_OF]-(ou_parent)
  )
  FOREACH (l IN org_units.locations |
    MERGE (loc:PhysicalEnvironment {location: l})
    MERGE (loc)-[:TENANTS]-(org_unit)
  )
}
// APPLICATIONS PROCESSING
CALL {
  WITH input_
  UNWIND input_.applications AS applications
  MERGE (app:Application {name: applications.name})
  WITH app, applications
  FOREACH (d IN applications.devices |
    MERGE (app)-[:RUNNING_ON]-(d)
  )
}
// DEVICES
CALL {
  WITH input_
  UNWIND input_.devices AS devices
  MERGE (device:Device {name:devices.name})
  SET device.power = devices.power, device.state = device.state
  WITH device, devices
 WITH device, devices
    FOREACH (ou IN devices.org_units |
      MERGE (org_unit:OrganizationUnit {name: ou})
      MERGE (device)-[:PART_OF]-(org_unit)
  )
  WITH devices, device
  CALL {
    WITH devices, device
    CALL apoc.do.when(
    NOT devices.ip_address IS NULL,
    'MERGE (ip_address:IP {address: devices.ip_address})
     MERGE (h:Host)-[:IS_A]-(n:Node)-[:ASSIGNED_TO]-(ip_address) MERGE (device)-[:HAS_IDENTITY]-(h)',
    '',
    {devices:devices, device: device}
    )
    YIELD value
    RETURN count(value) AS ip_val
  }
  WITH devices, device
  CALL {
    WITH device, devices
    CALL apoc.do.when(
      NOT (devices.manufacturer IS NULL OR devices.model IS NULL),
      'MERGE (h_v: HardwareVersion {manufacturer: devices.manufacturer, model: devices.model})-[:HAS]-(device)',
      '',
      {devices: devices, device: device}
    )
    YIELD value
    RETURN count(value) AS hv_val
  }

  RETURN devices // discarded value

}
// SOFTWARE VERSIONS
CALL {
WITH input_
UNWIND input_.software_versions AS sw_versions
  CALL apoc.do.case([
    sw_versions.port is not null and sw_versions.protocol is not null and sw_versions.version is not null and sw_versions.service is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    MERGE (ns:NetworkService {port: sw_versions.port, protocol: sw_versions.protocol, service: sw_versions.service})
    SET sw.tag = sw_versions.tag
    SET ns.tag = sw_versions.tag
    MERGE (sw)-[:PROVIDES]-(ns)
    FOREACH (ip_address in sw_versions.ip_addresses |
        MERGE (ip:IP {address: ip_address})
        MERGE (h:Host)-[:IS_A]-(n:Node)-[:ASSIGNED_TO]-(ip)
        MERGE (sw)-[:ON]-(h)
        MERGE (ns)-[:ON]-(h)
    )
    ',
    sw_versions.version is not null,
    '
    MERGE (sw:SoftwareVersion {version: sw_versions.version})
    SET sw.tag = sw_versions.tag
    FOREACH (ip_address in sw_versions.ip_addresses |
        MERGE (ip:IP {address: ip_address})
        MERGE (h:Host)-[:IS_A]-(n:Node)-[:ASSIGNED_TO]-(ip)
        MERGE (sw)-[:ON]-(h)
    )
    ',
    sw_versions.port is not null and sw_versions.protocol is not null and sw_versions.service is not null,
    '
    MERGE (ns:NetworkService {port: sw_versions.port, protocol: sw_versions.protocol, service: sw_versions.service})
    SET ns.tag = sw_versions.tag
    FOREACH (ip_address in sw_versions.ip_addresses |
        MERGE (ip:IP {address: ip_address})
        MERGE (h:Host)-[:IS_A]-(n:Node)-[:ASSIGNED_TO]-(ip)
        MERGE (ns)-[:ON]-(h)
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