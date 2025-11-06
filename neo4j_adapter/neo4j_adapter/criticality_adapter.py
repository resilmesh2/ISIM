from pathlib import Path
from typing import Any, LiteralString, cast

from neo4j_adapter.general_adapter import GeneralAdapter

BASE_DIR = Path(__file__).parent


class CriticalityAdapter(GeneralAdapter):
    def __init__(self, password: str, **kwargs: Any) -> None:
        super().__init__(password=password, **kwargs)

    def _create_topology_projection(self) -> None:
        """
        This procedure creates a graph projection used to compute centrality values.
        Centrality values must be computed for results from Nmap traceroute scanning.
        :return: None
        """
        query = """MATCH (source:Node)-[r:IS_CONNECTED_TO]->(target:Node) WHERE r.hops = 1
                RETURN gds.graph.project(
                  'topologyGraph',
                  source,
                  target
                )"""
        query = cast("LiteralString", query)
        self._run_query(query)

    def _drop_topology_projection(self) -> None:
        """
        This procedure drops the graph projection formed from Nmap traceroute results
         used to compute centrality values.

        :return: None
        """
        query = "CALL gds.graph.drop('topologyGraph') YIELD graphName"
        query = cast("LiteralString", query)
        self._run_query(query)

    def compute_topology_betweenness(self) -> None:
        """
        Compute betweenness centrality on topology edges with hops count equal to 1.

        :return: None
        """
        self._create_topology_projection()
        query = """CALL gds.betweenness.stream('topologyGraph') YIELD nodeId, score MATCH (n:Node)
                WHERE id(n) = nodeId SET n.topology_betweenness = score"""
        query = cast("LiteralString", query)
        self._run_query(query)
        self._drop_topology_projection()

    def compute_topology_degree(self) -> None:
        """
        Compute degree centrality on topology edges.

        :return: None
        """
        self._create_topology_projection()
        query = """CALL gds.degree.stream('topologyGraph')
                YIELD nodeId, score
                MATCH (n:Node)
                WHERE id(n) = nodeId SET n.topology_degree = score"""
        query = cast("LiteralString", query)
        self._run_query(query)
        self._drop_topology_projection()

    def _create_graph_projection(self) -> None:
        """
        This procedure creates a graph projection used to compute centrality values.
        Centrality values must be computed for unique edges between two nodes.
        IP flow data consist of five-minute-long time windows, it is complicated to
        distinguish when a session starts and ends.
        From the perspective of criticality, the most important is how many hosts communicate to an important host.
        :return: None
        """
        query = """CALL gds.graph.project('centralityGraph', ['Node'], {
                 IS_CONNECTED_TO: {properties: {numberOfConnections: {property: '*', aggregation: 'COUNT'}}}})
                YIELD graphName AS graph, relationshipProjection AS degreeProjection,
                 nodeCount AS nodes, relationshipCount AS rels"""
        query = cast("LiteralString", query)
        self._run_query(query)

    def _drop_graph_projection(self) -> None:
        """
        This procedure drops a graph projection used to compute centrality values.
        :return: None
        """
        query = "CALL gds.graph.drop('centralityGraph') YIELD graphName"
        query = cast("LiteralString", query)
        self._run_query(query)

    def compute_ip_flow_degree(self) -> None:
        """
        Compute degree centrality on graph projection created from IP flow edges.
        :return: None
        """
        self._create_graph_projection()
        query = """CALL gds.degree.stream('centralityGraph') YIELD nodeId, score MATCH (n:Node)
        WHERE id(n) = nodeId SET n.degree_centrality = score"""
        query = cast("LiteralString", query)
        self._run_query(query)
        self._drop_graph_projection()

    def compute_ip_flow_pagerank(self) -> None:
        """
        Compute PageRank centrality on graph projection created from IP flow edges.
        :return: None
        """
        self._create_graph_projection()
        query = """CALL gds.pageRank.stream('centralityGraph') YIELD nodeId, score MATCH (n:Node)
        WHERE id(n) = nodeId SET n.pagerank_centrality = score"""
        query = cast("LiteralString", query)
        self._run_query(query)
        self._drop_graph_projection()
