from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network, ip_interface, ip_network
from typing import Any, LiteralString

from neo4j_adapter.general_adapter import GeneralAdapter

IP_NET_TYPE = IPv4Network | IPv6Network
IP_TYPE = IPv4Interface | IPv6Interface


@dataclass
class IPToSubnet:
    ip_address: IP_TYPE
    subnet: IP_NET_TYPE | None


@dataclass
class SubnetToParent:
    subnet: IP_NET_TYPE
    parent: IP_NET_TYPE | None


class IpSubnetSynchronizer(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)
        self.duration = "P21D"

    @staticmethod
    def _find_closest_network(ip: IP_TYPE, networks: list[IP_NET_TYPE]) -> IP_NET_TYPE | None:
        """Return the most specific network that contains the IP."""
        candidates = [net for net in networks if ip in net]
        return max(candidates, key=lambda n: n.prefixlen, default=None)

    @staticmethod
    def _find_closest_parent(subnet: IP_NET_TYPE, networks: list[IP_NET_TYPE]) -> IP_NET_TYPE | None:
        """Return the most specific parent network."""
        parents = [net for net in networks if subnet != net and ip_interface(subnet) in net]
        return max(parents, key=lambda n: n.prefixlen, default=None)

    def prepare_data_for_neo4j(self, ips: list[IP_TYPE], subnets: list[IP_NET_TYPE]) -> dict[str, Any]:
        """Map IPs to closest subnets and subnets to closest parents, return parsed data."""
        closest_ip_map = [
            IPToSubnet(ip_address=ip, subnet=closest)
            for ip in ips
            if (closest := self._find_closest_network(ip, subnets))
        ]
        closest_parent_map = [
            SubnetToParent(subnet=sub, parent=parent)
            for sub in subnets
            if (parent := self._find_closest_parent(sub, subnets))
        ]
        return {
            "ips": self._parse_ips_for_cypher(closest_ip_map),
            "subnets": self._parse_subnets_for_cypher(closest_parent_map),
        }

    def fetch_ips_and_subnets(self) -> tuple[list[IP_TYPE], list[IP_NET_TYPE]]:
        """Fetch IPs and Subnets from the database."""
        ips_result = self._run_query("MATCH (ip:IP) RETURN ip.address AS address")
        subnets_result = self._run_query("MATCH (s:Subnet) RETURN s.range AS range")

        ips = [ip_interface(record["address"]) for record in ips_result]
        subnets = [ip_network(record["range"]) for record in subnets_result]
        return ips, subnets

    @staticmethod
    def _parse_subnets_for_cypher(subnets_to_parents: list[SubnetToParent]):
        return [
            {
                "ip_range": item.subnet.compressed,
                "version": item.subnet.version,
                "parent": item.parent.compressed if item.parent else None,
            }
            for item in subnets_to_parents
        ]

    @staticmethod
    def _parse_ips_for_cypher(ips_to_subnets: list[IPToSubnet]):
        return [
            {"address": item.ip_address.ip.compressed, "subnet": item.subnet.compressed if item.subnet else None}
            for item in ips_to_subnets
        ]

    def load_hierarchy_to_neo4j(self, ips: list[dict[str, str]], subnets: list[dict[str, str]]) -> dict[str, Any]:
        """Load the processed hierarchy back to Neo4j."""
        clear_query = """
        MATCH (s1:Subnet)-[r:PART_OF]->(s2:Subnet)
        MATCH (ip:IP)-[ip_rel:PART_OF]->(s1)
        DELETE r
        DELETE ip_rel
        """
        self._run_query(clear_query)

        subnet_query: LiteralString = """
           UNWIND $subnets AS subnets
           MERGE (subnet:Subnet {range: subnets.ip_range})
           SET subnet.version = subnets.version

           MERGE (parent:Subnet {range: subnets.parent})
           MERGE (subnet)-[:PART_OF]->(parent)
        """
        subnet_result = self._run_query(query=subnet_query, subnets=subnets)

        ip_subnet_query: LiteralString = """
        UNWIND $ips AS ip_data
        MATCH (ip:IP {address: ip_data.address})
        OPTIONAL MATCH (ip)-[old_rel:PART_OF]->(old_subnet:Subnet)
        DELETE old_rel
        WITH ip, ip_data
        WHERE ip_data.subnet IS NOT NULL
        MATCH (subnet:Subnet {range: ip_data.subnet})
        MERGE (ip)-[:PART_OF]->(subnet)
        """
        ip_result = self._run_query(query=ip_subnet_query, ips=ips)

        return {
            "subnet_processing": subnet_result,
            "ip_processing": ip_result,
        }

    def run(self) -> None:
        ip, subnets = self.fetch_ips_and_subnets()
        prepared_data = self.prepare_data_for_neo4j(ip, subnets)
        self.load_hierarchy_to_neo4j(prepared_data["ips"], prepared_data["subnets"])


def main() -> None:
    syncer = IpSubnetSynchronizer(password="supertestovaciheslo")  # ← Set real password
    ip, subnets = syncer.fetch_ips_and_subnets()
    prepared_data = syncer.prepare_data_for_neo4j(ip, subnets)
    syncer.load_hierarchy_to_neo4j(prepared_data["ips"], prepared_data["subnets"])


if __name__ == "__main__":
    main()
