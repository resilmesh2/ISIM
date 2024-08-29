from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network
from typing import TYPE_CHECKING

import msgspec
from msgspec import field

if TYPE_CHECKING:
    IP_NET_TYPE = IPv4Network | IPv6Network
    IP_TYPE = IPv4Interface | IPv6Interface
else:
    from ipaddress import _BaseAddress as IP_TYPE  # type: ignore
    from ipaddress import _BaseNetwork as IP_NET_TYPE  # type: ignore


class SubnetDTO(msgspec.Struct):
    ip_range: IP_NET_TYPE
    note: str | None = None
    contacts: list[str] = field(default_factory=list)
    parents: list[IP_NET_TYPE] = field(default_factory=list)
    org_units: list[str] = field(default_factory=list)
    version: int = 4

    def __post_init__(self) -> None:
        for p in self.parents:
            if self.ip_range.version != p.version or not self.ip_range.subnet_of(p):  # type: ignore
                raise ValueError(f"Declared {self.ip_range.compressed} is not subnet of {p.compressed}")
        self.version = self.ip_range.version


class HostDTO(msgspec.Struct):
    ip_address: IP_TYPE
    domain_names: list[str] = field(default_factory=list)
    subnets: list[IP_NET_TYPE] = field(default_factory=list)
    uris: list[str] = field(default_factory=list)
    tag: str | None = None
    version: int = 4

    def __post_init__(self) -> None:
        for s in self.subnets:
            if self.ip_address not in s:
                raise ValueError(f"Declared {self.ip_address.compressed} is not in subnet {s.compressed}")
        self.version = self.ip_address.version


class SoftwareVersionDTO(msgspec.Struct):
    ip_addresses: list[IP_TYPE]
    version: str | None = None
    service: str | None = None
    protocol: str | None = None
    port: int | None = None
    tag: str | None = None

    def __post_init__(self) -> None:
        if self.version is None and (self.protocol is None or self.port is None or self.service is None):
            raise ValueError("Either version or port and protocol and service must be set!")
        if not self.ip_addresses:
            raise ValueError("IP Addresses are mandatory for service definition!")


class DeviceDTO(msgspec.Struct):
    name: str
    manufacturer: str | None = None
    model: str | None = None
    ip_address: IP_TYPE | None = None
    org_units: list[str] = field(default_factory=list)
    power: str | None = None
    state: str | None = None


class ApplicationDTO(msgspec.Struct):
    device: str
    name: str


class OrgUnitDTO(msgspec.Struct):
    name: str
    locations: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)


class AssetListInputDTO(msgspec.Struct):
    hosts: list[HostDTO] = field(default_factory=list)
    subnets: list[SubnetDTO] = field(default_factory=list)
    software_versions: list[SoftwareVersionDTO] = field(default_factory=list)
    devices: list[DeviceDTO] = field(default_factory=list)
    applications: list[ApplicationDTO] = field(default_factory=list)
    org_units: list[OrgUnitDTO] = field(default_factory=list)

    def flatten_related_relationships(self) -> None:
        declared_hosts: set[IPv4Interface | IPv6Interface] = set()
        declared_subnets: set[IPv4Network | IPv6Network] = set()
        related_undeclared_hosts: set[IPv4Interface | IPv6Interface] = set()
        related_undeclared_subnets: set[IPv4Network | IPv6Network] = set()
        # we obtain declared hosts and related_undeclared_subnet candidates from  hosts
        for host in self.hosts:
            declared_hosts.add(host.ip_address)
            related_undeclared_subnets = related_undeclared_subnets.union(set(host.subnets))

        # we obtain declared subnets and related_undeclared_subnet candidates from subnets
        for subnet in self.subnets:
            declared_subnets.add(subnet.ip_range)
            related_undeclared_subnets = related_undeclared_subnets.union(set(subnet.parents))

        # we obtain related undeclared hosts candidates from devices
        related_undeclared_hosts.update(dev.ip_address for dev in self.devices if dev.ip_address)
        # we obtained related undeclared hosts candidates from sw version
        for sw in self.software_versions:
            related_undeclared_hosts = related_undeclared_hosts.union(set(sw.ip_addresses))
        # eliminate declared from undeclared
        related_undeclared_hosts = related_undeclared_hosts.difference(declared_hosts)
        related_undeclared_subnets = related_undeclared_subnets.difference(declared_subnets)

        # add undeclared to asset list
        self.hosts += [HostDTO(ip_address=h) for h in related_undeclared_hosts if h]
        self.subnets += [SubnetDTO(ip_range=s) for s in related_undeclared_subnets if s]
