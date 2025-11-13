from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    IPv6Address,
    IPv6Interface,
    IPv6Network,
    ip_interface,
    ip_network,
)
from ipaddress import _BaseAddress as IPInterface  # type: ignore
from ipaddress import _BaseNetwork as IPNetwork  # type: ignore
from typing import Any


def dec_hook_ip(type_: type[Any], obj: Any) -> Any:
    """
    This function processes IP types during decoding.
    :param type_: IP type from IPv4Network, IPv6Network, IPv4Address, IPv6Address, IPv4Interface, IPv6Interface,
    IPInterface, IPNetwork
    :param obj: object to be decoded
    :return: the decoded object
    """
    if type_ in {IPv4Network, IPv6Network, IPv4Address, IPv6Address, IPv4Interface, IPv6Interface}:
        return type_(obj)
    if type_ is IPInterface:
        return obj if isinstance(obj, IPv4Interface | IPv6Interface) else ip_interface(obj)
    if type_ is IPNetwork:
        return obj if isinstance(obj, IPv4Network | IPv6Network) else ip_network(obj)
    raise NotImplementedError(f"Objects of type {type_} are not supported")


def enc_hook_ip(obj: Any) -> Any:
    """
    This function processes IP types during encoding.
    :param obj: an object to be encoded
    :return: the encoded object
    """
    if isinstance(obj, IPv4Interface | IPv6Interface):
        return obj.ip.compressed
    if isinstance(obj, IPv4Address | IPv6Address):
        return obj.compressed
    if isinstance(obj, IPv4Network | IPv6Network):
        return obj.with_prefixlen
    # Raise a NotImplementedError for other types
    raise NotImplementedError(f"Objects of type {type(obj)} are not supported")
