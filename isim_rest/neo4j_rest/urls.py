from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path
from django.urls.resolvers import RoutePattern, URLPattern, URLResolver
from django.conf import settings
from django.conf.urls.static import static

from isim_rest.asset_management.urls import urlpatterns as asset_management_urls
from isim_rest.neo4j_rest import views

urlpatterns: list[RoutePattern | URLResolver | URLPattern] = []

urlpatterns += asset_management_urls

urlpatterns.append(
    path("", views.index, name="index"),
)

urlpatterns += staticfiles_urlpatterns()

if not settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

