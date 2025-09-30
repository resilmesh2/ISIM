from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path
from django.urls.resolvers import RoutePattern, URLPattern, URLResolver

from isim_rest.asset_management.urls import urlpatterns as asset_management_urls
from isim_rest.neo4j_rest import views

urlpatterns: list[RoutePattern | URLResolver | URLPattern] = []

urlpatterns += asset_management_urls

urlpatterns.append(
    path("", views.index, name="index"),
)

urlpatterns += staticfiles_urlpatterns()
