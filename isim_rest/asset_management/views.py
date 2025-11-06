"""
This module contains API views for individual URLs from the REST API.
They typically contain encoding and decoding of data, error handling and
response creation.
"""

import json

import msgspec.json
from django.http import HttpRequest
from msgspec import ValidationError
from neo4j.exceptions import ClientError, DatabaseError, TransientError
from neo4j_adapter.criticality_adapter import CriticalityAdapter
from neo4j_adapter.csa_adapter import CSAAdapter
from neo4j_adapter.ip_subnet_sync import IpSubnetSynchronizer
from neo4j_adapter.nmap_topology_adapter import NmapTopologyAdapter
from neo4j_adapter.rest_adapter import RESTAdapter
from neo4j_adapter.slp_enrichment_adapter import SLPEnrichmentAdapter
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
from isim_rest.asset_management.data_formats.serde_utils import dec_hook_ip, enc_hook_ip
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
        data = msgspec.json.decode(request_body, type=MissionListInputDTO, dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
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
        data = msgspec.json.decode(request_body, type=AssetListInputDTO, dec_hook=dec_hook_ip)
        data.flatten_related_relationships()
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
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
        data = msgspec.json.decode(request_body, type=list[EasmDTO], dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
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


@api_view(["GET"])
def applications(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_applications(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def cves(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_all_cve(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def cve(request: HttpRequest, cve_id: str) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_cve(cve_id=cve_id, limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def ip_cves(request: HttpRequest, ip: str) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_ip_cve(ip=ip, limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["POST"])
def traceroute(request: HttpRequest) -> Response:
    nmap_adapter = NmapTopologyAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)

    request_body = request.body
    try:
        data = msgspec.json.decode(request_body, type=NmapTopologyDTO)
        json_string = json.dumps(json.loads(msgspec.json.encode(data)))
        nmap_adapter.create_topology(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully.", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def betweenness_centrality(request: HttpRequest) -> Response:
    criticality_adapter = CriticalityAdapter(
        password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user
    )
    criticality_adapter.compute_topology_betweenness()
    return Response("Processed successfully.", status=status.HTTP_200_OK)


@api_view(["POST"])
def degree_centrality(request: HttpRequest) -> Response:
    criticality_adapter = CriticalityAdapter(
        password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user
    )
    criticality_adapter.compute_topology_degree()
    return Response("Processed successfully.", status=status.HTTP_200_OK)


@api_view(["POST"])
def store_criticality(request: HttpRequest) -> Response:
    csa_adapter = CSAAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
    request_body = request.body
    try:
        data = msgspec.json.decode(request_body, type=list[MissionCriticalityDTO], dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
        csa_adapter.store_criticality(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully.", status=status.HTTP_201_CREATED)


@api_view(["POST"])
def combine_criticality(request: HttpRequest) -> Response:
    csa_adapter = CSAAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
    csa_adapter.combine_criticality()
    return Response("Processed successfully.", status=status.HTTP_200_OK)


@api_view(["POST"])
def ip_hierarchy_sync(request: HttpRequest) -> Response:
    synchronizer = IpSubnetSynchronizer(
        user=config.neo4j.user,
        password=config.neo4j.password,
        bolt=config.neo4j.bolt,
    )
    synchronizer.run()
    return Response({"message": "Processed successfully"}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def slp_enrichment(request: HttpRequest) -> Response:
    slp_enrichment_adapter = SLPEnrichmentAdapter(
        password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user
    )
    request_body = request.body
    try:
        data = msgspec.json.decode(request_body, type=list[SLPEnrichmentDTO], dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
        slp_enrichment_adapter.store_slp_data(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, post operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully.", status=status.HTTP_201_CREATED)
