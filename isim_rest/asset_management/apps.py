import json

import msgspec
from django.apps.config import AppConfig
from neo4j.exceptions import ClientError
from neo4j_adapter.rest_adapter import RESTAdapter
from structlog import getLogger

from isim_rest.asset_management.data_formats.input_dtos import AssetListInputDTO
from isim_rest.asset_management.data_formats.serde_utils import dec_hook_ip, enc_hook_ip
from isim_rest.neo4j_rest.config import AppConfig as ISIMConfig

logger = getLogger()


class AssetManagementConfig(AppConfig):
    name = "neo4j_rest"

    def ready(self) -> None:
        config = ISIMConfig.get()

        initial_data = {
            "subnets": [
                {
                    "ip_range": "0.0.0.0/0",
                    "note": "Internet",
                },
                {"ip_range": "::/0", "note": "Internet"},
            ],
            "hosts": [],
        }

        for host in config.organization.hosts:
            initial_data["hosts"].append(
                {
                    "ip_address": host.ip_address,
                    "domain_names": host.domain_names,
                    "subnets": host.subnets,
                    "tag": ["config"],
                    "version": host.version,
                }
            )

        client = RESTAdapter(password=config.neo4j.password, bolt=config.neo4j.bolt, user=config.neo4j.user)
        try:
            client.init_db()
        except ClientError as e:
            if e.message and "An equivalent constraint already exists" not in e.message:
                logger.exception(e)
        data = msgspec.convert(initial_data, type=AssetListInputDTO, dec_hook=dec_hook_ip)
        json_string = json.dumps(json.loads(msgspec.json.encode(data, enc_hook=enc_hook_ip)))
        client.store_assets(json_string)
