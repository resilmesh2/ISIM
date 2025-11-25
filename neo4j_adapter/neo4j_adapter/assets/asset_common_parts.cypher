WITH apoc.convert.fromJsonMap($json_string) AS input_// SUBNETS PROCESSING
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
RETURN input_