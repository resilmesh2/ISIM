from __future__ import annotations

from typing import Any

from neomodel import (
    ArrayProperty,
    BooleanProperty,
    IntegerProperty,
    RelationshipFrom,
    RelationshipTo,
    StringProperty,
    StructuredNode,
    StructuredRel,
    UniqueIdProperty,
)


class TaggedRel(StructuredRel):
    tag = ArrayProperty(StringProperty(), default=list)


class IP(StructuredNode):
    uid = UniqueIdProperty()
    address = StringProperty(unique_index=True, required=True)
    version = IntegerProperty(required=False)
    tag = ArrayProperty(StringProperty(), default=list)

    part_of_subnet = RelationshipTo("Subnet", "PART_OF")
    identifies_uri = RelationshipTo("URI", "IDENTIFIES")
    resolves_to_domain = RelationshipTo("DomainName", "RESOLVES_TO")


class Host(StructuredNode):
    uid = UniqueIdProperty()

    is_a = RelationshipFrom("Node", "IS_A")
    has_identity_device = RelationshipTo("Device", "HAS_IDENTITY")


class Node(StructuredNode):
    uid = UniqueIdProperty()

    is_a_host = RelationshipTo("Host", "IS_A")
    has_assigned_ip = RelationshipTo("IP", "HAS_ASSIGNED")


class Subnet(StructuredNode):
    uid = UniqueIdProperty()
    range = StringProperty(unique_index=True, required=True)
    note = StringProperty(required=False)
    version = IntegerProperty(required=False)

    part_of_subnet = RelationshipTo("Subnet", "PART_OF")
    has_contact = RelationshipTo("Contact", "HAS")
    part_of_ou = RelationshipTo("OrganizationUnit", "PART_OF")


class URI(StructuredNode):
    uid = UniqueIdProperty()
    identifier = StringProperty(unique_index=True, required=True)


class DomainName(StructuredNode):
    uid = UniqueIdProperty()
    domain_name = StringProperty(unique_index=True, required=True)
    tag = ArrayProperty(StringProperty(), default=list)


class Contact(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)


class OrganizationUnit(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)

    part_of_ou = RelationshipTo("OrganizationUnit", "PART_OF")
    tenants_location = RelationshipTo("PhysicalEnvironment", "TENANTS")
    has_devices = RelationshipFrom("Device", "PART_OF")


class PhysicalEnvironment(StructuredNode):
    uid = UniqueIdProperty()
    location = StringProperty(unique_index=True, required=True)


class Device(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)
    power = StringProperty(required=False)
    state = StringProperty(required=False)

    part_of_ou = RelationshipTo("OrganizationUnit", "PART_OF")
    has_hardware = RelationshipTo("HardwareVersion", "HAS")


class HardwareVersion(StructuredNode):
    uid = UniqueIdProperty()
    manufacturer = StringProperty(required=True)
    model = StringProperty(required=True)


class Application(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)

    running_on = RelationshipTo("Device", "RUNNING_ON")


class SoftwareVersion(StructuredNode):
    uid = UniqueIdProperty()
    version = StringProperty(unique_index=True, required=True)
    tag = ArrayProperty(StringProperty(), default=list)

    provides_ns = RelationshipTo("NetworkService", "PROVIDES")
    on_host = RelationshipTo("Host", "ON", model=TaggedRel)


class NetworkService(StructuredNode):
    uid = UniqueIdProperty()
    port = IntegerProperty(required=True)
    protocol = StringProperty(required=True)
    service = StringProperty(required=True)
    tag = ArrayProperty(StringProperty(), default=list)

    on_host = RelationshipTo("Host", "ON", model=TaggedRel)
