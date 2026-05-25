#!/usr/bin/env python3
# type: ignore

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from isim_common.config import LoggingConfig
from isim_common.observability import configure_logging

load_dotenv()
configure_logging("isim-automation", LoggingConfig(level=os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger(__name__)

# Neo4j connection configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://resilmesh-sap-neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DATABASE_NAME = "neo4j"

class Neo4jGraphOperations:
    def __init__(self, uri, username, password, database):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
    
    def close(self):
        self.driver.close()
    
    def execute_query(self, query, description=""):
        """Execute a single Cypher query and return results"""
        with self.driver.session(database=self.database) as session:
            try:
                logger.info(f"Executing: {description}")
                result = session.run(query)
                records = list(result)
                
                # Log results summary
                if records:
                    logger.info(f"✓ Query executed successfully - {len(records)} records returned")
                    # Log first few records for debugging
                    for record in records[:3]:
                        logger.debug(dict(record))
                else:
                    logger.info(f"✓ Query executed successfully - no records returned")
                
                return records
                
            except Exception as e:
                logger.error(f"✗ Error executing query: {str(e)}")
                return None

def main():
    logger.info("="*80)
    logger.info("Starting ISIM calculations")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    
    # Initialize connection using environment variables
    neo4j_ops = Neo4jGraphOperations(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, DATABASE_NAME)
    
    try:
        # Create Graph
        create_graph_query = """
        CALL gds.graph.project(
          'myGraph',
          ['Host','Node'],  
          { IS_CONNECTED_TO: { orientation: 'UNDIRECTED' } }
        )
        YIELD graphName, nodeCount, relationshipCount
        """
        neo4j_ops.execute_query(create_graph_query, "Create Graph")
        
        # Betweenness LIMIT 20
        betweenness_query = """
        CALL gds.betweenness.stream('myGraph')
        YIELD nodeId, score AS betweenness
        MATCH (n) WHERE id(n) = nodeId
        RETURN
          COALESCE(n.address, elementId(n)) AS node_identifier,
          betweenness
        ORDER BY betweenness DESC
        LIMIT 20
        """
        neo4j_ops.execute_query(betweenness_query, "Betweenness LIMIT 20")
        
        # Degree LIMIT 20
        degree_query = """
        CALL gds.degree.stream('myGraph')
        YIELD nodeId, score AS degree
        MATCH (n) WHERE id(n) = nodeId
        RETURN
          COALESCE(n.address, elementId(n)) AS node_identifier,
          degree
        ORDER BY degree DESC
        LIMIT 20
        """
        neo4j_ops.execute_query(degree_query, "Degree LIMIT 20")
        
        # Write values back into nodes
        write_betweenness_query = """
        CALL gds.betweenness.write('myGraph', { writeProperty: 'betweenness' })
        YIELD nodePropertiesWritten
        """
        neo4j_ops.execute_query(write_betweenness_query, "Write betweenness values to nodes")
        
        write_degree_query = """
        CALL gds.degree.write('myGraph', { writeProperty: 'degree' })
        YIELD nodePropertiesWritten
        """
        neo4j_ops.execute_query(write_degree_query, "Write degree values to nodes")
        
        # Drop and recreate graph with properties
        drop_graph_query = """
        CALL gds.graph.drop('myGraph')
        """
        neo4j_ops.execute_query(drop_graph_query, "Drop myGraph")
        
        recreate_graph_query = """
        CALL gds.graph.project(
          'myGraph',
          ['Host','Node'],
          { IS_CONNECTED_TO: { orientation: 'UNDIRECTED' } },
          { nodeProperties: ['betweenness','degree'] }
        )
        YIELD graphName, nodeCount, relationshipCount
        """
        neo4j_ops.execute_query(recreate_graph_query, "Recreate graph with properties")
        
        # Normalize betweenness
        normalize_betweenness_query = """
        CALL gds.betweenness.stream('myGraph')
        YIELD nodeId, score AS rawB
        WITH
          collect(rawB)    AS allRaw,
          collect(nodeId)  AS allIds
        WITH
          allRaw,
          allIds,
          apoc.coll.min(allRaw) AS minB,
          apoc.coll.max(allRaw) AS maxB
        UNWIND range(0, size(allIds)-1) AS idx
        WITH
          gds.util.asNode(allIds[idx]) AS n,
          allRaw[idx] AS rawValue,
          minB,
          maxB
        WITH n,
          CASE 
            WHEN maxB - minB = 0 THEN 0.0
            ELSE toFloat((rawValue - minB) / (maxB - minB))
          END AS normB
        SET n.normalizedBetweenness = normB
        RETURN count(*) AS nodesUpdated
        """
        neo4j_ops.execute_query(normalize_betweenness_query, "Normalize betweenness")
        
        # Normalize degree
        normalize_degree_query = """
        CALL gds.degree.stream('myGraph')
        YIELD nodeId, score AS rawD
        WITH
          collect(rawD)    AS allRaw,
          collect(nodeId)  AS allIds
        WITH
          allRaw,
          allIds,
          apoc.coll.min(allRaw) AS minD,
          apoc.coll.max(allRaw) AS maxD
        UNWIND range(0, size(allIds)-1) AS idx
        WITH
          gds.util.asNode(allIds[idx]) AS n,
          allRaw[idx] AS rawValue,
          minD,
          maxD
        WITH n,
          CASE 
            WHEN maxD - minD = 0 THEN 0.0
            ELSE toFloat((rawValue - minD) / (maxD - minD))
          END AS normD
        SET n.normalizedDegree = normD
        RETURN count(*) AS nodesUpdated
        """
        neo4j_ops.execute_query(normalize_degree_query, "Normalize degree")
        
        # Set CVSS score on Nodes
        set_cvss_query = """
        MATCH (n:Node)-[:IS_A]->(h:Host)
            <-[:ON]-(sv:SoftwareVersion)
            <-[:IN]-(v:Vulnerability)
            -[:REFERS_TO]->(c:CVE)
        WITH n, COLLECT {
        MATCH (c)-[:HAS_CVSS_v31]->(cvss_v31:CVSSv31)
        RETURN cvss_v31.base_score as base_score
        UNION
        MATCH (c)-[:HAS_CVSS_v30]->(cvss_v30:CVSSv30)
        RETURN cvss_v30.base_score as base_score
        } AS base_score
        UNWIND base_score as bs
        WITH n, avg(bs) AS avgCvss
        SET n.cvss_score = avgCvss
        RETURN count(n)            AS nodesUpdated,
               round(avg(avgCvss),2) AS globalAverageCvss
        """
        neo4j_ops.execute_query(set_cvss_query, "Set CVSS score on Nodes")
        
        # Calculate average criticality
        average_criticality_query = """
        MATCH (n:Node)
        WHERE n.normalizedBetweenness IS NOT NULL
          AND n.normalizedDegree      IS NOT NULL
        WITH n, (n.normalizedBetweenness + n.normalizedDegree) / 2.0 AS avgNorm
        SET n.criticality = avgNorm * 10.0
        RETURN 
          count(n)                          AS nodesUpdated,
          round(avg(avgNorm * 10.0), 2)     AS avgCriticality
        """
        neo4j_ops.execute_query(average_criticality_query, "Calculate average criticality")

        # Calculate final Risk Score using the 3 components
        risk_score_query = """
        MATCH (n:Node)
        WHERE n.cvss_score IS NOT NULL 
          OR n.threatScore IS NOT NULL 
          OR n.criticality IS NOT NULL
        WITH n,
          COALESCE(n.cvss_score, 0.0) AS cvss,
          COALESCE(n.threatScore, 0.0) AS threat,  
          COALESCE(n.criticality, 0.0) AS crit
        SET n.`Risk Score` = (cvss * 0.4) + (threat * 0.3) + (crit * 0.3)
        RETURN 
          count(n) AS nodesUpdated,
          round(avg(n.`Risk Score`), 2) AS avgRiskScore,
          round(max(n.`Risk Score`), 2) AS maxRiskScore
        """
        neo4j_ops.execute_query(risk_score_query, "Calculate final Risk Score")

        drop_graph = """
        CALL gds.graph.drop('myGraph');
        """
        neo4j_ops.execute_query(drop_graph, "Graph cleanup")
        
        # ISIM plugin folder permissions
        logger.info("Running in container - skipping file permission changes")
        logger.info("Ensure proper permissions are set in Dockerfile or docker-compose")
        
        logger.info("All ISIM calculations completed successfully!")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"Fatal error in ISIM calculations: {str(e)}")
        sys.exit(1)
    finally:
        neo4j_ops.close()

if __name__ == "__main__":
    main()
