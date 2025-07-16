from ipaddress import ip_address, ip_network, IPv4Address, IPv6Address
from typing import Any

from neo4j_adapter.general_adapter import GeneralAdapter


class IpSubnetSynchronize(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)
        self.duration = "P21D"

    def fetch_ips_and_subnets(self) -> tuple[list[dict], list[dict]]:
        """Fetch IPs and Subnets from the database."""
        ips_result = self._run_query("MATCH (ip:IP) RETURN ip.address AS address, ip.version AS version")
        subnets_result = self._run_query("MATCH (s:Subnet) RETURN s.range AS range, s.version AS version")

        ips = [{"address": record["address"], "version": record["version"]} for record in ips_result]
        subnets = [{"range": record["range"], "version": record["version"]} for record in subnets_result]
        return ips, subnets

    def pair_ips_to_subnets(self, ips: list[dict], subnets: list[dict]) -> list[dict]:
        """Match IPs to Subnets and return the relationships."""
        matches = []

        for ip in ips:
            try:
                ip_obj = ip_address(ip["address"])
                for subnet in subnets:
                    if ip["version"] != subnet["version"]:
                        continue
                    try:
                        net = ip_network(subnet["range"], strict=False)
                        if ip_obj in net:
                            matches.append({"ip": ip["address"], "subnet": subnet["range"]})
                            break  # Assuming only one subnet per IP
                    except ValueError:
                        print(f"Invalid subnet format: {subnet['range']}")
            except ValueError:
                print(f"Invalid IP address: {ip['address']}")
        return matches

    def create_relationships(self, matches: list[dict[str, Any]]) -> None:
        """Create PART_OF relationships between IPs and Subnets."""
        for match in matches:
            self._run_query(
                """
                MATCH (ip:IP {address: $ip})
                MATCH (subnet:Subnet {range: $subnet})
                MERGE (ip)-[:PART_OF]->(subnet)
            """,
                ip=match["ip"],
                subnet=match["subnet"],
            )

    def process_ip_subnet_relationships(self) -> None:
        """Complete workflow to process IP to subnet relationships."""
        with self._driver.session() as session:
            # Fetch data
            ips, subnets = session.execute_read(self.fetch_ips_and_subnets)

            # Find matches
            matches = self.pair_ips_to_subnets(ips, subnets)

            # Create relationships
            if matches:
                session.execute_write(self.create_relationships, matches)
                print(f"Created {len(matches)} IP-subnet relationships")
            else:
                print("No IP-subnet matches found")


test = IpSubnetSynchronize("supertestovaciheslo")

print(test.fetch_ips_and_subnets())