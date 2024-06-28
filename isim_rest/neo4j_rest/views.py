import json

import msgspec.json
from django.http import HttpRequest
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from configparser import ConfigParser
from neo4j.exceptions import ClientError, DatabaseError, TransientError

from isim_rest.neo4j_rest.data_formats.assets import AssetListDTO
from isim_rest.neo4j_rest.data_formats.serde_utils import dec_hook_ip, enc_hook_ip
from isim_rest.neo4j_rest.settings import BASE_DIR
from neo4j_adapter.RESTAdapter import RESTAdapter

def get_password():
    config_parser = ConfigParser()
    config_parser.read(BASE_DIR / "neo4j_rest/conf.ini")
    return config_parser['dashboard_rest']['neo4j_password']


client = RESTAdapter(password=get_password())
LIMIT = 100
OFFSET = 100


def get_limit(request):
    limit = request.GET.get('limit')
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = LIMIT
    return limit


# RED and BLUE LAYERS
@api_view(['GET', 'POST'])
def mission(request):
    """
    GET/POST information about missions view.
    :param request: GET/POST request
    :return: HTTP response
    """
    if request.method == 'GET':
        limit = get_limit(request)
        return Response(client.get_all_mission(limit))
    elif request.method == 'POST':
        properties = request.data
        try:
            data = json.dumps(properties)
            return Response(client.create_missions_and_components_string(data))
        except (ClientError, TransientError, DatabaseError) as e:
            return Response("Exception on neo4j side, set operation failed. " + str(e),
                            status=status.HTTP_400_BAD_REQUEST)
        except (KeyError, TypeError) as e:
            return Response("Structured data was not provided or are incorrect.", status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
def assets(request: HttpRequest) -> Response:
    if request.method == 'GET':
        return Response(client.get_assets(), status=status.HTTP_200_OK)
    else:
        request_body = request.body
        try:
            data = msgspec.json.decode(request_body, type=AssetListDTO, dec_hook=dec_hook_ip)
            json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
            client.store_assets(json_string)
        except Exception as e:
            return Response(f"ERROR {str(e)}", status=status.HTTP_500_INTERNAL_SERVER_ERROR )
        return Response("Alles gutte", status=status.HTTP_201_CREATED)
