from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
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

    def load_hierarchy_to_neo4j(self, processed_data: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
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

        self._run_query(clear_query)

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

               MERGE (parent:Subnet {range: subnets.parent})
               MERGE (subnet)-[:PART_OF]->(parent)
           }
           RETURN count(*) as processed_subnets
        """

        subnet_result = self._run_query(query=subnet_query, input=input_data)

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

        ip_result = self._run_query(query=ip_subnet_query, ips=processed_data["ips"])

        return {
            "subnet_processing": subnet_result,
            "ip_processing": ip_result,
        }


@dataclass
class BaseNetwork(ABC):
    """Abstract base class for network representations."""

    range: str
    version: str
    parent_subnet: BaseNetwork = field(init=False, default=None)  # pyright: ignore [reportAssignmentType]

    @abstractmethod  # pyright: ignore [reportArgumentType]
    def __post_init__(self) -> None:
        """Validate network range on creation."""

    @property
    @abstractmethod
    def network_object(self) -> IPv4Network | IPv6Network:
        """Get the ipaddress network object."""

    @property
    @abstractmethod
    def prefix_length(self) -> int:
        """Get the prefix length of this network."""

    @abstractmethod
    def contains_network(self, other_network: BaseNetwork) -> bool:
        """Check if this network contains another network."""

    def find_nearest_parent(self, potential_parents: list[BaseNetwork]) -> BaseNetwork | None:
        """
        Find the nearest parent network (most specific parent that contains this network).

        Args:
            potential_parents: List of Network objects that could be parents

        Returns:
            The most specific parent Network, or None if no parent found
        """
        best_parent = self.parent_subnet
        best_prefix_length = -1

        for parent in potential_parents:
            if (
                parent.version == self.version
                and parent.contains_network(self)
                and parent.prefix_length > best_prefix_length
            ):
                best_prefix_length = parent.prefix_length
                best_parent = parent

        if best_parent:
            self.parent_subnet = best_parent

        return best_parent

    def __hash__(self):
        return hash((self.range, self.version))

    def __eq__(self, other):
        if not isinstance(other, BaseNetwork):
            return False
        return self.range == other.range and self.version == other.version


@dataclass
class IPv4NetworkImpl(BaseNetwork):
    """IPv4 network implementation."""

    _network_obj: IPv4Network = field(init=False)

    def __post_init__(self) -> None:
        """Validate IPv4 network range on creation."""
        try:
            self._network_obj = IPv4Network(self.range)
        except ValueError as err:
            raise ValueError(f"Invalid IPv4 network range: {self.range}") from err  # type: ignore

        self.parent_subnet = IPv4NetworkImpl(range="0.0.0.0/0", version="4")

    @property
    def network_object(self) -> IPv4Network:
        """Get the IPv4 network object."""
        return self._network_obj

    @property
    def prefix_length(self) -> int:
        """Get the prefix length of this network."""
        return self._network_obj.prefixlen

    def contains_network(self, other_network: BaseNetwork) -> bool:
        """Check if this IPv4 network contains another IPv4 network."""
        if not isinstance(other_network, IPv4NetworkImpl):
            return False

        try:
            other_interface = IPv4Interface(other_network.range)
            return other_interface in self._network_obj and other_network.prefix_length > self.prefix_length
        except ValueError:
            return False


@dataclass
class IPv6NetworkImpl(BaseNetwork):
    """IPv6 network implementation."""

    _network_obj: IPv6Network = field(init=False)  # pyright: ignore [reportAssignmentType]

    def __post_init__(self) -> None:
        """Validate IPv6 network range on creation."""
        try:
            self._network_obj = IPv6Network(self.range, strict=False)
        except ValueError as err:
            raise ValueError(f"Invalid IPv6 network range: {self.range}") from err

        self.parent_subnet = IPv6NetworkImpl(range="::/0", version="6")

    @property
    def network_object(self) -> IPv6Network:
        """Get the IPv6 network object."""
        return self._network_obj

    @property
    def prefix_length(self) -> int:
        """Get the prefix length of this network."""
        return self._network_obj.prefixlen

    def contains_network(self, other_network: BaseNetwork) -> bool:
        """Check if this IPv6 network contains another IPv6 network."""
        if not isinstance(other_network, IPv6NetworkImpl):
            return False

        try:
            other_interface = IPv6Interface(other_network.range)
            return other_interface in self._network_obj and other_network.prefix_length > self.prefix_length
        except ValueError:
            return False


# Factory function to create the appropriate network type
def create_network(range_str: str, version: str) -> BaseNetwork:
    """Create a network object of the appropriate type."""
    if version == "4":
        return IPv4NetworkImpl(range=range_str, version=version)
    if version == "6":
        return IPv6NetworkImpl(range=range_str, version=version)
    raise ValueError(f"Unsupported IP version: {version}")  # type: ignore


@dataclass
class BaseIPAddress(ABC):
    """Abstract base class for IP address representations."""

    address: str
    version: str
    subnet: BaseNetwork = field(init=False, default=None)  # pyright: ignore [reportAssignmentType]

    @abstractmethod
    def __post_init__(self) -> None:
        """Initialize IP address."""

    @property
    @abstractmethod
    def ip_object(self) -> IPv4Address | IPv6Address:
        """Get the IP interface object."""

    @abstractmethod
    def find_nearest_subnet(self, networks: list[BaseNetwork]) -> BaseNetwork | None:
        """Find the nearest subnet that contains this IP address."""

    def __str__(self) -> str:
        subnet_info = f" (subnet: {self.subnet.range})" if self.subnet else " (no subnet)"
        return f"IP {self.address}{subnet_info}"


@dataclass
class IPv4AddressImpl(BaseIPAddress):
    """IPv4 address implementation."""

    _ip_obj: IPv4Interface = field(init=False)  # pyright: ignore [reportAssignmentType]

    def __post_init__(self) -> None:
        try:
            self._ip_obj = IPv4Interface(self.address)
        except ValueError as err:
            raise ValueError(f"Invalid IPv4 interface: {self.address}") from err  # type: ignore

        self.subnet = IPv4NetworkImpl(range="0.0.0.0/0", version="4")

    @property
    def ip_object(self) -> IPv4Interface:
        return self._ip_obj

    def find_nearest_subnet(self, networks: list[BaseNetwork]) -> BaseNetwork | None:
        best_match = self.subnet
        best_prefix_length = -1

        for network in networks:
            if not isinstance(network, IPv4NetworkImpl):
                continue

            if self._ip_obj in network.network_object and network.prefix_length > best_prefix_length:
                best_match = network
                best_prefix_length = network.prefix_length

        self.subnet = best_match
        return best_match


@dataclass
class IPv6AddressImpl(BaseIPAddress):
    """IPv6 address implementation."""

    _ip_obj: IPv6Address = field(init=False)  # pyright: ignore [reportAssignmentType]

    def __post_init__(self) -> None:
        try:
            self._ip_obj = IPv6Address(self.address)
        except ValueError as err:
            raise ValueError(f"Invalid IPv6 interface: {self.address}") from err  # type: ignore

        self.subnet = IPv6NetworkImpl(range="::/0", version="6")

    @property
    def ip_object(self) -> IPv6Address:
        return self._ip_obj

    def find_nearest_subnet(self, networks: list[BaseNetwork]) -> BaseNetwork | None:
        best_match = self.subnet
        best_prefix_length = -1

        for network in networks:
            if not isinstance(network, IPv6NetworkImpl):
                continue

            if self._ip_obj in network.network_object and network.prefix_length > best_prefix_length:
                best_match = network
                best_prefix_length = network.prefix_length

        self.subnet = best_match
        return best_match


# Factory function to create the appropriate IP address type
def create_ip_address(address: str, version: str) -> BaseIPAddress:
    """Create an IP address object of the appropriate type."""
    if version == "4":
        return IPv4AddressImpl(address=address, version=version)
    if version == "6":
        return IPv6AddressImpl(address=address, version=version)
    raise ValueError(f"Unsupported IP version: {version}")  # type: ignore


class NetworkManager:
    """Manages collections of IP addresses and networks with relationship building."""

    def __init__(self) -> None:
        self.ip_addresses: list[BaseIPAddress] = []
        self.networks: list[BaseNetwork] = []

    def add_ip(self, address: str, version: str) -> BaseIPAddress:
        """Add an IP address to the manager."""
        ip_addr = create_ip_address(address, version)
        self.ip_addresses.append(ip_addr)
        return ip_addr

    def add_network(self, range_str: str, version: str) -> BaseNetwork:
        """Add a network to the manager."""
        network = create_network(range_str, version)
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

        # Build hierarchy
        for network in sorted_networks:
            network.find_nearest_parent(self.networks)


class Neo4jIpSubnetSynchronize:
    """Extended version of IpSubnetSynchronize with hierarchy processing."""

    def __init__(self, adapter: IpSubnetSynchronize) -> None:
        self.adapter = adapter
        self.manager = NetworkManager()

    def fetch_and_process_hierarchy(self) -> dict[str, list[dict[str, str]]]:
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

        for subnet in subnets:
            with contextlib.suppress(ValueError):
                self.manager.add_network(subnet["range"], subnet["version"])

        for ip in ips:
            with contextlib.suppress(ValueError):
                self.manager.add_ip(ip["address"], ip["version"])

    def _generate_neo4j_data(self) -> dict[str, list[dict[str, str]]]:
        """Generate data structure for Neo4j loading."""
        # Prepare subnet data with hierarchy
        subnet_data: list[dict[str, str]] = []
        for network in self.manager.networks:
            subnet_entry: dict[str, str] = {
                "ip_range": network.range,
                "version": network.version,
                "parent": network.parent_subnet.range,
            }
            subnet_data.append(subnet_entry)

        # Prepare IP data with subnet relationships
        ip_data: list[dict[str, str]] = []
        for ip_addr in self.manager.ip_addresses:
            ip_entry: dict[str, str] = {
                "address": ip_addr.address,
                "version": ip_addr.version,
                "subnet": ip_addr.subnet.range,
            }
            ip_data.append(ip_entry)

        return {"subnets": subnet_data, "ips": ip_data}

    def run_full_hierarchy_sync(self) -> dict[str, Any]:
        """
        Run the complete hierarchy synchronization process.

        Returns:
            Complete results of the synchronization
        """

        # Process hierarchy
        processed_data = self.fetch_and_process_hierarchy()

        # Load back to Neo4j
        return self.adapter.load_hierarchy_to_neo4j(processed_data)


# Example usage
def example_usage() -> None:
    """Example of how to use the Neo4j hierarchy integration."""

    # Assuming you have an existing IpSubnetSynchronize instance
    original_adapter = IpSubnetSynchronize(password="supertestovaciheslo")

    # Create the hierarchy synchronizer
    hierarchy_sync = Neo4jIpSubnetSynchronize(original_adapter)

    # Run the full synchronization
    hierarchy_sync.run_full_hierarchy_sync()


if __name__ == "__main__":
    example_usage()
