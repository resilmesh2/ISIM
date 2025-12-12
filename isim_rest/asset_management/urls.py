"""
URL configuration for neo4j_rest project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path, re_path

from . import views

urlpatterns = [
    path("missions", views.mission, name="missions"),
    path("assets", views.assets, name="assets"),
    path("asset_info", views.asset_info, name="asset_info"),
    path("ips", views.ip_assets, name="ips"),
    path("subnets", views.subnets, name="subnets"),
    path("devices", views.devices, name="devices"),
    path("org-units", views.org_units, name="org-units"),
    path("applications", views.applications, name="applications"),
    path("cves", views.cves, name="cves"),
    path("ip-hierarchy-sync", views.ip_hierarchy_sync, name="ip-hierarchy-sync"),
    re_path(r"^cve/(?P<cve_id>CVE-\d{4}-\d{4,7})$", views.cve, name="cve"),
    re_path(r"^ip/(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/cve", views.ip_cves, name="ip_cves"),
    # endpoints for temporal workflows from CASM
    path("easm", views.easm, name="easm"),
    path("traceroute", views.traceroute, name="traceroute"),
    path("nodes/betweenness_centrality", views.betweenness_centrality, name="betweenness_centrality"),
    path("nodes/degree_centrality", views.degree_centrality, name="degree_centrality"),
    path("nodes/store_criticality", views.store_criticality, name="store_criticality"),
    path("nodes/combine_criticality", views.combine_criticality, name="combine_criticality"),
    path("slp_enrichment", views.slp_enrichment, name="slp_enrichment"),
]
