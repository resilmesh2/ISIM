import os

from neomodel import config as neomodel_config

from neo4j_adapter.models import Device, Host, Node

if __name__ == "__main__":
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "supertestovaciheslo")

    if neo4j_uri.startswith("bolt://"):
        neomodel_config.DATABASE_URL = (
            f"bolt://{neo4j_user}:{neo4j_password}@{neo4j_uri.removeprefix('bolt://')}"
        )
    else:
        neomodel_config.DATABASE_URL = f"bolt://{neo4j_user}:{neo4j_password}@{neo4j_uri}"

    host = Host().save()
    node = Node().save()
    device = Device(name="device-test").save()

    node.is_a_host.connect(host)
    host.has_identity_device.connect(device)

    _ = Host.nodes.get(uid=host.uid)
    device.name = "device-test-updated"
    device.save()
    node.delete()
