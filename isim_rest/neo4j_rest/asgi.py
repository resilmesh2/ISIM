"""
ASGI config for neo4j_rest project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

from isim_common.observability import configure_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "neo4j_rest.settings")
configure_logging("isim-rest")

application = get_asgi_application()
