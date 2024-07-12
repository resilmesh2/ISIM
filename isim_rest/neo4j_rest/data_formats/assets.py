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

    def __post_init__(self):
        for p in self.parents:
            if not self.ip_range.subnet_of(p):
                raise ValueError(f"Declared {self.ip_range.compressed} is not subnet of {p.compressed}")


class HostDTO(msgspec.Struct):
    ip_address: IP_TYPE
    domain_names: list[str] = field(default_factory=list)
    subnets: list[IP_NET_TYPE] = field(default_factory=list)
    uris: list[str] = field(default_factory=list)
    tag: str | None = None

    def __post_init__(self):
        for s in self.subnets:
            if not self.ip_address not in s:
                raise ValueError(f"Declared {self.ip_address.compressed} is not in subnet {s.compressed}")


class SoftwareVersionDTO(msgspec.Struct):
    ip_addresses: list[IP_TYPE]
    version: str | None = None
    service: str | None = None
    protocol: str | None = None
    port: int | None = None
    tag: str | None = None

    def __post_init__(self):
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


class AssetListDTO(msgspec.Struct):
    hosts: list[HostDTO] = field(default_factory=list)
    subnets: list[SubnetDTO] = field(default_factory=list)
    software_versions: list[SoftwareVersionDTO] = field(default_factory=list)
    devices: list[DeviceDTO] = field(default_factory=list)
    applications: list[ApplicationDTO] = field(default_factory=list)
    org_units: list[OrgUnitDTO] = field(default_factory=list)
