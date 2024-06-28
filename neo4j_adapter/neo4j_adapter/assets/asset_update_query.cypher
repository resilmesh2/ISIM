WITH apoc.convert.fromJsonMap($json_string) as input_
UNWIND input_.hosts as hosts
MERGE (host:Host)-[:IS_A]-(node:Node)-[:ASSIGNED_TO]-(ip:IP {address: hosts.ip_address})
WITH hosts, ip
FOREACH (s in hosts.subnets |
  MERGE (subnet:Subnet {range: s})
  MERGE (ip)-[:PART_OF]-(subnet)
)
WITH hosts, ip
FOREACH(u in hosts.uris |
  MERGE (uri:URI {identifier: u})
  MERGE (ip)-[:IDENTIFIES]-(uri)
)
WITH hosts, ip
FOREACH(d in hosts.domain_names |
  MERGE (domain:Domain {domain_name: d})
    ON MATCH SET domain.tag = hosts.tag
    ON CREATE SET domain.tag = hosts.tag
  MERGE (ip)-[:RESOLVES_TO]-(domain)
)

