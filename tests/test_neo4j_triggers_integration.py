from collections.abc import Generator
from typing import Any

import pytest
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from config import AppConfig

TEST_ID_PREFIX = "it-trigger-"


@pytest.fixture(scope="module")
def neo4j_driver() -> Generator[Driver]:
    neo4j_config = AppConfig.get().neo4j

    driver = GraphDatabase.driver(neo4j_config.bolt, auth=(neo4j_config.user, neo4j_config.password))

    try:
        driver.verify_connectivity()
    except ServiceUnavailable as exc:
        driver.close()
        pytest.fail(f"Neo4j is not reachable at {neo4j_config.bolt}: {exc}")

    yield driver
    driver.close()


@pytest.fixture(autouse=True)
def cleanup_data(neo4j_driver: Driver) -> Generator[None]:
    with neo4j_driver.session(database="neo4j") as session:
        session.run(
            "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
            prefix=TEST_ID_PREFIX,
        ).consume()

    yield

    with neo4j_driver.session(database="neo4j") as session:
        session.run(
            "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
            prefix=TEST_ID_PREFIX,
        ).consume()


@pytest.fixture(scope="module", autouse=True)
def reload_triggers(neo4j_driver: Driver) -> None:
    trigger_names = [
        "setInRelationshipEndOnClose",
        "setInRelationshipStartOnCreate",
        "updateSoftwareVersionCveTimestampOnVulnStatusChange",
    ]
    with neo4j_driver.session(database="neo4j") as session:
        existing = {
            row["name"]
            for row in session.run(
                "CALL apoc.trigger.list() YIELD name RETURN name",
            )
        }
        for trigger_name in trigger_names:
            if trigger_name in existing:
                session.run("CALL apoc.trigger.remove($name)", name=trigger_name).consume()
        session.run(
            "CALL apoc.cypher.runFile('file:///triggers.cypher',{reportError:true,statistics:true})",
        ).consume()


def _single_record_value(driver: Driver, query: str, value_key: str, **params: Any) -> Any:
    with driver.session(database="neo4j") as session:
        record = session.run(query, **params).single()
    assert record is not None
    return record[value_key]


def test_triggers_are_installed_and_active(neo4j_driver: Driver) -> None:
    with neo4j_driver.session(database="neo4j") as session:
        rows = list(
            session.run(
                "CALL apoc.trigger.list() YIELD name, paused RETURN name, paused ORDER BY name",
            )
        )

    trigger_map = {row["name"]: row["paused"] for row in rows}
    expected = {
        "setInRelationshipEndOnClose",
        "setInRelationshipStartOnCreate",
        "updateSoftwareVersionCveTimestampOnVulnStatusChange",
    }

    assert expected.issubset(set(trigger_map))
    assert trigger_map["setInRelationshipEndOnClose"] is False
    assert trigger_map["setInRelationshipStartOnCreate"] is False
    assert trigger_map["updateSoftwareVersionCveTimestampOnVulnStatusChange"] is False


def test_in_relationship_gets_start_timestamp_when_created(neo4j_driver: Driver) -> None:
    vulnerability_id = f"{TEST_ID_PREFIX}v-start"
    software_version_id = f"{TEST_ID_PREFIX}s-start"

    with neo4j_driver.session(database="neo4j") as session:
        session.run(
            """
            CREATE (v:Vulnerability {id: $vulnerability_id, status: 'open'})
            CREATE (s:SoftwareVersion {id: $software_version_id})
            CREATE (v)-[:IN]->(s)
            """,
            vulnerability_id=vulnerability_id,
            software_version_id=software_version_id,
        ).consume()

    start_value = _single_record_value(
        neo4j_driver,
        """
        MATCH (:Vulnerability {id: $vulnerability_id})-[r:IN]->(:SoftwareVersion {id: $software_version_id})
        RETURN r.start AS start_value
        """,
        "start_value",
        vulnerability_id=vulnerability_id,
        software_version_id=software_version_id,
    )

    assert start_value is not None


@pytest.mark.parametrize("new_status", ["closed", ["closed"]])
def test_status_change_sets_end_and_cve_timestamp(neo4j_driver: Driver, new_status: str | list[str]) -> None:
    vulnerability_id = f"{TEST_ID_PREFIX}v-close"
    software_version_id = f"{TEST_ID_PREFIX}s-close"

    with neo4j_driver.session(database="neo4j") as session:
        session.run(
            """
            CREATE (v:Vulnerability {id: $vulnerability_id, status: 'open'})
            CREATE (s:SoftwareVersion {id: $software_version_id, cve_timestamp: null})
            CREATE (v)-[:IN]->(s)
            """,
            vulnerability_id=vulnerability_id,
            software_version_id=software_version_id,
        ).consume()

        session.run(
            "MATCH (v:Vulnerability {id: $vulnerability_id}) SET v.status = $new_status",
            vulnerability_id=vulnerability_id,
            new_status=new_status,
        ).consume()

    result = _single_record_value(
        neo4j_driver,
        """
        MATCH (:Vulnerability {id: $vulnerability_id})-[r:IN]->(s:SoftwareVersion {id: $software_version_id})
        RETURN {end: r.end, cve_timestamp: s.cve_timestamp} AS trigger_values
        """,
        "trigger_values",
        vulnerability_id=vulnerability_id,
        software_version_id=software_version_id,
    )

    assert result["end"] is not None
    assert result["cve_timestamp"] is not None
