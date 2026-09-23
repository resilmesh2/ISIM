""" This module implements conversion of mission representation to CycloneDX format. """
from typing import Any, Tuple
from uuid import uuid4
import json
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType, ComponentScope
from cyclonedx.model.service import Service
from cyclonedx.output import make_outputter, BaseOutput, OutputFormat, SchemaVersion
from cyclonedx.model import Property
from cyclonedx.validation.json import JsonValidator


def create_cyclonedx_json(mission_representation: dict[str, Any]) -> dict[str, Any]:
    """
    The main function for conversion of mission representation to CycloneDX format.
    :param mission_representation: dictionary representing the mission representation
    :return: cyclonedx json
    """
    missions = []
    dependencies = []
    services_objects = []
    components_objects = []

    mission_bom = Bom()
    formulation = []

    process_mission_layer(mission_representation, missions, services_objects)
    process_services_layer(mission_representation, services_objects, components_objects, dependencies)

    for component in mission_representation["nodes"]["hosts"]:
        component_dict = component
        component_object = find_object_with_properties(component_dict, components_objects)
        if not component_object:
            component_dict["bom-ref"] = "component-" + str(uuid4())
            components_objects.append(Component(name=component_dict["hostname"], bom_ref=component_dict["bom-ref"],
                                                type=ComponentType.DEVICE,
                                                properties=[Property(name="ip", value=component_dict["ip"])],
                                                scope=ComponentScope.REQUIRED))
        else:
            component_dict["bom-ref"] = component_object.bom_ref.value

    for component in components_objects:
        mission_bom.components.add(component)

    for service_object in services_objects:
        mission_bom.services.add(service_object)

    # literal dependencies in JSON
    find_and_register_dependencies(mission_representation, mission_bom)

    # derived dependencies from AND/OR tree
    for dependency in dependencies:
        mission_bom.register_dependency(dependency[0], dependency[1])
    convert_missions_into_formulation(missions, formulation)

    outputter: BaseOutput = make_outputter(bom=mission_bom, output_format=OutputFormat.JSON,
                                           schema_version=SchemaVersion.V1_7)
    bom_json: str = outputter.output_as_string()

    bom_json = json.loads(bom_json)
    bom_json["formulation"] = formulation

    json_validation = JsonValidator(schema_version=SchemaVersion.V1_7)
    json_validation.validate_str(json.dumps(bom_json))
    return bom_json


def process_mission_layer(json_data: dict[str, Any], missions: list[dict[str, Any]],
                          services_objects: list[Service]) -> None:
    """
    This procedure processes mission layer from mission representation
    :param json_data: mission representation in json
    :param missions: list of missions
    :param services_objects: list of objects representing services
    :return: None
    """
    for mission in json_data["nodes"]["missions"]:
        mission_dict = mission
        mission_dict["bom-ref"] = "mission-" + str(uuid4())
        mission_dict["services"] = []

        for one_way_relationship in json_data["relationships"]["one_way"]:
            and_ids = []
            or_ids = []
            service_ids = []
            if one_way_relationship["from"] == mission_dict["id"]:
                if one_way_relationship["to"] in json_data["nodes"]["aggregations"]["and"]:
                    and_ids.append(one_way_relationship["to"])
                elif one_way_relationship["to"] in json_data["nodes"]["aggregations"]["or"]:
                    or_ids.append(one_way_relationship["to"])
                elif one_way_relationship["to"] in [service["id"] for service in json_data["nodes"]["services"]]:
                    service_ids.append(one_way_relationship["to"])
            process_mission_and_nodes(json_data, and_ids, or_ids, service_ids)
            process_mission_or_nodes(json_data, mission_dict, or_ids, services_objects)
            for service_id in service_ids:
                service_dict = [service for service in json_data["nodes"]["services"] if service["id"] == service_id][0]
                service_dict["properties"] = [{"name": "scope", "value": ComponentScope.REQUIRED}]
                service_object = find_object_with_properties(service_dict, services_objects)
                if not service_object:
                    services_objects.append(Service(name=service_dict["name"], bom_ref="service-" + str(uuid4()),
                                                    services=[Service(name=inner_service["name"],
                                                                      bom_ref=inner_service["bom-ref"]) for
                                                              inner_service in service_dict[
                                                                  "services"]] if "services" in service_dict else None,
                                                    properties=[Property(name="scope", value=ComponentScope.REQUIRED)]))
                if service_dict not in mission_dict["services"]:
                    mission_dict["services"].append(service_dict)
        missions.append(mission_dict)


def process_mission_and_nodes(json_data: dict[str, Any], and_ids: list[int], or_ids: list[int],
                              service_ids: list[int]) -> None:
    """
    This procedure processes AND nodes from the mission layer of mission representation
    :param json_data: mission representation in JSON
    :param and_ids: IDs of AND nodes
    :param or_ids: IDs of OR nodes
    :param service_ids: IDs of services
    :return: None
    """
    for and_id in and_ids:
        for inner_relationship in json_data["relationships"]["one_way"]:
            if inner_relationship["from"] == and_id:
                if inner_relationship["to"] in json_data["nodes"]["aggregations"]["and"]:
                    and_ids.append(inner_relationship["to"])
                elif inner_relationship["to"] in json_data["nodes"]["aggregations"]["or"]:
                    or_ids.append(inner_relationship["to"])
                elif inner_relationship["to"] in [service["id"] for service in json_data["nodes"]["services"]]:
                    service_ids.append(inner_relationship["to"])


def process_mission_or_nodes(json_data: dict[str, Any], mission_dict: dict[str, Any],
                             or_ids: list[int], services_objects: list[Service]) -> None:
    """
    This procedure processes OR nodes from the mission layer of mission representation
    :param json_data: mission representation in JSON
    :param mission_dict: dictionary representing a mission
    :param or_ids: IDs of OR nodes
    :param services_objects: objects representing services
    :return: None
    """
    for or_id in or_ids:
        service_dict = {"name": "Joint entity - OR", "bom-ref": "service" + str(uuid4()),
                        "properties": [{"name": "scope", "value": ComponentScope.REQUIRED}]}
        service_dict["services"] = []
        for inner_relationship in json_data["relationships"]["one_way"]:
            if (inner_relationship["from"] == or_id and
                    inner_relationship["to"] in [service["id"] for service in json_data["nodes"]["services"]]):
                inner_service_dict = [service for service in json_data["nodes"][
                    "services"] if service["id"] == inner_relationship["to"]][0]
                service_object = find_object_with_properties(inner_service_dict, services_objects)
                if not service_object:
                    inner_service_dict["bom-ref"] = "service-" + str(uuid4())
                    services_objects.append(Service(name=inner_service_dict["name"],
                                                    bom_ref=inner_service_dict["bom-ref"],
                                                    properties=[
                                                        Property(name="scope",
                                                                 value=ComponentScope.OPTIONAL)]))
                else:
                    inner_service_dict["bom-ref"] = service_object.bom_ref.value
                service_dict["services"].append({"name": inner_service_dict["name"],
                                                 "bom-ref": inner_service_dict["bom-ref"],
                                                 "properties": [{"name": "scope", "value": ComponentScope.OPTIONAL}]})
        if service_dict not in mission_dict["services"]:
            mission_dict["services"].append(service_dict)


def process_services_layer(json_data: dict[str, Any], services_objects: list[Service],
                           components_objects: list[Component],
                           dependencies: list[Tuple[Service | Component, list[Service | Component]]]) -> None:
    """
    This procedure processes the service layer of mission representation
    :param json_data: dictionary representing a mission representation
    :param services_objects: objects representing services
    :param components_objects: objects representing components
    :param dependencies: dependencies inferred from AND / OR tree
    :return: None
    """
    for service in json_data["nodes"]["services"]:
        service_dict = service
        service_object = find_object_with_properties(service_dict, services_objects)
        if not service_object:
            service_dict["bom-ref"] = "service-" + str(uuid4())
            service_object = Service(name=service_dict["name"], bom_ref=service_dict["bom-ref"],
                                     properties=[Property(name="scope", value=ComponentScope.REQUIRED)])
            services_objects.append(service_object)
        else:
            service_dict["bom-ref"] = service_object.bom_ref.value

        for one_way_relationship in json_data["relationships"]["one_way"]:
            and_ids = []
            or_ids = []
            component_ids = []
            if one_way_relationship["from"] == service_dict["id"]:
                if one_way_relationship["to"] in json_data["nodes"]["aggregations"]["and"]:
                    and_ids.append(one_way_relationship["to"])
                elif one_way_relationship["to"] in json_data["nodes"]["aggregations"]["or"]:
                    or_ids.append(one_way_relationship["to"])
                elif one_way_relationship["to"] in [component["id"] for component in json_data["nodes"]["hosts"]]:
                    component_ids.append(one_way_relationship["to"])
            process_service_and_nodes(json_data, and_ids, or_ids, component_ids)
            for or_id in or_ids:
                current_service_object = create_service_or_node(service_dict, services_objects)
                process_service_or_inner_relationships(json_data, current_service_object, or_id, components_objects,
                                                       dependencies)
            for component_id in component_ids:
                inner_component_dict = [component for component in json_data[
                    "nodes"]["hosts"] if component["id"] == component_id][0]
                component_object = find_object_with_properties(inner_component_dict, components_objects)
                if not component_object:
                    component_object = Component(
                        name=inner_component_dict["hostname"], bom_ref="component-" + str(uuid4()),
                        type=ComponentType.DEVICE, scope=ComponentScope.REQUIRED,
                        properties=[Property(name="ip", value=inner_component_dict["ip"])])
                    components_objects.append(component_object)
                if (service_object, [component_object]) not in dependencies:
                    dependencies.append((service_object, [component_object]))


def process_service_and_nodes(json_data: dict[str, Any], and_ids: list[int], or_ids: list[int],
                              component_ids: list[int]) -> None:
    """
    This procedure processes AND nodes from the service layer of mission representation
    :param json_data: dictionary representing a mission representation
    :param and_ids: IDs of AND nodes
    :param or_ids: IDs of OR nodes
    :param component_ids: IDs of components
    :return: None
    """
    for and_id in and_ids:
        for inner_relationship in json_data["relationships"]["one_way"]:
            if inner_relationship["from"] == and_id:
                if inner_relationship["to"] in json_data["nodes"]["aggregations"]["or"]:
                    or_ids.append(inner_relationship["to"])
                elif inner_relationship["to"] in [component["id"] for component in json_data["nodes"]["hosts"]]:
                    component_ids.append(inner_relationship["to"])


def create_service_or_node(service_dict: dict[str, Any], services_objects: list[Service]) -> Service:
    """
    This procedure creates a service object for OR node from the service layer
    :param service_dict: dictionary representing a parent service
    :param services_objects: objects representing services
    :return: OR service object
    """
    inner_service_dict = {"name": "Joint entity - OR", "bom-ref": "service-" + str(uuid4()),
                          "properties": [{"name": "scope", "value": ComponentScope.REQUIRED}]}
    service_dict["services"] = []
    service_dict["services"].append(inner_service_dict)
    current_service_object = Service(name=inner_service_dict["name"], bom_ref=inner_service_dict["bom-ref"],
                                    properties=[Property(name="scope", value=ComponentScope.REQUIRED)])
    services_objects.append(current_service_object)

    return current_service_object


def process_service_or_inner_relationships(json_data: dict[str, Any], current_service_object: Service,
                                           current_or_id: int, components_objects: list[Component],
                                           dependencies: list[Tuple[
                                               Service | Component, list[Service | Component]]]) -> None:
    """
    This procedure processes inner relationship for OR nodes from the service layer of mission representation
    :param json_data: dictionary representing a mission representation
    :param current_service_object: service object
    :param current_or_id: ID of OR node
    :param components_objects: objects representing components
    :param dependencies: list of dependencies
    :return: None
    """
    for inner_relationship in json_data["relationships"]["one_way"]:
        if (inner_relationship["from"] == current_or_id and
                inner_relationship["to"] in [component["id"] for component in json_data["nodes"]["hosts"]]):
            inner_component_dict = [component for component in json_data[
                "nodes"]["hosts"] if component["id"] == inner_relationship["to"]][0]
            component_object = find_object_with_properties(inner_component_dict, components_objects)
            if not component_object:
                inner_component_dict["bom-ref"] = "component-" + str(uuid4())
                inner_component_dict["scope"] = ComponentScope.OPTIONAL
                components_objects.append(
                    Component(name=inner_component_dict["hostname"], type=ComponentType.DEVICE,
                              bom_ref=inner_component_dict["bom-ref"],
                              scope=ComponentScope.OPTIONAL,
                              properties=[Property(name="ip", value=inner_component_dict["ip"])]))
            else:
                inner_component_dict["bom-ref"] = component_object.bom_ref.value
            dependencies.append((current_service_object,
                                 [tmp_component for tmp_component in components_objects if str(
                                     tmp_component.bom_ref) == inner_component_dict["bom-ref"]]))


def find_and_register_dependencies(json_data: dict[str, Any], mission_bom: Bom) -> None:
    """
    This procedure finds objects listed in dependencies in mission representation
    and registers them as dependencies
    :param json_data: dictionary representing a mission representation
    :param mission_bom: bill of materials for a mission
    :return: None
    """
    for dependency in json_data["relationships"]["dependencies"]:
        from_entity = find_json_entity_with_id(dependency["from"], json_data["nodes"]["services"])
        if from_entity:
            from_object = find_object_with_properties(from_entity, mission_bom.services)
        else:
            from_entity = find_json_entity_with_id(dependency["from"], json_data["nodes"]["hosts"])
            from_object = find_object_with_properties(from_entity, mission_bom.components)
        to_entity = find_json_entity_with_id(dependency["to"], json_data["nodes"]["services"])
        if to_entity:
            to_object = find_object_with_properties(to_entity, mission_bom.services)
        else:
            to_entity = find_json_entity_with_id(dependency["to"], json_data["nodes"]["hosts"])
            to_object = find_object_with_properties(to_entity, mission_bom.components)
        mission_bom.register_dependency(from_object, [to_object])


def convert_missions_into_formulation(missions: list[dict[str, Any]], formulation: list[dict[str, Any]]) -> None:
    """
    This procedure converts mission representation to formulation representation in BOM
    :param missions: list of missions
    :param formulation: dictionary containing Bill of Materials formulation
    :return: None
    """
    for mission in missions:
        mission_dict_tmp = {"bom-ref": mission["bom-ref"]}
        mission_dict_tmp["properties"] = []
        for key in mission:
            if key not in ["id", "bom-ref", "services"] and mission[key]:
                mission_dict_tmp["properties"].append(
                    {"name": key,
                     "value": str(mission[key]) if key in [
                         "criticality", "confidentiality_requirement", "integrity_requirement",
                         "availability_requirement"] else mission[key]})
            if key == "services" and mission[key]:
                for tmp_component in mission[key]:
                    tmp_component.pop("id", None)
                mission_dict_tmp["services"] = mission[key]
        formulation.append(mission_dict_tmp)


def get_successors(entity_id: int, relationships_list: list[dict[str, Any]]) -> list[int]:
    """
    This procedure gets successors of entity from relationships list
    :param entity_id: ID of entity
    :param relationships_list: list of relationships
    :return: list of successor IDs
    """
    successors_ids = []
    for relationship in relationships_list:
        if relationship["from"] == entity_id:
            successors_ids.append(relationship["to"])
    return successors_ids


def create_service(service_id: int, scope: ComponentScope, service_list: list[dict[str, Any]]) -> Service | None:
    """
    This procedure creates a service found in a service list or returns None if service not found
    :param service_id: ID of service
    :param scope: scope of service - required or optional
    :param service_list: list of services
    :return: Service object or None
    """
    found_service = None
    for service_item in service_list:
        if service_item["id"] == service_id:
            found_service = Service(name=service_item["name"], bom_ref="service" + str(uuid4()),
                                    properties=[Property(name="scope", value=scope)])
    return found_service


def find_json_entity_with_id(entity_id: int, entities_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    This procedure finds entity with id from entities_list or returns None if entity not found
    :param entity_id: ID of entity
    :param entities_list: list of entities
    :return: ID of entity or None
    """
    for entity in entities_list:
        if entity["id"] == entity_id:
            return entity
    return None


def find_object_with_properties(entity: dict[str, Any],
                                objects_list: list[Service | Component]) -> Service | Component | None:
    """
    This procedure finds entity with properties from the objects list or returns None if entity not found
    :param entity: entity to be processed
    :param objects_list: list of objects
    :return: Service, Component, or None
    """
    for current_object in objects_list:
        if isinstance(current_object, Service):
            if current_object.name == entity["name"]:
                return current_object
        elif isinstance(current_object, Component):
            if (current_object.name == entity["hostname"] and
                    find_value_among_properties("ip", current_object.properties) == entity["ip"]):
                return current_object
    return None


def find_value_among_properties(property_name: str, property_list: list[Property]) -> str | None:
    """
    This procedure finds property value among properties from property list
    :param property_name: name of property
    :param property_list: list of properties expressed by keys and values
    :return: value of property or None
    """
    for current_property in property_list:
        if current_property.name == property_name:
            return current_property.value
    return None
