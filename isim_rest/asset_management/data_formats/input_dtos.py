from ipaddress import IPv4Interface, IPv4Network, IPv6Interface, IPv6Network
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    IP_NET_TYPE = IPv4Network | IPv6Network
    IP_TYPE = IPv4Interface | IPv6Interface
else:
    from ipaddress import _BaseAddress as IP_TYPE  # type: ignore
    from ipaddress import _BaseNetwork as IP_NET_TYPE  # type: ignore

T = TypeVar("T")


class BaseDTO(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={
            IPv4Interface: lambda value: value.ip.compressed,
            IPv6Interface: lambda value: value.ip.compressed,
            IPv4Network: lambda value: value.with_prefixlen,
            IPv6Network: lambda value: value.with_prefixlen,
        },
        extra="ignore",
    )

    @field_validator("*", mode="before")
    @classmethod
    def _strip_empty_strings(cls, value: Any) -> Any:
        if isinstance(value, str) and value == "":
            return None
        return value


class SubnetDTO(BaseDTO):
    ip_range: IP_NET_TYPE
    note: str | None = None
    contacts: list[str] = Field(default_factory=list[str])
    parents: list[IP_NET_TYPE] = Field(default_factory=list[IP_NET_TYPE])
    org_units: list[str] = Field(default_factory=list[str])
    version: int | None = None

    @model_validator(mode="after")
    def _validate_parents(self) -> "SubnetDTO":
        for parent in self.parents:
            if self.ip_range.version != parent.version or not self.ip_range.subnet_of(parent):  # type: ignore
                raise ValueError(f"Declared {self.ip_range.compressed} is not subnet of {parent.compressed}")
        if self.version is None:
            self.version = self.ip_range.version
        return self


class HostDTO(BaseDTO):
    ip_address: IP_TYPE
    domain_names: list[str] = Field(default_factory=list[str])
    subnets: list[IP_NET_TYPE] = Field(default_factory=list[IP_NET_TYPE])
    uris: list[str] = Field(default_factory=list[str])
    tag: list[str] = Field(default_factory=list[str])
    version: int | None = None

    @model_validator(mode="after")
    def _validate_subnets(self) -> "HostDTO":
        for subnet in self.subnets:
            if self.ip_address not in subnet:
                raise ValueError(f"Declared {self.ip_address.compressed} is not in subnet {subnet.compressed}")
        if self.version is None:
            self.version = self.ip_address.version
        return self


class SoftwareVersionDTO(BaseDTO):
    ip_addresses: list[IP_TYPE]
    version: str | None = None
    service: str | None = None
    protocol: str | None = None
    port: int | None = None
    tag: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def _validate_fields(self) -> "SoftwareVersionDTO":
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
    org_units: list[str] = Field(default_factory=list[str])
    power: str | None = None
    state: str | None = None


class ApplicationDTO(BaseDTO):
    device: str
    name: str


class OrgUnitDTO(BaseDTO):
    name: str
    locations: list[str] = Field(default_factory=list[str])
    parents: list[str] = Field(default_factory=list[str])


class EasmDTO(BaseDTO):
    port: str
    protocol: str
    service: str
    ip: IP_TYPE | None = None
    domain_name: str | None = None
    software_versions: list[dict[str, str]] = Field(default_factory=list[dict[str, str]])

    @model_validator(mode="after")
    def _validate_ip_or_domain(self) -> "EasmDTO":
        if self.ip is None and self.domain_name is None:
            raise ValueError("Either IP or domain is necessary!")
        return self


class AssetListInputDTO(BaseDTO):
    hosts: list[HostDTO] = Field(default_factory=list[HostDTO])
    subnets: list[SubnetDTO] = Field(default_factory=list[SubnetDTO])
    software_versions: list[SoftwareVersionDTO] = Field(default_factory=list[SoftwareVersionDTO])
    devices: list[DeviceDTO] = Field(default_factory=list[DeviceDTO])
    applications: list[ApplicationDTO] = Field(default_factory=list[ApplicationDTO])
    org_units: list[OrgUnitDTO] = Field(default_factory=list[OrgUnitDTO])

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

    def save_to_db(self, *, bolt: str, user: str, password: str) -> None:
        """
        Persist assets using neomodel-backed models.
        """
        from neo4j_adapter.asset_model_mapper import AssetModelMapper

        AssetModelMapper.store_assets(self, bolt=bolt, user=user, password=password)

    @classmethod
    def from_models(
        cls,
        *,
        ips: list["IP"] | None = None,
        subnets: list["Subnet"] | None = None,
        software_versions: list["SoftwareVersion"] | None = None,
        devices: list["Device"] | None = None,
        applications: list["Application"] | None = None,
        org_units: list["OrganizationUnit"] | None = None,
    ) -> "AssetListInputDTO":
        """
        Convert model instances to DTOs for JSON serialization.
        """
        from neo4j_adapter.asset_model_mapper import AssetModelMapper

        return AssetModelMapper.asset_list_from_models(
            ips=ips,
            subnets=subnets,
            software_versions=software_versions,
            devices=devices,
            applications=applications,
            org_units=org_units,
        )


class MissionDTO(BaseModel):
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
    or_: list[int] = Field(default_factory=list[int], alias="or")
    and_: list[int] = Field(default_factory=list[int], alias="and")


class HostMissionDTO(BaseDTO):
    id: int
    hostname: str
    ip: IP_TYPE


class NodeMissionDTO(BaseDTO):
    aggregations: AggregationsDTO
    missions: list[MissionDTO] = Field(default_factory=list[MissionDTO])
    services: list[ServiceDTO] = Field(default_factory=list[ServiceDTO])
    hosts: list[HostMissionDTO] = Field(default_factory=list[HostMissionDTO])

    @model_validator(mode="after")
    def _validate_required(self) -> "NodeMissionDTO":
        if not self.missions:
            raise ValueError("Missions are mandatory!")
        if not self.services:
            raise ValueError("Services are mandatory!")
        if not self.hosts:
            raise ValueError("Hosts are mandatory!")
        return self


class DirectedRelationshipDTO(BaseDTO, Generic[T]):
    from_: T = Field(alias="from")
    to: T


class UndirectedRelationshipDTO(BaseDTO, Generic[T]):
    first: T
    second: T


class RelationshipDTO(BaseDTO):
    one_way: list[DirectedRelationshipDTO[int]] = Field(default_factory=list[DirectedRelationshipDTO[int]])
    two_way: list[UndirectedRelationshipDTO[int]] = Field(default_factory=list[UndirectedRelationshipDTO[int]])
    dependencies: list[DirectedRelationshipDTO[int]] = Field(default_factory=list[DirectedRelationshipDTO[int]])
    supports: list[DirectedRelationshipDTO[str]] = Field(default_factory=list[DirectedRelationshipDTO[str]])
    has_identity: list[DirectedRelationshipDTO[str]] = Field(default_factory=list[DirectedRelationshipDTO[str]])


class MissionListInputDTO(BaseDTO):
    nodes: NodeMissionDTO
    relationships: RelationshipDTO


class NmapTopologyDTO(BaseDTO):
    data: list[dict[str, Any]]
    time: str


class MissionCriticalityDTO(BaseDTO):
    ip: IP_TYPE = Field(alias="ip")
    hostname: str = Field(alias="hostname")
    criticality: float = Field(alias="criticality")


class SLPEnrichmentDTO(BaseDTO):
    domain: str = Field(alias="domain")
    ip: IP_TYPE = Field(alias="ip")
    # str for sp_risk_score is used for "null" value that must be passed to Neo4j as string
    sp_risk_score: int | str = Field(alias="sp_risk_score")
    subnet: IP_NET_TYPE = Field(alias="subnet")
    tag: str = Field(alias="tag")
