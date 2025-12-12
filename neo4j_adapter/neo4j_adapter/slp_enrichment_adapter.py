from pathlib import Path
from typing import Any, LiteralString, cast

from neo4j_adapter.general_adapter import GeneralAdapter

BASE_DIR = Path(__file__).parent


class SLPEnrichmentAdapter(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)

    def store_slp_data(self, domains_ips_for_storing: str) -> None:
        """
        This method stores enrichment data obtained from SLP API.
        :param domains_ips_for_storing: string containing representation for storing
        :return: None
        """
        query = "WITH apoc.convert.fromJsonList($json_string) as value \
                UNWIND value as result \
                UNWIND result.domain AS domain \
                UNWIND result.ip AS ip_address \
                UNWIND result.subnet AS subnet \
                UNWIND result.sp_risk_score AS sp_risk_score \
                UNWIND result.tag AS tag \
                MERGE (d: DomainName {domain_name: domain}) \
                ON CREATE SET d.tag = [tag] \
                ON MATCH SET d.tag = CASE \
                    WHEN d.tag IS NULL THEN tag \
                    ELSE apoc.coll.toSet([tag] + [x IN d.tag WHERE x <> 'SLP_no']) \
                END \
                MERGE (ip: IP {address: ip_address}) \
                ON CREATE SET ip.tag = ['SLP'] \
                ON MATCH SET ip.tag = CASE \
                    WHEN ip.tag IS NULL THEN ['SLP'] \
                    ELSE apoc.coll.toSet(['SLP'] + ip.tag) \
                END \
                SET ip.sp_risk_score = sp_risk_score \
                MERGE (d)<-[r:RESOLVES_TO {start: datetime.truncate('second', datetime.fromepochmillis(TIMESTAMP()))}]-(ip) \
                MERGE (s: Subnet {range: subnet, version: 4}) \
                MERGE (ip)-[:PART_OF]->(s)"

        query = cast("LiteralString", query)
        params = {"json_string": domains_ips_for_storing}
        self._run_query(query, **params)
