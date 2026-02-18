from __future__ import annotations

from neomodel import (
    ArrayProperty,
    DateTimeProperty,
    FloatProperty,
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


class TimedRel(StructuredRel):
    start = DateTimeProperty(required=False)
    end = DateTimeProperty(required=False)


class TimedTaggedRel(StructuredRel):
    start = DateTimeProperty(required=False)
    end = DateTimeProperty(required=False)
    tag = ArrayProperty(StringProperty(), default=list)


class IP(StructuredNode):
    uid = UniqueIdProperty()
    address = StringProperty(unique_index=True, required=True)
    version = IntegerProperty(required=False)
    tag = ArrayProperty(StringProperty(), default=list)

    part_of_subnet = RelationshipTo("Subnet", "PART_OF")
    identifies_uri = RelationshipTo("URI", "IDENTIFIES")
    resolves_to_domain = RelationshipTo("DomainName", "RESOLVES_TO", model=TimedRel)


class Host(StructuredNode):
    uid = UniqueIdProperty()
    hostname = StringProperty(required=False)

    is_a = RelationshipFrom("Node", "IS_A")
    has_identity_device = RelationshipTo("Device", "HAS_IDENTITY")
    provided_by_component = RelationshipFrom("Component", "PROVIDED_BY")


class Node(StructuredNode):
    uid = UniqueIdProperty()
    degree_centrality = FloatProperty(required=False)
    pagerank_centrality = FloatProperty(required=False)
    topology_betweenness = FloatProperty(required=False)
    topology_degree = FloatProperty(required=False)

    is_a_host = RelationshipTo("Host", "IS_A")
    has_assigned_ip = RelationshipTo("IP", "HAS_ASSIGNED", model=TimedRel)


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
    for_mission = RelationshipFrom("Mission", "FOR")


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
    name = StringProperty(required=False)
    version = StringProperty(required=False)
    tag = ArrayProperty(StringProperty(), default=list)

    provides_ns = RelationshipTo("NetworkService", "PROVIDES")
    on_host = RelationshipTo("Host", "ON", model=TimedTaggedRel)


class NetworkService(StructuredNode):
    uid = UniqueIdProperty()
    port = IntegerProperty(required=True)
    protocol = StringProperty(required=True)
    service = StringProperty(required=True)
    tag = ArrayProperty(StringProperty(), default=list)

    on_host = RelationshipTo("Host", "ON", model=TimedTaggedRel)


class Mission(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)
    criticality = IntegerProperty(required=False)
    description = StringProperty(required=False)
    confidentiality_requirement = IntegerProperty(required=False)
    integrity_requirement = IntegerProperty(required=False)
    availability_requirement = IntegerProperty(required=False)
    structure = StringProperty(required=False)

    for_organization_unit = RelationshipTo("OrganizationUnit", "FOR")


class Component(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)

    provided_by = RelationshipTo("Host", "PROVIDED_BY")
    supports = RelationshipTo("Mission", "SUPPORTS")
    has_identity = RelationshipTo("Application", "HAS_IDENTITY")


class MissionDependency(StructuredNode):
    uid = UniqueIdProperty()

    to_component = RelationshipTo("Component", "TO")
    from_component = RelationshipTo("Component", "FROM")
