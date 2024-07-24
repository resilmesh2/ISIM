import json

import msgspec.json
from django.http import HttpRequest
from msgspec._core import ValidationError
from neo4j.exceptions import ClientError, DatabaseError, TransientError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from isim_rest.asset_management.data_formats.assets import AssetListDTO
from isim_rest.asset_management.data_formats.serde_utils import dec_hook_ip, enc_hook_ip
from isim_rest.neo4j_rest.config import AppConfig
from neo4j_adapter.rest_adapter import RESTAdapter

DEFAULT_LIMIT = 50
DEFAULT_OFFSET = 0

config = AppConfig.get()
client = RESTAdapter(
    password=config.neo4j_config.password,
    bolt=config.neo4j_config.bolt,
    user=config.neo4j_config.user
)


def get_limit(request: HttpRequest) -> int:
    limit = request.GET.get("limit")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return limit


def get_offset(request: HttpRequest) -> int | None:
    offset = request.GET.get("offset", DEFAULT_OFFSET)
    try:
        offset = int(offset)
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
    if request.method == "GET":
        limit = get_limit(request)
        return Response(client.get_all_mission(limit))
    properties = request.data
    try:
        data = json.dumps(properties)
        return Response(client.create_missions_and_components_string(data))
    except (ClientError, TransientError, DatabaseError) as e:
        return Response("Exception on neo4j side, set operation failed. " + str(e), status=status.HTTP_400_BAD_REQUEST)
    except (KeyError, TypeError):
        return Response("Structured data was not provided or are incorrect.", status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def assets(request: HttpRequest) -> Response:
    request_body = request.body
    try:
        data = msgspec.json.decode(request_body, type=AssetListDTO, dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
        client.store_assets(json_string)
    except ValidationError as e:
        return Response(f"Bad input: {e!s}", status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except (ClientError, TransientError, DatabaseError) as e:
        return Response(
            "Exception on neo4j side, set operation failed. " + str(e), status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response("Processed successfully", status=status.HTTP_201_CREATED)


@api_view(["GET"])
def ip_assets(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_offset(request)
    return Response(client.get_ip_assets(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def subnets(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_limit(request)
    return Response(client.get_subnets(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def devices(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_limit(request)
    return Response(client.get_devices(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def org_units(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_limit(request)
    return Response(client.get_organization_units(limit=limit, offset=offset), status=status.HTTP_200_OK)


@api_view(["GET"])
def applications(request: HttpRequest) -> Response:
    limit = get_limit(request)
    offset = get_limit(request)
    return Response(client.get_applications(limit=limit, offset=offset), status=status.HTTP_200_OK)
