import json

import msgspec
from django.apps.config import AppConfig
from neo4j.exceptions import ClientError

from isim_rest.asset_management.data_formats.assets import AssetListDTO
from isim_rest.asset_management.data_formats.serde_utils import dec_hook_ip, enc_hook_ip
from isim_rest.asset_management.utils import get_password
from neo4j_adapter.rest_adapter import RESTAdapter


class AssetManagementConfig(AppConfig):
    name = "neo4j_rest"

    def ready(self) -> None:
        initial_data = {
            "subnets": [
                {
                    "ip_range": "0.0.0.0/0",
                    "note": "Internet",
                },
                {"ip_range": "::/0", "note": "Internet"},
            ]
        }
        client = RESTAdapter(password=get_password())
        try:
            client.init_db()
        except ClientError as e:
            print(e) # todo replace with logging
        data = msgspec.convert(initial_data, type=AssetListDTO, dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
        client.store_assets(json_string)
