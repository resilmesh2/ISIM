from django.urls.resolvers import RoutePattern, URLPattern, URLResolver

from isim_rest.asset_management.urls import urlpatterns as asset_management_urls

urlpatterns: list[RoutePattern | URLResolver | URLPattern] = []

urlpatterns += asset_management_urls
