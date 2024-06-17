import json
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from configparser import ConfigParser
from neo4j.exceptions import ClientError, DatabaseError, TransientError
from neo4j_adapter.RESTAdapter import RESTAdapter


def get_password():
    config_parser = ConfigParser()
    config_parser.read("isim_rest/neo4j_rest/conf.ini")
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
