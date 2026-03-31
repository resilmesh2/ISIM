WITH apoc.convert.fromJsonList($json_string) AS rows, datetime.truncate('second', datetime.fromepochmillis(TIMESTAMP())) as scan_dt
        UNWIND rows AS row
        MERGE (ipadd:IP { address: row.ip })
            ON CREATE SET ipadd.status = "unknown"
            ON CREATE SET ipadd.tag = ["CASM"]
            ON MATCH SET ipadd.tag = apoc.coll.toSet(ipadd.tag + ["CASM"])
        WITH row, ipadd, scan_dt
        MERGE (node:Node)-[r1_seed:HAS_ASSIGNED]->(ipadd)
            ON CREATE SET r1_seed.start = scan_dt, r1_seed.end = scan_dt
        WITH row, ipadd, node, scan_dt
        OPTIONAL MATCH (node)-[existing_r1:HAS_ASSIGNED]->(ipadd) WHERE existing_r1.start IS NOT NULL
        WITH row, ipadd, node, scan_dt, head(collect(existing_r1)) AS r1
        FOREACH (_ IN CASE WHEN r1 IS NULL THEN [1] ELSE [] END |
            MERGE (node)-[:HAS_ASSIGNED {start: scan_dt, end: scan_dt}]->(ipadd)
        )
        FOREACH (_ IN CASE
            WHEN r1 IS NOT NULL
                 AND scan_dt - duration($rediscovery_time) > r1.end
                 AND ipadd.status = "known"
            THEN [1]
            ELSE []
        END |
            SET ipadd.status = "rediscovered"
        )
        FOREACH (_ IN CASE WHEN r1 IS NOT NULL THEN [1] ELSE [] END |
            SET r1.end = scan_dt
        )
        MERGE (host:Host)<-[:IS_A]-(node)
        WITH host, row, ipadd, scan_dt
        MERGE (dn: DomainName { domain_name: row.domain_name})
            ON CREATE SET dn.status = "unknown"
            ON CREATE SET dn.tag = ["A/AAAA", "CASM"]
            ON MATCH SET dn.tag = apoc.coll.toSet(["A/AAAA", "CASM"] + dn.tag)
        WITH host, row, dn, ipadd, scan_dt
        OPTIONAL MATCH (dn)<-[existing_r2:RESOLVES_TO]-(ipadd) WHERE existing_r2.start IS NOT NULL
        WITH host, row, dn, ipadd, scan_dt, head(collect(existing_r2)) AS r2
        FOREACH (_ IN CASE WHEN r2 IS NULL THEN [1] ELSE [] END |
            MERGE (dn)<-[:RESOLVES_TO {start: scan_dt, end: scan_dt}]-(ipadd)
        )
        FOREACH (_ IN CASE
            WHEN r2 IS NOT NULL
                 AND scan_dt - duration($rediscovery_time) > r2.end
                 AND dn.status = "known"
            THEN [1]
            ELSE []
        END |
            SET dn.status = "rediscovered"
        )
        FOREACH (_ IN CASE WHEN r2 IS NOT NULL THEN [1] ELSE [] END |
            SET r2.end = scan_dt
        )
        WITH host, row, scan_dt
        MERGE (ns: NetworkService {service: row.service, port: row.port, protocol: row.protocol})
            ON CREATE SET ns.tag = ["CASM"]
            ON MATCH SET ns.tag = apoc.coll.toSet(["CASM"] + ns.tag)
        WITH host, row, ns, scan_dt
        MATCH (host:Host)<-[IS_A]-(:Node)-[:HAS_ASSIGNED]->(:IP {address: row.ip})
        OPTIONAL MATCH (ns)-[existing_r3:ON]->(host) WHERE existing_r3.start IS NOT NULL
        WITH host, row, ns, scan_dt, head(collect(existing_r3)) AS r3
        FOREACH (_ IN CASE WHEN r3 IS NULL THEN [1] ELSE [] END |
            MERGE (ns)-[ns_h:ON {start: scan_dt, end: scan_dt}]->(host)
                ON CREATE SET ns_h.tag = ["CASM"], ns_h.status = "unknown"
        )
        FOREACH (_ IN CASE
            WHEN r3 IS NOT NULL
                 AND scan_dt - duration($rediscovery_time) > r3.end
                 AND r3.status = "known"
            THEN [1]
            ELSE []
        END |
            SET r3.status = "rediscovered"
        )
        FOREACH (_ IN CASE WHEN r3 IS NOT NULL THEN [1] ELSE [] END |
            SET r3.end = scan_dt
        )
        WITH host, row, scan_dt
        UNWIND row.software_versions AS software_version
        MERGE (sv:SoftwareVersion {name: software_version.name})
            ON CREATE SET sv.version = software_version.version
        WITH host, row, scan_dt, software_version
        MATCH (sv:SoftwareVersion {name: software_version.name})
        MATCH (host:Host)<-[IS_A]-(:Node)-[:HAS_ASSIGNED]->(:IP {address: row.ip})
        OPTIONAL MATCH (sv)-[existing_r4:ON]->(host) WHERE existing_r4.start IS NOT NULL
        WITH host, row, scan_dt, sv, head(collect(existing_r4)) AS r4
        FOREACH (_ IN CASE WHEN r4 IS NULL THEN [1] ELSE [] END |
            MERGE (sv)-[:ON {start: scan_dt, end: scan_dt}]->(host)
        )
        FOREACH (_ IN CASE WHEN r4 IS NOT NULL THEN [1] ELSE [] END |
            SET r4.end = scan_dt
        )
        ;
