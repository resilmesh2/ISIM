from __future__ import annotations

from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

JSONValue = object

IP_NET_TYPE = IPv4Network | IPv6Network
IP_TYPE = IPv4Interface | IPv6Interface


class BaseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubnetDTO(BaseDTO):
    ip_range: IP_NET_TYPE
    note: str | None = None
    contacts: list[str] = Field(default_factory=list)
    parents: list[IP_NET_TYPE] = Field(default_factory=list)
    org_units: list[str] = Field(default_factory=list)
    version: int = 4

    @model_validator(mode="after")
    def validate_parents(self) -> "SubnetDTO":
        for parent in self.parents:
            if self.ip_range.version != parent.version or not self.ip_range.subnet_of(parent):
                raise ValueError(f"Declared {self.ip_range.compressed} is not subnet of {parent.compressed}")
        object.__setattr__(self, "version", self.ip_range.version)
        return self


class HostDTO(BaseDTO):
    ip_address: IP_TYPE
    domain_names: list[str] = Field(default_factory=list)
    subnets: list[IP_NET_TYPE] = Field(default_factory=list)
    uris: list[str] = Field(default_factory=list)
    tag: list[str] = Field(default_factory=list)
    version: int = 4

    @model_validator(mode="after")
    def validate_subnets(self) -> "HostDTO":
        for subnet in self.subnets:
            if self.ip_address not in subnet:
                raise ValueError(f"Declared {self.ip_address.compressed} is not in subnet {subnet.compressed}")
        object.__setattr__(self, "version", self.ip_address.version)
        return self


class SoftwareVersionDTO(BaseDTO):
    ip_addresses: list[IP_TYPE]
    version: str | None = None
    service: str | None = None
    protocol: str | None = None
    port: int | None = None
    tag: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_required_fields(self) -> SoftwareVersionDTO:
        if self.version is None and (self.protocol is None or self.port is None or self.service is None):
            raise ValueError("Either version or port and protocol and service must be set!")
        if not self.ip_addresses:
            raise ValueError("IP Addresses are mandatory for service definition!")
        return self


class DeviceDTO(BaseDTO):
    name: str
    manufacturer: str | None = None
    model: str | None = None
    ip_address: IP_TYPE | None = None
    org_units: list[str] = Field(default_factory=list)
    power: str | None = None
    state: str | None = None


class ApplicationDTO(BaseDTO):
    device: str
    name: str


class OrgUnitDTO(BaseDTO):
    name: str
    locations: list[str] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)


class EasmDTO(BaseDTO):
    port: str
    protocol: str
    service: str
    ip: IP_TYPE | None = None
    domain_name: str | None = None
    software_versions: list[dict[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_location(self) -> "EasmDTO":
        if self.ip is None and self.domain_name is None:
            raise ValueError("Either IP or domain is necessary!")
        return self


class AssetListInputDTO(BaseDTO):
    hosts: list[HostDTO] = Field(default_factory=list)
    subnets: list[SubnetDTO] = Field(default_factory=list)
    software_versions: list[SoftwareVersionDTO] = Field(default_factory=list)
    devices: list[DeviceDTO] = Field(default_factory=list)
    applications: list[ApplicationDTO] = Field(default_factory=list)
    org_units: list[OrgUnitDTO] = Field(default_factory=list)

    def flatten_related_relationships(self) -> None:
        declared_hosts: set[IP_TYPE] = set()
        declared_subnets: set[IP_NET_TYPE] = set()
        related_undeclared_hosts: set[IP_TYPE] = set()
        related_undeclared_subnets: set[IP_NET_TYPE] = set()

        for host in self.hosts:
            declared_hosts.add(host.ip_address)
            related_undeclared_subnets.update(host.subnets)

        for subnet in self.subnets:
            declared_subnets.add(subnet.ip_range)
            related_undeclared_subnets.update(subnet.parents)

        related_undeclared_hosts.update(
            device.ip_address for device in self.devices if device.ip_address is not None
        )

        for software_version in self.software_versions:
            related_undeclared_hosts.update(software_version.ip_addresses)

        related_undeclared_hosts = related_undeclared_hosts.difference(declared_hosts)
        related_undeclared_subnets = related_undeclared_subnets.difference(declared_subnets)

        self.hosts += [HostDTO(ip_address=host) for host in related_undeclared_hosts]
        self.subnets += [SubnetDTO(ip_range=subnet) for subnet in related_undeclared_subnets]


class MissionDTO(BaseDTO):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    criticality: int | None = None
    description: str | None = None
    confidentiality_requirement: int | None = None
    integrity_requirement: int | None = None
    availability_requirement: int | None = None


class ServiceDTO(BaseDTO):
    id: int
    name: str


class AggregationsDTO(BaseDTO):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    or_: list[int] = Field(default_factory=list, alias="or")
    and_: list[int] = Field(default_factory=list, alias="and")


class HostMissionDTO(BaseDTO):
    id: int
    hostname: str
    ip: IP_TYPE


class NodeMissionDTO(BaseDTO):
    aggregations: AggregationsDTO
    missions: list[MissionDTO] = Field(default_factory=list)
    services: list[ServiceDTO] = Field(default_factory=list)
    hosts: list[HostMissionDTO] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mandatory_lists(self) -> "NodeMissionDTO":
        if not self.missions:
            raise ValueError("Missions are mandatory!")
        if not self.services:
            raise ValueError("Services are mandatory!")
        if not self.hosts:
            raise ValueError("Hosts are mandatory!")
        return self


T = TypeVar("T")


class DirectedRelationshipDTO(BaseDTO, Generic[T]):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: T = Field(alias="from")
    to: T


class UndirectedRelationshipDTO(BaseDTO, Generic[T]):
    first: T
    second: T


class RelationshipDTO(BaseDTO):
    one_way: list[DirectedRelationshipDTO[int]] = Field(default_factory=list)
    two_way: list[UndirectedRelationshipDTO[int]] = Field(default_factory=list)
    dependencies: list[DirectedRelationshipDTO[int]] = Field(default_factory=list)
    supports: list[DirectedRelationshipDTO[str]] = Field(default_factory=list)
    has_identity: list[DirectedRelationshipDTO[str]] = Field(default_factory=list)


class MissionListInputDTO(BaseDTO):
    nodes: NodeMissionDTO
    relationships: RelationshipDTO


class NmapTopologyDTO(BaseDTO):
    data: list[dict[str, JSONValue]]
    time: str


class MissionCriticalityDTO(BaseDTO):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ip: IP_TYPE = Field(alias="ip")
    hostname: str = Field(alias="hostname")
    criticality: float = Field(alias="criticality")


class SLPEnrichmentDTO(BaseDTO):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    domain: str = Field(alias="domain")
    ip: IP_TYPE = Field(alias="ip")
    sp_risk_score: int | str = Field(alias="sp_risk_score")
    subnet: IP_NET_TYPE = Field(alias="subnet")
    tag: str = Field(alias="tag")


class MissionPostDTO(MissionListInputDTO):
    pass


class AssetsPostDTO(AssetListInputDTO):
    pass


class EasmPostDTO(RootModel[list[EasmDTO]]):
    pass


class TraceroutePostDTO(NmapTopologyDTO):
    pass


class StoreCriticalityPostDTO(RootModel[list[MissionCriticalityDTO]]):
    pass


class SlpEnrichmentPostDTO(RootModel[list[SLPEnrichmentDTO]]):
    pass
