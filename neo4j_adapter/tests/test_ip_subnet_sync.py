from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network, ip_interface, ip_network
from unittest.mock import Mock, patch

import pytest

from neo4j_adapter.ip_subnet_sync import IPAddress, Network, NetworkManager


class TestIPAddress:
    """Test cases for IPAddress class."""

    def test_invalid_ip_address(self):
        """Test that invalid IP addresses raise ValueError."""
        with pytest.raises(ValueError, match="Invalid IP interface"):
            IPAddress("invalid.ip", "4")

    def test_find_nearest_subnet_ipv4(self):
        """Test finding the nearest subnet for an IPv4 address."""
        ip = IPAddress("192.168.1.100/32", "4")

        # Create test networks
        networks = [
            Network("192.168.0.0/16", "4"),
            Network("192.168.1.0/24", "4"),
            Network("192.168.1.64/26", "4"),
        ]

        result = ip.find_nearest_subnet(networks)

        # Should find the most specific subnet that contains this IP
        assert result is not None
        assert result.range == "192.168.1.64/26"
        assert ip.subnet == result

    def test_find_nearest_subnet_no_match(self):
        """Test when no subnet matches the IP address."""
        ip = IPAddress("10.0.0.1/32", "4")

        networks = [
            Network("192.168.0.0/16", "4"),
            Network("172.16.0.0/12", "4"),
        ]

        result = ip.find_nearest_subnet(networks)

        assert result is None
        assert ip.subnet is None

    def test_find_nearest_subnet_version_mismatch(self):
        """Test that IPv4 address doesn't match IPv6 networks."""
        ip = IPAddress("192.168.1.1/32", "4")

        networks = [
            Network("2001:db8::/32", "6"),
            Network("fe80::/64", "6"),
        ]

        result = ip.find_nearest_subnet(networks)

        assert result is None
        assert ip.subnet is None


class TestNetwork:
    """Test cases for Network class."""

    def test_network_creation_ipv4(self):
        """Test creating a valid IPv4 network."""
        net = Network("192.168.1.0/24", "4")
        assert net.range == "192.168.1.0/24"
        assert net.version == "4"
        assert isinstance(net.network_object, IPv4Network)
        assert net.prefix_length == 24

    def test_network_creation_ipv6(self):
        """Test creating a valid IPv6 network."""
        net = Network("2001:db8::/64", "6")
        assert net.range == "2001:db8::/64"
        assert net.version == "6"
        assert isinstance(net.network_object, IPv6Network)
        assert net.prefix_length == 64

    def test_invalid_network(self):
        """Test that invalid network ranges raise ValueError."""
        with pytest.raises(ValueError, match="Invalid network range"):
            Network("invalid.network", "4")

    def test_contains_network(self):
        """Test network containment logic."""
        parent = Network("192.168.0.0/16", "4")
        child = Network("192.168.1.0/24", "4")
        sibling = Network("10.0.0.0/8", "4")

        assert parent.contains_network(child)
        assert not parent.contains_network(sibling)
        assert not child.contains_network(parent)

    def test_find_nearest_parent(self):
        """Test finding the nearest parent network."""
        child = Network("192.168.1.0/24", "4")

        potential_parents = [
            Network("0.0.0.0/0", "4"),  # Most general
            Network("192.168.0.0/16", "4"),  # More specific
            Network("192.0.0.0/8", "4"),  # Less specific than /16
        ]

        result = child.find_nearest_parent(potential_parents)

        # Should find the most specific parent
        assert result is not None
        assert result.range == "192.168.0.0/16"
        assert child.parent_subnet == result
        assert child in result.child_subnets

    def test_find_nearest_parent_no_match(self):
        """Test when no parent network is found."""
        child = Network("10.0.0.0/24", "4")

        potential_parents = [
            Network("192.168.0.0/16", "4"),
            Network("172.16.0.0/12", "4"),
        ]

        result = child.find_nearest_parent(potential_parents)

        assert result is None
        assert child.parent_subnet is None

    def test_network_equality(self):
        """Test network equality and hashing."""
        net1 = Network("192.168.1.0/24", "4")
        net2 = Network("192.168.1.0/24", "4")
        net3 = Network("192.168.2.0/24", "4")

        assert net1 == net2
        assert net1 != net3
        assert hash(net1) == hash(net2)
        assert hash(net1) != hash(net3)


class TestNetworkManager:
    """Test cases for NetworkManager class."""

    def test_add_ip(self):
        """Test adding IP addresses to the manager."""
        manager = NetworkManager()
        ip = manager.add_ip("192.168.1.1/32", "4")

        assert len(manager.ip_addresses) == 1
        assert manager.ip_addresses[0] == ip
        assert ip.address == "192.168.1.1/32"

    def test_add_network(self):
        """Test adding networks to the manager."""
        manager = NetworkManager()
        net = manager.add_network("192.168.1.0/24", "4")

        assert len(manager.networks) == 1
        assert manager.networks[0] == net
        assert net.range == "192.168.1.0/24"

    def test_build_ip_subnet_relationships(self):
        """Test building relationships between IPs and subnets."""
        manager = NetworkManager()

        # Add networks
        manager.add_network("192.168.0.0/16", "4")
        manager.add_network("192.168.1.0/24", "4")
        manager.add_network("10.0.0.0/8", "4")

        # Add IPs
        ip1 = manager.add_ip("192.168.1.100/32", "4")
        ip2 = manager.add_ip("10.0.0.1/32", "4")
        ip3 = manager.add_ip("172.16.1.1/32", "4")  # No matching subnet

        manager.build_ip_subnet_relationships()

        # Check relationships
        assert ip1.subnet is not None
        assert ip1.subnet.range == "192.168.1.0/24"  # Most specific match

        assert ip2.subnet is not None
        assert ip2.subnet.range == "10.0.0.0/8"

        assert ip3.subnet is None  # No matching subnet

    def test_build_network_hierarchy(self):
        """Test building hierarchical relationships between networks."""
        manager = NetworkManager()

        # Add networks in random order
        root = manager.add_network("0.0.0.0/0", "4")
        specific = manager.add_network("192.168.1.0/24", "4")
        intermediate = manager.add_network("192.168.0.0/16", "4")
        very_specific = manager.add_network("192.168.1.128/25", "4")

        manager.build_network_hierarchy()

        # Check hierarchy
        assert root.parent_subnet is None  # Root has no parent
        assert intermediate.parent_subnet == root
        assert specific.parent_subnet == intermediate
        assert very_specific.parent_subnet == specific

        # Check child relationships
        assert intermediate in root.child_subnets
        assert specific in intermediate.child_subnets
        assert very_specific in specific.child_subnets

    def test_mixed_ip_versions(self):
        """Test handling mixed IPv4 and IPv6 addresses."""
        manager = NetworkManager()

        # Add mixed networks
        manager.add_network("192.168.0.0/16", "4")
        manager.add_network("2001:db8::/32", "6")
        manager.add_network("192.168.1.0/24", "4")
        manager.add_network("2001:db8:1::/64", "6")

        # Add mixed IPs
        ipv4 = manager.add_ip("192.168.1.100/32", "4")
        ipv6 = manager.add_ip("2001:db8:1::100/128", "6")

        manager.build_ip_subnet_relationships()

        # IPv4 should only match IPv4 networks
        assert ipv4.subnet is not None
        assert ipv4.subnet.range == "192.168.1.0/24"

        # IPv6 should only match IPv6 networks
        assert ipv6.subnet is not None
        assert ipv6.subnet.range == "2001:db8:1::/64"

    def test_clear_relationships_on_rebuild(self):
        """Test that relationships are cleared when rebuilding hierarchy."""
        manager = NetworkManager()

        net1 = manager.add_network("192.168.0.0/16", "4")
        net2 = manager.add_network("192.168.1.0/24", "4")

        # Build initial hierarchy
        manager.build_network_hierarchy()
        assert net2.parent_subnet == net1
        assert net2 in net1.child_subnets

        # Add a new intermediate network
        net3 = manager.add_network("192.168.1.0/25", "4")  # More specific than net2

        # Rebuild hierarchy
        manager.build_network_hierarchy()

        # Check that relationships were updated
        assert net3.parent_subnet == net2
        assert net2.parent_subnet == net1


class TestComplexHierarchies:
    """Test complex network hierarchy scenarios."""

    def test_deep_hierarchy(self):
        """Test a deep network hierarchy."""
        manager = NetworkManager()

        # Create a deep hierarchy
        networks = [
            "0.0.0.0/0",
            "10.0.0.0/8",
            "10.1.0.0/16",
            "10.1.1.0/24",
            "10.1.1.0/25",
            "10.1.1.0/26",
            "10.1.1.0/27",
        ]

        for net_range in networks:
            manager.add_network(net_range, "4")

        manager.build_network_hierarchy()

        # Verify the chain
        net_objects = {net.range: net for net in manager.networks}

        assert net_objects["0.0.0.0/0"].parent_subnet is None
        assert net_objects["10.0.0.0/8"].parent_subnet == net_objects["0.0.0.0/0"]
        assert net_objects["10.1.0.0/16"].parent_subnet == net_objects["10.0.0.0/8"]
        assert net_objects["10.1.1.0/24"].parent_subnet == net_objects["10.1.0.0/16"]
        assert net_objects["10.1.1.0/25"].parent_subnet == net_objects["10.1.1.0/24"]
        assert net_objects["10.1.1.0/26"].parent_subnet == net_objects["10.1.1.0/25"]
        assert net_objects["10.1.1.0/27"].parent_subnet == net_objects["10.1.1.0/26"]

    def test_multiple_branches(self):
        """Test a hierarchy with multiple branches."""
        manager = NetworkManager()

        # Create multiple branches
        networks = [
            "0.0.0.0/0",  # Root
            "10.0.0.0/8",  # Branch 1
            "192.168.0.0/16",  # Branch 2
            "10.1.0.0/16",  # Branch 1.1
            "10.2.0.0/16",  # Branch 1.2
            "192.168.1.0/24",  # Branch 2.1
            "192.168.2.0/24",  # Branch 2.2
        ]

        for net_range in networks:
            manager.add_network(net_range, "4")

        manager.build_network_hierarchy()

        net_objects = {net.range: net for net in manager.networks}

        # Check root
        root = net_objects["0.0.0.0/0"]
        assert len(root.child_subnets) == 2

        # Check branches
        branch1 = net_objects["10.0.0.0/8"]
        branch2 = net_objects["192.168.0.0/16"]

        assert branch1.parent_subnet == root
        assert branch2.parent_subnet == root

        assert len(branch1.child_subnets) == 2
        assert len(branch2.child_subnets) == 2

    def test_overlapping_networks(self):
        """Test handling of overlapping but not nested networks."""
        manager = NetworkManager()

        # These networks overlap but are not hierarchically related
        manager.add_network("192.168.0.0/23", "4")  # 192.168.0.0 - 192.168.1.255
        manager.add_network("192.168.1.0/23", "4")  # 192.168.1.0 - 192.168.2.255

        manager.build_network_hierarchy()

        # Neither should be parent of the other
        net1 = manager.networks[0]
        net2 = manager.networks[1]

        assert net1.parent_subnet is None
        assert net2.parent_subnet is None
        assert len(net1.child_subnets) == 0
        assert len(net2.child_subnets) == 0

    @pytest.mark.parametrize(
        "ip_addr,expected_subnet",
        [
            ("192.168.1.1/32", "192.168.1.0/24"),
            ("192.168.1.200/32", "192.168.1.0/24"),
            ("192.168.2.1/32", "192.168.0.0/16"),
            ("10.0.0.1/32", None),
            ("192.168.1.1", "192.168.1.0/24"),  # Test without prefix
        ],
    )
    def test_ip_subnet_matching_scenarios(self, ip_addr, expected_subnet):
        """Test various IP to subnet matching scenarios."""
        manager = NetworkManager()

        # Add some test networks
        manager.add_network("192.168.0.0/16", "4")
        manager.add_network("192.168.1.0/24", "4")

        # Add IP and build relationships
        ip = manager.add_ip(ip_addr, "4")
        manager.build_ip_subnet_relationships()

        if expected_subnet:
            assert ip.subnet is not None
            assert ip.subnet.range == expected_subnet
        else:
            assert ip.subnet is None

