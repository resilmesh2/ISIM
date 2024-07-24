#!/usr/bin/python3.12
from typing import Any

from neo4j import GraphDatabase, basic_auth


class GeneralAdapter:
    def __init__(
        self,
        bolt: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str | None = None,
        driver: str | None = None,
        lifetime: int = 200,
        encrypted: bool = False,
    ) -> None:
        self._user = user
        if driver is None:
            self._driver = GraphDatabase.driver(
                bolt, auth=basic_auth(user, password), max_connection_lifetime=lifetime, encrypted=encrypted
            )
        else:
            self._driver = driver

    def _run_query(self, query: str, **kwargs: Any) -> list[Any]:
        records, _, _ = self._driver.execute_query(query, **kwargs)
        return records

    def _get_driver(self) -> None:
        return self._driver

    def _close(self) -> None:
        self._driver.close()

    def init_db(self) -> None:
        """
        Create initial constraints
        """
        constraints = [
            "CREATE CONSTRAINT FOR (n:Contact) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT FOR (n:DetectionSystem) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT FOR (p:IP) REQUIRE p.address IS UNIQUE",
            "CREATE CONSTRAINT FOR (o:OrganizationUnit) REQUIRE o.name IS UNIQUE",
            "CREATE CONSTRAINT FOR (n:Subnet) REQUIRE n.range IS UNIQUE",
            "CREATE CONSTRAINT FOR (c:CVE) REQUIRE c.CVE_id IS UNIQUE",
            "CREATE CONSTRAINT FOR (v:Vulnerability) REQUIRE v.description IS UNIQUE",
            "CREATE CONSTRAINT FOR (n:Mission) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT FOR (n:Component) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT FOR (n:DomainName) REQUIRE (n.domain_name, n.tag) IS UNIQUE",
            "CREATE CONSTRAINT FOR (s:NetworkService) REQUIRE (s.service, s.tag) IS UNIQUE",
            "CREATE CONSTRAINT FOR (s:SoftwareVersion) REQUIRE (s.version, s.tag) IS UNIQUE",
        ]

        for constraint in constraints:
            self._run_query(constraint)
