from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network
from typing import TYPE_CHECKING, Any

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
    tag: list[str] = field(default_factory=list)
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
    tag: list[str] = field(default_factory=list)

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


class EasmDTO(msgspec.Struct):
    port: str
    protocol: str
    service: str
    ip: IP_TYPE | None = None
    domain_name: str | None = None
    software_versions: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ip is None and self.domain_name is None:
            raise ValueError("Either IP or domain is necessary!")


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


class MissionDTO(msgspec.Struct, forbid_unknown_fields=True, omit_defaults=True):
    id: int
    name: str
    criticality: int | None = None
    description: str | None = None
    confidentiality_requirement: int | None = None
    integrity_requirement: int | None = None
    availability_requirement: int | None = None


class ServiceDTO(msgspec.Struct):
    id: int
    name: str


class AggregationsDTO(msgspec.Struct):
    or_: list[int] = field(default_factory=list, name="or")
    and_: list[int] = field(default_factory=list, name="and")


class HostMissionDTO(msgspec.Struct):
    id: int
    hostname: str
    ip: IP_TYPE


class NodeMissionDTO(msgspec.Struct):
    aggregations: AggregationsDTO
    missions: list[MissionDTO] = field(default_factory=list)
    services: list[ServiceDTO] = field(default_factory=list)
    hosts: list[HostMissionDTO] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.missions:
            raise ValueError("Missions are mandatory!")
        if not self.services:
            raise ValueError("Services are mandatory!")
        if not self.hosts:
            raise ValueError("Hosts are mandatory!")


class DirectedRelationshipDTO[T](msgspec.Struct):
    from_: T = field(name="from")
    to: T


class UndirectedRelationshipDTO[T](msgspec.Struct):
    first: T
    second: T


class RelationshipDTO(msgspec.Struct):
    one_way: list[DirectedRelationshipDTO[int]] = field(default_factory=list)
    two_way: list[UndirectedRelationshipDTO[int]] = field(default_factory=list)
    dependencies: list[DirectedRelationshipDTO[int]] = field(default_factory=list)
    supports: list[DirectedRelationshipDTO[str]] = field(default_factory=list)
    has_identity: list[DirectedRelationshipDTO[str]] = field(default_factory=list)


class MissionListInputDTO(msgspec.Struct):
    nodes: NodeMissionDTO
    relationships: RelationshipDTO


class NmapTopologyDTO(msgspec.Struct):
    data: list[dict[str, Any]]
    time: str


class MissionCriticalityDTO(msgspec.Struct):
    ip: IP_TYPE = field(name="ip")
    hostname: str = field(name="hostname")
    criticality: float = field(name="criticality")


class SLPEnrichmentDTO(msgspec.Struct):
    domain: str = field(name="domain")
    ip: IP_TYPE = field(name="ip")
    # str for sp_risk_score is used for "null" value that must be passed to Neo4j as string
    sp_risk_score: int | str = field(name="sp_risk_score")
    subnet: IP_NET_TYPE = field(name="subnet")
    tag: str = field(name="tag")
