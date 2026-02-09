"""
This module contains API views for individual URLs from the REST API.
They typically contain encoding and decoding of data, error handling and
response creation.
"""

import json

from django.http import HttpRequest
from neo4j.exceptions import ClientError, DatabaseError, TransientError
from neo4j_adapter.criticality_adapter import CriticalityAdapter
from neo4j_adapter.csa_adapter import CSAAdapter
from neo4j_adapter.ip_subnet_sync import IpSubnetSynchronizer
from neo4j_adapter.nmap_topology_adapter import NmapTopologyAdapter
from neo4j_adapter.rest_adapter import RESTAdapter
from neo4j_adapter.slp_enrichment_adapter import SLPEnrichmentAdapter
from pydantic import TypeAdapter, ValidationError
from rest_framework import status
from rest_framework.decorators import api_view  # type: ignore
from rest_framework.response import Response

from isim_rest.asset_management.data_formats.input_dtos import (
    AssetListInputDTO,
    EasmDTO,
    MissionCriticalityDTO,
    MissionListInputDTO,
    NmapTopologyDTO,
    SLPEnrichmentDTO,
)
from isim_rest.neo4j_rest.config import AppConfig

DEFAULT_LIMIT = 50
DEFAULT_OFFSET = 0

config = AppConfig.get()
client = RESTAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)


def get_limit(request: HttpRequest) -> int:
    limit_param = request.GET.get("limit", DEFAULT_LIMIT)
    try:
        limit = int(limit_param)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return limit


def get_offset(request: HttpRequest) -> int:
    offset_param = request.GET.get("offset", DEFAULT_OFFSET)
    try:
        offset = int(offset_param)
    except (TypeError, ValueError):
        offset = DEFAULT_OFFSET
    return offset


# RED and BLUE LAYERS
@api_view(["GET", "POST"])
def mission(request: HttpRequest) -> Response:
    """
    GET/POST information about missions view.
    :param request: GET/POST request
    :return: HTTP response
    """
    if request.method == "GET":  # type: ignore
        limit = get_limit(request)
        return Response(client.get_all_mission(limit))
    request_body = request.body
    try:
        data = MissionListInputDTO.model_validate_json(request_body)
        json_string = json.dumps(data.model_dump(mode="json", by_alias=True, exclude_none=True))
        client.create_missions_and_components_string(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, set operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def assets(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        data = AssetListInputDTO.model_validate_json(request_body)
        data.flatten_related_relationships()
        json_string = json.dumps(data.model_dump(mode="json", by_alias=True, exclude_none=True))
        client.store_assets(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, set operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response(
        "Processed successfully. If some assets support missions, use /missions endpoint to add descriptions of missions.",
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def easm(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        adapter = TypeAdapter(list[EasmDTO])
        data = adapter.validate_json(request_body)
        json_string = json.dumps(adapter.dump_python(data, mode="json", by_alias=True, exclude_none=True))
        client.store_easm(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, set operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response(
        "Processed successfully. If some assets support missions, use /missions endpoint to add descriptions of missions.",
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def asset_info(request: HttpRequest) -> Response:
    ip: str | None = request.GET.get("ip", None)
    limit = get_limit(request)
    offset = get_offset(request)
    asset_infos = client.get_ip_asset_info(limit=limit, offset=offset, ip=ip)
    asset_information = [asset_info.serialize() for asset_info in asset_infos]
    return Response(asset_information, status=status.HTTP_200_OK)


@api_view(["GET"])
def ip_assets(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_ip_assets(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def subnets(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_subnets(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def devices(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_devices(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def org_units(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_organization_units(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["POST"])
def nmap_topology(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        data = NmapTopologyDTO.model_validate_json(request_body)
        json_string = json.dumps(data.model_dump(mode="json", by_alias=True, exclude_none=True))
        nmap_adapter = NmapTopologyAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
        nmap_adapter.create_topology(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def criticality(request: HttpRequest) -> Response:
    data = request.body
    criticality_adapter = CriticalityAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
    try:
        criticality_adapter.apply_ip_criticality_data(data)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def csa(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        adapter = TypeAdapter(list[MissionCriticalityDTO])
        data = adapter.validate_json(request_body)
        json_string = json.dumps(adapter.dump_python(data, mode="json", by_alias=True, exclude_none=True))
        csa_adapter = CSAAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
        csa_adapter.create_mission_criticality(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def ip_subnet_sync(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        adapter = TypeAdapter(list[MissionCriticalityDTO])
        data = adapter.validate_json(request_body)
        json_string = json.dumps(adapter.dump_python(data, mode="json", by_alias=True, exclude_none=True))
        syncer = IpSubnetSynchronizer(
            user=config.neo4j.user,
            password=config.neo4j.password,
            bolt=config.neo4j.bolt,
        )
        syncer.sync_ip_subnet_relation(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def slp_enrichment(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        adapter = TypeAdapter(list[SLPEnrichmentDTO])
        data = adapter.validate_json(request_body)
        json_string = json.dumps(adapter.dump_python(data, mode="json", by_alias=True, exclude_none=True))
        slp_adapter = SLPEnrichmentAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
        slp_adapter.enrich(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)
