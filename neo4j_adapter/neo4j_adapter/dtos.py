from __future__ import annotations

from ipaddress import IPv4Interface, IPv6Interface
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, computed_field

JSONValue = object

IP_TYPE = IPv4Interface | IPv6Interface


class BaseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaginationQueryDTO(BaseDTO):
    limit: int = 50
    offset: int = 0


class MissionQueryDTO(BaseDTO):
    limit: int = 50


class AssetInfoQueryDTO(PaginationQueryDTO):
    ip: IP_TYPE | None = None


class CveQueryDTO(PaginationQueryDTO):
    cve_id: str


class IpQueryDTO(BaseDTO):
    ip: IP_TYPE


class MessageResponseDTO(BaseDTO):
    message: str


class EmptyBodyDTO(BaseDTO):
    pass


class PlainTextResponseDTO(RootModel[str]):
    pass


class MissionInfoDTO(BaseDTO):
    name: str
    description: str | None = None
    criticality: int | None = None
    confidentiality_requirement: int | None = None
    integrity_requirement: int | None = None
    availability_requirement: int | None = None
    structure: str | None = None


class MissionInfoResponseDTO(RootModel[list[MissionInfoDTO]]):
    pass


class NodeCentralityDTO(BaseDTO):
    degree_centrality: float | None = None
    pagerank_centrality: float | None = None
    topology_betweenness: float | None = None
    topology_degree: float | None = None


class IPAssetInformationDTO(BaseDTO):
    ip: str
    domain_names: list[str] = Field(default_factory=list)
    subnets: list[str] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    missions: list[str] = Field(default_factory=list)
    nodes: list[NodeCentralityDTO] = Field(default_factory=list)

    @computed_field(return_type=int)
    def critical(self) -> int:
        return 1 if self.missions else 0

    def serialize(self) -> dict[str, Any]:
        return self.model_dump()


class AssetInfoResponseDTO(RootModel[list[IPAssetInformationDTO]]):
    pass


NodeMap = dict[str, JSONValue]
OrganizationUnitsRowDTO = tuple[NodeMap, NodeMap | None, NodeMap | None]
SubnetsRowDTO = tuple[NodeMap, NodeMap | None, NodeMap | None, NodeMap | None, NodeMap | None]
IpAssetsRowDTO = tuple[NodeMap, NodeMap | None, NodeMap | None, NodeMap | None, NodeMap | None]
DevicesRowDTO = tuple[NodeMap, NodeMap | None, NodeMap | None, NodeMap | None, NodeMap | None, NodeMap | None]
ApplicationsRowDTO = tuple[NodeMap, NodeMap | None]


class OrganizationUnitsResponseDTO(RootModel[list[OrganizationUnitsRowDTO]]):
    pass


class SubnetsResponseDTO(RootModel[list[SubnetsRowDTO]]):
    pass


class IpAssetsResponseDTO(RootModel[list[IpAssetsRowDTO]]):
    pass


class DevicesResponseDTO(BaseDTO):
    pass


class ApplicationsResponseDTO(RootModel[list[ApplicationsRowDTO]]):
    pass


class CveSummaryDTO(BaseDTO):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    CVE_id: str | None = None
    description: str | None = None


CveSummaryRowDTO = tuple[CveSummaryDTO]


class CveSummaryResponseDTO(RootModel[list[CveSummaryRowDTO]]):
    pass


CveNodeRowDTO = tuple[NodeMap]


class CveNodeResponseDTO(RootModel[list[CveNodeRowDTO]]):
    pass
