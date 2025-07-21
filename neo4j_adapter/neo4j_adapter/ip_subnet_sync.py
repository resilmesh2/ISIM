import contextlib
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network, IPv4Address, IPv6Address, IPv4Network, IPv6Network, IPv4Interface, \
    IPv6Interface, ip_interface
from typing import Any, LiteralString

from neo4j_adapter.general_adapter import GeneralAdapter


class IpSubnetSynchronize(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)
        self.duration = "P21D"

    def fetch_ips_and_subnets(self) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Fetch IPs and Subnets from the database."""
        ips_result = self._run_query("MATCH (ip:IP) RETURN ip.address AS address, ip.version AS version")
        subnets_result = self._run_query("MATCH (s:Subnet) RETURN s.range AS range, s.version AS version")

        ips = [{"address": record["address"], "version": record["version"]} for record in ips_result]
        subnets = [{"range": record["range"], "version": record["version"]} for record in subnets_result]
        return ips, subnets


@dataclass
class IPAddress:
    """Represents an IP address with its associated subnet."""

    address: str
    version: str
    subnet: "Network" = field(init=False)
    _ip_obj: IPv4Interface | IPv6Interface = field(init=False)

    def __post_init__(self):
        try:
            self._ip_obj = ip_interface(self.address)
        except ValueError:
            raise ValueError(f"Invalid IP interface: {self.address}")

    @property
    def ip_object(self) -> IPv4Interface | IPv6Interface:
        return self._ip_obj

    def find_nearest_subnet(self, networks: list["Network"]) -> "Network":
        best_match = None
        best_prefix_length = -1

        for network in networks:
            if network.version != self.version:
                continue

            if self._ip_obj.ip in network.network_object and network.prefix_length > best_prefix_length:
                best_match = network
                best_prefix_length = network.prefix_length

        self.subnet = best_match
        return best_match

    def __str__(self) -> str:
        subnet_info = f" (subnet: {self.subnet.range})" if self.subnet else " (no subnet)"
        return f"IP {self.address}{subnet_info}"

    def __repr__(self) -> str:
        return f"IPAddress(address='{self.address}', version='{self.version}', subnet={self.subnet})"


@dataclass
class Network:
    """Represents a network/subnet with parent and child relationships."""

    range: str
    version: str
    parent_subnet: "Network" = field(init=False)
    child_subnets: set["Network"] = field(default_factory=set)
    _network_obj: IPv4Network | IPv6Network = field(init=False)

    def __post_init__(self) -> None:
        """Validate network range on creation."""
        try:
            self._network_obj = ip_network(self.range, strict=False)
        except ValueError:
            raise ValueError(f"Invalid network range: {self.range}")

    @property
    def network_object(self) -> IPv4Network | IPv6Network:
        """Get the ipaddress network object."""
        return self._network_obj

    @property
    def prefix_length(self):
        """Get the prefix length of this network."""
        return self._network_obj.prefixlen

    def contains_network(self, other_network: "Network") -> bool:
        """
        Check if this network contains another network.

        Args:
            other_network: Network object to check

        Returns:
            True if the other network is a subnet of this network
        """
        return ip_interface(other_network.range) in self.network_object

    def find_nearest_parent(self, potential_parents: list["Network"]) -> "Network":
        """
        Find the nearest parent network (most specific parent that contains this network).

        Args:
            potential_parents: List of Network objects that could be parents

        Returns:
            The most specific parent Network, or None if no parent found
        """
        best_parent = None
        best_prefix_length = -1

        for parent in potential_parents:
            if parent.contains_network(self) and parent.prefix_length > best_prefix_length:
                best_prefix_length = parent.prefix_length
                best_parent = parent

        if best_parent:
            self.parent_subnet = best_parent
            best_parent.child_subnets.add(self)

        return best_parent

    def __hash__(self):
        return hash((self.range, self.version))

    def __eq__(self, other):
        if not isinstance(other, Network):
            return False
        return self.range == other.range and self.version == other.version


class NetworkManager:
    """Manages collections of IP addresses and networks with relationship building."""

    def __init__(self) -> None:
        self.ip_addresses: list[IPAddress] = []
        self.networks: list[Network] = []

    def add_ip(self, address: str, version: str) -> IPAddress:
        """Add an IP address to the manager."""
        ip_addr = IPAddress(address, version)
        self.ip_addresses.append(ip_addr)
        return ip_addr

    def add_network(self, range_str: str, version: str) -> Network:
        """Add a network to the manager."""
        network = Network(range_str, version)
        self.networks.append(network)
        return network

    def build_ip_subnet_relationships(self) -> None:
        """Build relationships between IP addresses and their nearest subnets."""
        for ip_addr in self.ip_addresses:
            ip_addr.find_nearest_subnet(self.networks)

    def build_network_hierarchy(self) -> None:
        """Build parent-child relationships between networks."""
        # Sort networks by prefix length (most specific first)
        sorted_networks = sorted(self.networks, key=lambda n: n.prefix_length, reverse=True)

        # Clear existing relationships
        for network in self.networks:
            network.parent_subnet = None
            network.child_subnets.clear()

        # Build hierarchy
        for network in sorted_networks:
            network.find_nearest_parent(self.networks)


class Neo4jIpSubnetSynchronize:
    """Extended version of IpSubnetSynchronize with hierarchy processing."""

    def __init__(self, adapter: "IpSubnetSynchronize") -> None:
        self.adapter = adapter
        self.manager = NetworkManager()

    def fetch_and_process_hierarchy(self) -> dict[str, Any]:
        """
        Fetch data from Neo4j, process hierarchy, and prepare for loading back.

        Returns:
            Dictionary containing processed data ready for Neo4j loading
        """
        # Fetch existing data
        ips, subnets = self.adapter.fetch_ips_and_subnets()

        # Load into manager
        self._load_data_into_manager(ips, subnets)

        # Build hierarchy
        self.manager.build_network_hierarchy()
        self.manager.build_ip_subnet_relationships()

        # Generate Neo4j update data
        return self._generate_neo4j_data()

    def _load_data_into_manager(self, ips: list[dict[str, str]], subnets: list[dict[str, str]]) -> None:
        """Load fetched data into the network manager."""
        # Clear existing data
        self.manager.ip_addresses.clear()
        self.manager.networks.clear()

        # Add networks
        for subnet in subnets:
            with contextlib.suppress(ValueError):
                self.manager.add_network(subnet["range"], subnet["version"])

        # Add IPs
        for ip in ips:
            with contextlib.suppress(ValueError):
                self.manager.add_ip(ip["address"], ip["version"])

    def _generate_neo4j_data(self) -> dict[str, Any]:
        """Generate data structure for Neo4j loading."""
        # Prepare subnet data with hierarchy
        subnet_data = []
        for network in self.manager.networks:
            subnet_entry = {
                "ip_range": network.range,
                "version": network.version,
                "parents": [network.parent_subnet.range] if network.parent_subnet else [],
            }
            subnet_data.append(subnet_entry)

        # Prepare IP data with subnet relationships
        ip_data = []
        for ip_addr in self.manager.ip_addresses:
            ip_entry = {
                "address": ip_addr.address,
                "version": ip_addr.version,
                "subnet": ip_addr.subnet.range if ip_addr.subnet else None,
            }
            ip_data.append(ip_entry)

        return {"subnets": subnet_data, "ips": ip_data, "statistics": self._get_statistics()}

    def _get_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        root_networks = [n for n in self.manager.networks if n.parent_subnet is None]
        orphaned_ips = [ip for ip in self.manager.ip_addresses if ip.subnet is None]

        return {
            "total_networks": len(self.manager.networks),
            "total_ips": len(self.manager.ip_addresses),
            "root_networks": len(root_networks),
            "orphaned_ips": len(orphaned_ips),
            "hierarchy_relationships": sum(1 for n in self.manager.networks if n.parent_subnet),
            "ip_subnet_relationships": sum(1 for ip in self.manager.ip_addresses if ip.subnet),
        }

    def load_hierarchy_to_neo4j(self, processed_data: dict[str, Any]) -> dict[str, Any]:
        """
        Load the processed hierarchy back to Neo4j.

        Args:
            processed_data: Data returned from fetch_and_process_hierarchy()

        Returns:
            Result of the Neo4j operation
        """
        # Clear existing PART_OF relationships between subnets
        clear_query = """
        MATCH (s1:Subnet)-[r:PART_OF]->(s2:Subnet)
        DELETE r
        """
        self.adapter._run_query(clear_query)

        # Prepare input for the existing Cypher query
        input_data = {"subnets": processed_data["subnets"]}

        # Use the existing subnet processing query
        subnet_query: LiteralString = """
           WITH $input AS input_
               CALL {
           WITH input_
               UNWIND input_.subnets AS subnets
               MERGE (subnet: Subnet {range: subnets.ip_range})
           SET subnet.note = subnets.note
           SET subnet.version = subnets.version
               FOREACH (p IN subnets.parents |
               MERGE (parent:Subnet {range: p})
               MERGE (subnet)-[:PART_OF]->(parent)
               )
               }
               RETURN count(*) as processed_subnets \
        """

        subnet_result = self.adapter._run_query(query=subnet_query, input=input_data)

        # Update IP-subnet relationships
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

        ip_result = self.adapter._run_query(query=ip_subnet_query, ips=processed_data["ips"])

        return {
            "subnet_processing": subnet_result,
            "ip_processing": ip_result,
            "statistics": processed_data["statistics"],
        }

    def run_full_hierarchy_sync(self) -> dict[str, Any]:
        """
        Run the complete hierarchy synchronization process.

        Returns:
            Complete results of the synchronization
        """

        # Process hierarchy
        processed_data = self.fetch_and_process_hierarchy()

        print("Hierarchy processing complete:")
        for key, value in processed_data["statistics"].items():
            print(f"  {key}: {value}")

        # Load back to Neo4j
        print("\nLoading hierarchy to Neo4j...")
        result = self.load_hierarchy_to_neo4j(processed_data)

        print("Hierarchy synchronization complete!")
        return result

    def print_hierarchy_preview(self) -> None:
        """Print a preview of the hierarchy structure."""

        # Show root networks and their immediate children
        root_networks = [n for n in self.manager.networks if n.parent_subnet is None]

        for root in sorted(root_networks, key=lambda n: n.prefix_length):

            # Show direct children
            children = sorted(root.child_subnets, key=lambda n: n.prefix_length)
            for child in children:

                # Show IPs in this child subnet
                ips_in_child = [ip for ip in self.manager.ip_addresses if ip.subnet == child]
                for ip in ips_in_child[:3]:  # Show first 3 IPs
                    print(f"    └─ IP: {ip.address}")
                if len(ips_in_child) > 3:
                    print(f"    └─ ... and {len(ips_in_child) - 3} more IPs")


# Example usage
def example_usage() -> None:
    """Example of how to use the Neo4j hierarchy integration."""

    # Assuming you have an existing IpSubnetSynchronize instance
    original_adapter = IpSubnetSynchronize(password="supertestovaciheslo")

    # Create the hierarchy synchronizer
    hierarchy_sync = Neo4jIpSubnetSynchronize(original_adapter)

    # Run the full synchronization
    hierarchy_sync.run_full_hierarchy_sync()

    # Or run step by step for more control
    # processed_data = hierarchy_sync.fetch_and_process_hierarchy()
    # hierarchy_sync.print_hierarchy_preview()
    # load_result = hierarchy_sync.load_hierarchy_to_neo4j(processed_data)


if __name__ == "__main__":
    example_usage()
