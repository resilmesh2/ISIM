from ipaddress import IPv4Interface, IPv6Interface, IPv4Network, IPv6Network, IPv4Address, IPv6Address
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
    parent: list[IP_NET_TYPE] = field(default_factory=list)
    org_units: list[str] = field(default_factory=list)


class HostDTO(msgspec.Struct):
    ip_address: IP_TYPE
    domain_names: list[str] = field(default_factory=list)
    subnets: list[IP_NET_TYPE] = field(default_factory=list)
    uris: list[str] = field(default_factory=list)
    tag: str | None = None


class SoftwareVersionDTO(msgspec.Struct):
    ip_addresses: list[IP_TYPE]
    version: str | None = None
    protocol: str | None = None
    port: int | None = None
    tag: str | None = None

    def __post_init__(self):
        if self.version is None and (self.protocol is None and self.port is None):
            raise ValueError("Either version or port and protocol must be set!")


class DeviceDTO(msgspec.Struct):
    name: str
    manufacturer: str | None = None
    model: str | None = None
    ip_address: IP_TYPE | None = None
    org_units: list[str] = field(default_factory=list)


class ApplicationDTO(msgspec.Struct):
    device: str
    name: str


class OrgUnitDTO(msgspec.Struct):
    name: str
    locations: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)


class AssetListDTO(msgspec.Struct):
    hosts: list[HostDTO] = field(default_factory=list)
    subnets: list[SubnetDTO] = field(default_factory=list)
    software_versions: list[SoftwareVersionDTO] = field(default_factory=list)
    devices: list[DeviceDTO] = field(default_factory=list)
    applications: list[ApplicationDTO] = field(default_factory=list)
    org_units: list[OrgUnitDTO] = field(default_factory=list)
