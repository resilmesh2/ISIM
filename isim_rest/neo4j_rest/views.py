from django.http import HttpRequest, HttpResponse
from django.template import loader
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes  # type: ignore
from rest_framework.renderers import TemplateHTMLRenderer


@api_view(["GET"])
@renderer_classes([TemplateHTMLRenderer])
def index(_: HttpRequest) -> HttpResponse:
    template = loader.get_template("index.html")
    return HttpResponse(template.render(), status=status.HTTP_200_OK)
