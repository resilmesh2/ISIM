MATCH (h:Host)-[:IS_A]-(n:Node)-[:ASSIGNED_TO]-(ip:IP)
OPTIONAL MATCH (ip)-[:PART_OF]-(s:Subnet)
OPTIONAL MATCH (ip)-[:RESOLVES_TO]-(d:Domain)
OPTIONAL MATCH (ip)-[:IDENTIFIES]-(u:URI)
RETURN h,n,ip,s,d,u