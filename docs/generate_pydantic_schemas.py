from __future__ import annotations

import json
from pathlib import Path

from isim_rest.asset_management.data_formats import pydantic_dtos as dtos

OUTPUT_PATH = Path(__file__).with_name("pydantic_schemas.json")

MODELS = [
    dtos.HostDTO,
    dtos.SubnetDTO,
    dtos.SoftwareVersionDTO,
    dtos.DeviceDTO,
    dtos.ApplicationDTO,
    dtos.OrgUnitDTO,
    dtos.EasmDTO,
    dtos.AssetListInputDTO,
    dtos.MissionDTO,
    dtos.ServiceDTO,
    dtos.AggregationsDTO,
    dtos.HostMissionDTO,
    dtos.NodeMissionDTO,
    dtos.RelationshipDTO,
    dtos.MissionListInputDTO,
    dtos.NmapTopologyDTO,
    dtos.MissionCriticalityDTO,
    dtos.SLPEnrichmentDTO,
    dtos.MissionPostDTO,
    dtos.AssetsPostDTO,
    dtos.EasmPostDTO,
    dtos.TraceroutePostDTO,
    dtos.StoreCriticalityPostDTO,
    dtos.SlpEnrichmentPostDTO,
    dtos.PlainTextResponseDTO,
    dtos.MessageResponseDTO,
    dtos.MissionInfoDTO,
    dtos.MissionInfoResponseDTO,
    dtos.NodeCentralityDTO,
    dtos.IPAssetInformationDTO,
    dtos.AssetInfoResponseDTO,
    dtos.OrganizationUnitsResponseDTO,
    dtos.SubnetsResponseDTO,
    dtos.IpAssetsResponseDTO,
    dtos.DevicesResponseDTO,
    dtos.ApplicationsResponseDTO,
    dtos.CveSummaryDTO,
    dtos.CveSummaryResponseDTO,
    dtos.CveNodeResponseDTO,
]


def build_components() -> dict[str, object]:
    schemas: dict[str, object] = {}
    definitions: dict[str, object] = {}
    for model in MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        defs = schema.pop("$defs", {})
        definitions.update(defs)
        schemas[model.__name__] = schema

    return {"components": {"schemas": {**definitions, **schemas}}}


def main() -> None:
    payload = build_components()
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
