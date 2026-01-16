#!/usr/bin/env python3
# type: ignore
"""
Query Wazuh alerts, calculate threat scores, and update Neo4j ISIM
Location: /app/threat_calcs.py
"""

from opensearchpy import OpenSearch
from neo4j import GraphDatabase
import os
import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List, Tuple
import statistics
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/threat_calcs.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Neo4j connection from .env
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://resilmesh-sap-neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "supertestovaciheslo")

# OpenSearch connection from .env
OS_HOST = os.getenv("OS_HOST", "https://resilmesh-tap-wazuh-indexer:9200")
OS_USER = os.getenv("OS_USER", "admin")
OS_PASSWORD = os.getenv("OS_PASSWORD", "SecretPassword")
OS_INDEX = os.getenv("OS_INDEX", "wazuh-alerts-*")

# Parse the OS_HOST to extract components
parsed_url = urlparse(OS_HOST)
OPENSEARCH_HOST = parsed_url.hostname
OPENSEARCH_PORT = parsed_url.port or 9200
OPENSEARCH_SSL = parsed_url.scheme == 'https'

class WazuhThreatScoreCalculator:
    def __init__(self):
        """Initialize connections to OpenSearch and Neo4j"""
        # OpenSearch client
        logger.info(f"Connecting to OpenSearch at {OPENSEARCH_HOST}:{OPENSEARCH_PORT}")
        
        self.es = OpenSearch(
            hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
            http_auth=(OS_USER, OS_PASSWORD),
            use_ssl=OPENSEARCH_SSL,
            verify_certs=False,
            ssl_show_warn=False,
            timeout=30
        )
        
        # Test connection
        try:
            info = self.es.info()
            logger.info(f"Connected to OpenSearch version: {info['version']['number']}")
        except Exception as e:
            logger.error(f"Failed to connect to OpenSearch: {str(e)}")
            raise
        
        # Neo4j driver
        self.neo4j_driver = GraphDatabase.driver(
            NEO4J_URI, 
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        
    def close(self):
        """Close connections"""
        self.neo4j_driver.close()
        
    def map_wazuh_to_cvss(self, wazuh_level: int) -> float:
        """
        Map Wazuh alert level (1-15) to CVSS score (0-10)
        """
        mapping = {
            1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0, 5: 4.0,
            6: 4.5, 7: 5.0, 8: 6.0, 9: 7.0, 10: 7.5,
            11: 8.0, 12: 8.5, 13: 9.0, 14: 9.5, 15: 10.0
        }
        return mapping.get(wazuh_level, 0.0)
    
    def query_wazuh_alerts(self, time_range_hours: int = 24) -> Dict:
        """Query Wazuh alerts from OpenSearch"""
        query = {
            "size": 0,
            "_source": False,
            "query": {
                "bool": {
                    "must": [
                        {"match_all": {}},
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": f"now-{time_range_hours}h",
                                    "lte": "now"
                                }
                            }
                        }
                    ]
                }
            },
            "aggs": {
                "agents": {
                    "terms": {
                        "field": "agent.name",
                        "size": 1000
                    },
                    "aggs": {
                        "agent_ip": {
                            "terms": {
                                "field": "agent.ip",  # Get agent IP address
                                "size": 1
                            }
                        },
                        "by_rule_id": {
                            "terms": {
                                "field": "rule.id",
                                "size": 1000
                            },
                            "aggs": {
                                "levels": {
                                    "terms": {
                                        "field": "rule.level",
                                        "size": 1
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        try:
            response = self.es.search(
                index=OS_INDEX,
                body=query
            )
            logger.info(f"Successfully queried Wazuh alerts from index {OS_INDEX}")
            return response
        except Exception as e:
            logger.error(f"Error querying Wazuh alerts: {str(e)}")
            return None
    
    def calculate_threat_scores(self, wazuh_response: Dict) -> Dict[str, Tuple[float, str]]:
        """Calculate threat scores for each agent based on alert levels
        Returns: Dict mapping agent names to (threat_score, ip_address) tuples
        """
        threat_scores = {}
        
        if not wazuh_response or 'aggregations' not in wazuh_response:
            logger.warning("No aggregations found in Wazuh response")
            return threat_scores
        
        agents = wazuh_response['aggregations']['agents']['buckets']
        
        for agent in agents:
            agent_name = agent['key']
            alert_count = agent['doc_count']
            
            # Get agent IP if available
            agent_ip = None
            if 'agent_ip' in agent and agent['agent_ip']['buckets']:
                agent_ip = agent['agent_ip']['buckets'][0]['key']
                logger.info(f"Agent {agent_name} has IP: {agent_ip}")
            
            alert_levels = []
            weighted_scores = []
            
            for rule in agent['by_rule_id']['buckets']:
                rule_id = rule['key']
                rule_count = rule['doc_count']
                
                if rule['levels']['buckets']:
                    level = rule['levels']['buckets'][0]['key']
                    cvss_score = self.map_wazuh_to_cvss(level)
                    
                    alert_levels.extend([level] * min(rule_count, 100))
                    weighted_scores.append((cvss_score, rule_count))
            
            if weighted_scores:
                # Calculate scores
                total_weight = sum(min(count, 100) for score, count in weighted_scores)
                weighted_avg = sum(score * min(count, 100) for score, count in weighted_scores) / total_weight
                max_score = max(score for score, _ in weighted_scores)
                
                cvss_values = sorted([self.map_wazuh_to_cvss(l) for l in alert_levels])
                index = int(len(cvss_values) * 0.9)
                if index >= len(cvss_values):
                    index = len(cvss_values) - 1
                percentile_90 = cvss_values[index] if cvss_values else 0
                
                final_score = (weighted_avg * 0.4) + (max_score * 0.3) + (percentile_90 * 0.3)
                volume_factor = min(1.2, 1 + (alert_count / 10000))
                final_score = min(10.0, final_score * volume_factor)
                
                # Store both score and IP
                threat_scores[agent_name] = (round(final_score, 2), agent_ip)
                
                logger.info(f"Agent {agent_name} ({agent_ip}): {alert_count} alerts, "
                        f"threat score: {threat_scores[agent_name][0]}")
            else:
                threat_scores[agent_name] = (0.0, agent_ip)
                logger.info(f"Agent {agent_name} ({agent_ip}): No alerts with levels")
        
        return threat_scores

    def update_neo4j_threat_scores(self, threat_scores: Dict[str, Tuple[float, str]]) -> int:
        """Update threat scores in Neo4j for nodes/hosts"""
        nodes_updated = 0
        
        with self.neo4j_driver.session() as session:
            for agent_name, (threat_score, agent_ip) in threat_scores.items():
                try:
                    # Primary strategy: Match via IP address relationship
                    if agent_ip:
                        result = session.run("""
                            MATCH (n:Node)-[:HAS_ASSIGNED]->(ip:IP)
                            WHERE ip.address = $agent_ip
                            SET n.threatScore = $threat_score
                            RETURN count(n) as updated
                        """, agent_ip=agent_ip, threat_score=threat_score)
                        
                        count = result.single()['updated']
                        if count > 0:
                            nodes_updated += count
                            logger.info(f"Updated {count} nodes for agent {agent_name} via IP {agent_ip}")
                        else:
                            logger.warning(f"No nodes found with IP {agent_ip} for agent {agent_name}")
                    else:
                        logger.warning(f"No IP address found for agent {agent_name}")
                        
                except Exception as e:
                    logger.error(f"Error updating Neo4j for agent {agent_name}: {str(e)}")
        
        # Update average threat score
        try:
            with self.neo4j_driver.session() as session:
                session.run("""
                    MATCH (n:Node)
                    WHERE n.threatScore IS NOT NULL
                    WITH avg(n.threatScore) as avgThreat
                    MERGE (m:Metrics {type: 'threat_scores'})
                    SET m.averageThreatScore = avgThreat,
                        m.lastUpdated = datetime()
                """)
                logger.info("Updated average threat score metrics")
        except Exception as e:
            logger.error(f"Error updating metrics: {str(e)}")
        
        return nodes_updated

def main():
    """Main execution function"""
    logger.info("="*80)
    logger.info("Starting Wazuh Threat Score Calculation")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    
    calculator = WazuhThreatScoreCalculator()
    
    try:
        # Query Wazuh alerts
        logger.info("Querying Wazuh alerts from OpenSearch...")
        wazuh_response = calculator.query_wazuh_alerts(time_range_hours=24)
        
        if not wazuh_response:
            logger.error("Failed to get Wazuh alerts")
            return
        
        # Calculate threat scores
        logger.info("Calculating threat scores...")
        threat_scores = calculator.calculate_threat_scores(wazuh_response)
        
        if not threat_scores:
            logger.warning("No threat scores calculated")
            return
        
        logger.info(f"Calculated threat scores for {len(threat_scores)} agents")
        
        # Update Neo4j
        logger.info("Updating Neo4j with threat scores...")
        nodes_updated = calculator.update_neo4j_threat_scores(threat_scores)
        
        logger.info(f"Successfully updated {nodes_updated} nodes in Neo4j")
        
        # Log summary statistics
        if threat_scores:
            avg_score = statistics.mean([score for score, ip in threat_scores.values()])
            max_score = max([score for score, ip in threat_scores.values()])
            min_score = min([score for score, ip in threat_scores.values()])
            
            logger.info(f"Threat Score Statistics:")
            logger.info(f"  Average: {avg_score:.2f}")
            logger.info(f"  Maximum: {max_score:.2f}")
            logger.info(f"  Minimum: {min_score:.2f}")
            
            high_threat = {k: v[0] for k, v in threat_scores.items() if v[0] >= 7.0}
            if high_threat:
                logger.warning(f"High threat agents (score >= 7.0): {high_threat}")
        
    except Exception as e:
        logger.error(f"Fatal error in threat score calculation: {str(e)}")
        raise
    finally:
        calculator.close()
    
    logger.info("Threat Score Calculation completed!")
    logger.info("="*80)

if __name__ == "__main__":
    main()
