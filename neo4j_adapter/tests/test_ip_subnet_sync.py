from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network, ip_interface, ip_network
from typing import cast

import pytest
from neo4j_adapter.ip_subnet_sync import (
    IP_NET_TYPE,
    IP_TYPE,
    IpSubnetSynchronizer,
    IPToSubnet,
    SubnetToParent,
)


class TestIPSubnetSynchronizer:
    """Test cases for IpSubnetSynchronizer class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Use a mock password for testing
        self.synchronizer = IpSubnetSynchronizer(password="test_password")

        # Sample test data
        self.ipv4_addresses: list[IPv4Interface] = [
            IPv4Interface("192.168.1.10/32"),
            IPv4Interface("192.168.1.200/32"),
            IPv4Interface("10.0.0.5/32"),
            IPv4Interface("172.16.5.9/32"),
        ]

        self.ipv6_addresses: list[IPv6Interface] = [
            IPv6Interface("2001:db8::1/128"),
            IPv6Interface("2001:db8:0:1::5/128"),
            IPv6Interface("fd00::1234/128"),
            IPv6Interface("fe80::abcd/128"),
        ]

        self.ipv4_networks: list[IPv4Network] = [
            IPv4Network("192.168.1.0/24"),
            IPv4Network("192.168.0.0/16"),
            IPv4Network("10.0.0.0/8"),
            IPv4Network("172.16.0.0/12"),
            IPv4Network("172.0.0.0/8"),
        ]

        self.ipv6_networks: list[IPv6Network] = [
            IPv6Network("2001:db8::/32"),
            IPv6Network("2001:db8:0:1::/64"),
            IPv6Network("fd00::/8"),
            IPv6Network("fe80::/10"),
        ]

        self.all_ips: list[IP_TYPE] = self.ipv4_addresses + self.ipv6_addresses
        self.all_networks: list[IP_NET_TYPE] = self.ipv4_networks + self.ipv6_networks

    def test_find_closest_network(self) -> None:
        """Test the _find_closest_network static method."""
        # IPv4 test cases
        ip1 = self.ipv4_addresses[0]  # 192.168.1.10/32
        closest1 = self.synchronizer._find_closest_network(ip1, self.ipv4_networks)
        assert closest1 == ip_network("192.168.1.0/24")  # Most specific match

        ip2 = cast("IPv4Interface", ip_interface("172.16.100.100/32"))
        closest2 = self.synchronizer._find_closest_network(ip2, self.ipv4_networks)
        assert closest2 == ip_network("172.16.0.0/12")

        # IPv6 test cases
        ip3 = self.ipv6_addresses[1]  # 2001:db8:0:1::5/128
        closest3 = self.synchronizer._find_closest_network(ip3, self.ipv6_networks)
        assert closest3 == ip_network("2001:db8:0:1::/64")  # Most specific match

        ip4 = cast("IPv6Interface", ip_interface("2001:db8:9:9::5/128"))
        closest4 = self.synchronizer._find_closest_network(ip4, self.ipv6_networks)
        assert closest4 == ip_network("2001:db8::/32")  # Less specific match

        # No match case
        ip5 = cast("IPv4Interface", ip_interface("8.8.8.8/32"))
        closest5 = self.synchronizer._find_closest_network(ip5, self.ipv4_networks)
        assert closest5 is None  # No match

    def test_find_closest_parent(self) -> None:
        """Test the _find_closest_parent static method."""
        # IPv4 test cases
        subnet1 = cast("IPv4Network", ip_network("192.168.1.0/24"))
        parent1 = self.synchronizer._find_closest_parent(subnet1, self.ipv4_networks)
        assert parent1 == ip_network("192.168.0.0/16")  # Direct parent

        subnet2 = cast("IPv4Network", ip_network("192.168.1.128/25"))  # Not in the list
        parent2 = self.synchronizer._find_closest_parent(subnet2, self.ipv4_networks)
        assert parent2 == ip_network("192.168.1.0/24")  # Parent from list

        # IPv6 test cases
        subnet3 = cast("IPv6Network", ip_network("2001:db8:0:1::/64"))
        parent3 = self.synchronizer._find_closest_parent(subnet3, self.ipv6_networks)
        assert parent3 == ip_network("2001:db8::/32")  # Direct parent

        # No parent case
        subnet4 = cast("IPv4Network", ip_network("8.0.0.0/8"))  # Not in hierarchy
        parent4 = self.synchronizer._find_closest_parent(subnet4, self.ipv4_networks)
        assert parent4 is None  # No parent

    def test_prepare_data_for_neo4j(self) -> None:
        """Test the prepare_data_for_neo4j method."""
        prepared_data = self.synchronizer.prepare_data_for_neo4j(self.all_ips, self.all_networks)

        # Check that the prepared data has the right structure
        assert "ips" in prepared_data
        assert "subnets" in prepared_data

        # Check IP mappings
        ip_mappings = prepared_data["ips"]
        assert len(ip_mappings) > 0

        # Verify specific mappings
        ip_mapping_dict = {item["address"]: item["subnet"] for item in ip_mappings}

        # Check that 192.168.1.10 is mapped to 192.168.1.0/24
        assert ip_mapping_dict.get("192.168.1.10") == "192.168.1.0/24"

        # Check that 2001:db8:0:1::5 is mapped to 2001:db8:0:1::/64
        assert ip_mapping_dict.get("2001:db8:0:1::5") == "2001:db8:0:1::/64"

        # Check subnet mappings
        subnet_mappings = prepared_data["subnets"]
        assert len(subnet_mappings) > 0

        # Verify specific subnet to parent mappings
        subnet_mapping_dict = {item["ip_range"]: item["parent"] for item in subnet_mappings}

        # Check that 192.168.1.0/24 is mapped to 192.168.0.0/16
        assert subnet_mapping_dict.get("192.168.1.0/24") == "192.168.0.0/16"

        # Check that 2001:db8:0:1::/64 is mapped to 2001:db8::/32
        assert subnet_mapping_dict.get("2001:db8:0:1::/64") == "2001:db8::/32"

    def test_parse_ips_for_cypher(self) -> None:
        """Test the _parse_ips_for_cypher static method."""
        # Create sample IPToSubnet instances
        ip_to_subnet1 = IPToSubnet(
            ip_address=cast("IPv4Interface", ip_interface("192.168.1.10/32")),
            subnet=cast("IPv4Network", ip_network("192.168.1.0/24")),
        )
        ip_to_subnet2 = IPToSubnet(
            ip_address=cast("IPv4Interface", ip_interface("10.0.0.5/32")),
            subnet=None,  # Test with None subnet
        )

        ips_to_subnets: list[IPToSubnet] = [ip_to_subnet1, ip_to_subnet2]

        # Parse for Cypher
        parsed = self.synchronizer._parse_ips_for_cypher(ips_to_subnets)

        # Verify structure and values
        assert len(parsed) == 2
        assert parsed[0]["address"] == "192.168.1.10"
        assert parsed[0]["subnet"] == "192.168.1.0/24"
        assert parsed[1]["address"] == "10.0.0.5"
        assert parsed[1]["subnet"] is None

    def test_parse_subnets_for_cypher(self) -> None:
        """Test the _parse_subnets_for_cypher static method."""
        # Create sample SubnetToParent instances
        subnet_to_parent1 = SubnetToParent(
            subnet=cast("IPv4Network", ip_network("192.168.1.0/24")),
            parent=cast("IPv4Network", ip_network("192.168.0.0/16")),
        )
        subnet_to_parent2 = SubnetToParent(
            subnet=cast("IPv4Network", ip_network("10.0.0.0/8")),
            parent=None,  # Test with None parent
        )

        subnets_to_parents: list[SubnetToParent] = [subnet_to_parent1, subnet_to_parent2]

        # Parse for Cypher
        parsed = self.synchronizer._parse_subnets_for_cypher(subnets_to_parents)

        # Verify structure and values
        assert len(parsed) == 2
        assert parsed[0]["ip_range"] == "192.168.1.0/24"
        assert parsed[0]["version"] == 4
        assert parsed[0]["parent"] == "192.168.0.0/16"
        assert parsed[1]["ip_range"] == "10.0.0.0/8"
        assert parsed[1]["version"] == 4
        assert parsed[1]["parent"] is None

    @pytest.mark.parametrize(
        ("ip_addr", "networks", "expected_subnet"),
        [
            # IPv4 cases
            (
                "192.168.1.100/32",
                ["192.168.0.0/16", "192.168.1.0/24", "10.0.0.0/8"],
                "192.168.1.0/24",  # Most specific match
            ),
            (
                "192.168.5.5/32",
                ["192.168.0.0/16", "10.0.0.0/8"],
                "192.168.0.0/16",  # Less specific match
            ),
            (
                "8.8.8.8/32",
                ["192.168.0.0/16", "10.0.0.0/8"],
                None,  # No match
            ),
            # IPv6 cases
            (
                "2001:db8:0:1::5/128",
                ["2001:db8::/32", "2001:db8:0:1::/64"],
                "2001:db8:0:1::/64",  # Most specific match
            ),
            (
                "2001:db8:5::1/128",
                ["2001:db8::/32", "fd00::/8"],
                "2001:db8::/32",  # Less specific match
            ),
        ],
    )
    def test_find_closest_network_scenarios(
        self, ip_addr: str, networks: list[str], expected_subnet: str | None
    ) -> None:
        """Test various IP to subnet matching scenarios."""
        ip = ip_interface(ip_addr)
        net_list = [ip_network(net) for net in networks]

        closest = self.synchronizer._find_closest_network(ip, net_list)

        if expected_subnet is None:
            assert closest is None
        else:
            assert closest == ip_network(expected_subnet)

    @pytest.mark.parametrize(
        ("subnet", "networks", "expected_parent"),
        [
            # IPv4 cases
            (
                "192.168.1.0/24",
                ["192.168.0.0/16", "10.0.0.0/8", "0.0.0.0/0"],
                "192.168.0.0/16",  # Most specific parent
            ),
            (
                "192.168.0.0/16",
                ["0.0.0.0/0", "10.0.0.0/8"],
                "0.0.0.0/0",  # Only possible parent
            ),
            (
                "10.1.0.0/16",
                ["10.0.0.0/8", "192.168.0.0/16"],
                "10.0.0.0/8",  # Direct parent
            ),
            (
                "8.8.8.0/24",
                ["10.0.0.0/8", "192.168.0.0/16"],
                None,  # No parent
            ),
            # IPv6 cases
            (
                "2001:db8:0:1::/64",
                ["2001:db8::/32", "2001::/16", "::/0"],
                "2001:db8::/32",  # Most specific parent
            ),
        ],
    )
    def test_find_closest_parent_scenarios(self, subnet: str, networks: list[str], expected_parent: str | None) -> None:
        """Test various subnet to parent matching scenarios."""
        subnet_obj = ip_network(subnet)
        net_list = [ip_network(net) for net in networks]

        parent = self.synchronizer._find_closest_parent(subnet_obj, net_list)

        if expected_parent is None:
            assert parent is None
        else:
            assert parent == ip_network(expected_parent)
