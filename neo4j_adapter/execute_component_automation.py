# /app/execute_component_automation.py
#!/usr/bin/env python3
# type: ignore
"""
Execute scheduled component automations
Location: /app/execute_component_automation.py
"""
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from neo4j import GraphDatabase

from isim_common.config import LoggingConfig
from isim_common.observability import configure_logging, get_logger

load_dotenv()
configure_logging("isim-automation", LoggingConfig(level=os.getenv("LOG_LEVEL", "INFO")))
logger = get_logger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://resilmesh-sap-neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

COMPONENT_CONFIG_PATH = "/config/component_automation_config.yaml"
MAIN_CONFIG_PATH = "/config/risk_assessment_config.yaml"

def load_component_automations() -> Dict[str, Any]:
    """Load component automation configurations"""
    try:
        with open(COMPONENT_CONFIG_PATH, 'r') as file:
            config = yaml.safe_load(file)
            if config is None:
                logger.warning("component_automation_config_empty", path=COMPONENT_CONFIG_PATH)
                return {}
            return config.get('active_component_automations', {})
    except yaml.YAMLError:
        logger.exception("component_automation_config_parse_failed", path=COMPONENT_CONFIG_PATH)
        return None  # Return None to indicate parse error
    except Exception:
        logger.exception("component_automations_load_failed", path=COMPONENT_CONFIG_PATH)
        return {}
    
def should_run_component_automation(automation: Dict[str, Any]) -> bool:
    """Check if component automation should run"""
    frequency = automation.get('update_frequency', 'manual')
    
    # Check if automation is enabled
    if not automation.get('enabled', True):
        return False
    
    # Check if expired
    if automation.get('expires_at'):
        try:
            expires = datetime.fromisoformat(automation['expires_at'])
        except (TypeError, ValueError):
            logger.warning("component_automation_expires_at_parse_failed", expires_at=automation.get('expires_at'))
            return True
        if datetime.now() > expires:
            logger.info("component_automation_expired", expires_at=expires.isoformat())
            return False
    
    # Never run manual automations
    if frequency == 'manual':
        return False
    
    last_run = automation.get('last_run')
    if not last_run:
        logger.info("component_automation_due", reason="never_run")
        return True
    
    try:
        last_run_time = datetime.fromisoformat(last_run)
    except (TypeError, ValueError):
        logger.warning("component_automation_last_run_parse_failed", last_run=last_run)
        return True
    
    now = datetime.now()
    time_since_last_run = now - last_run_time
    
    # Check based on frequency
    frequency_checks = {
        'minute': timedelta(minutes=1),
        'hourly': timedelta(hours=1),
        'daily': timedelta(days=1),
        'weekly': timedelta(weeks=1)
    }
    
    required_delta = frequency_checks.get(frequency)
    if required_delta:
        should_run = time_since_last_run >= required_delta
        logger.info("component_automation_due_check", frequency=frequency, elapsed=str(time_since_last_run), should_run=should_run)
        return should_run
    
    return False

def execute_component_automation(automation_id: str, config: dict):
    """Execute component automation and update both Neo4j properties AND config"""
    
    component_name = config.get('component_name')
    logger.info("component_automation_execution_started", automation_id=automation_id, component_name=component_name)
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            data_source = config.get('data_source', {})
            source_type = data_source.get('type')
            query = data_source.get('query')
            neo4j_property = config.get('neo4j_property', config.get('component_id'))
            
            value = None
            
            # Execute based on source type
            if source_type == 'neo4j_query' and query:
                result = session.run(query)
                records = list(result)
                if records and 'value' in records[0]:
                    value = records[0]['value']
                    logger.info("component_automation_query_value_returned", automation_id=automation_id, value=value)
                    
            elif source_type == 'static_value':
                value = data_source.get('value', 0)
                logger.info("component_automation_static_value_used", automation_id=automation_id, value=value)
            
            # CRITICAL: Update Neo4j properties with the component value
            if value is not None and neo4j_property:
                # Format property name for Neo4j
                if ' ' in neo4j_property or '-' in neo4j_property:
                    formatted_property = f"`{neo4j_property}`"
                else:
                    formatted_property = neo4j_property
                
                # Update ALL nodes with this component property value
                update_query = f"""
                MATCH (n:Node)
                SET n.{formatted_property} = $value
                RETURN count(n) as updated_count
                """
                
                update_result = session.run(update_query, value=float(value))
                update_record = update_result.single()
                nodes_updated = update_record['updated_count'] if update_record else 0
                
                logger.info("component_automation_nodes_updated", automation_id=automation_id, nodes_updated=nodes_updated, neo4j_property=neo4j_property, value=value)
                
                # ALSO update config file for UI display
                update_component_value(component_name, value)
                update_last_run(automation_id)
                
                logger.info("component_automation_execution_completed", automation_id=automation_id)
            else:
                logger.warning("component_automation_missing_value_or_property", automation_id=automation_id, component_name=component_name, neo4j_property=neo4j_property)
                
    except Exception:
        logger.exception("component_automation_execution_failed", automation_id=automation_id)
    finally:
        driver.close()
        
def update_component_value(component_name: str, value: float):
    """Update component value in main risk assessment config"""
    try:
        with open(MAIN_CONFIG_PATH, 'r') as file:
            config = yaml.safe_load(file) or {}
        
        # Update in available_components
        if 'available_components' in config:
            for comp_key, comp_data in config['available_components'].items():
                if comp_data.get('name') == component_name:
                    comp_data['currentValue'] = value
                    comp_data['lastUpdated'] = datetime.now().isoformat()
                    break
        
        with open(MAIN_CONFIG_PATH, 'w') as file:
            yaml.dump(config, file, default_flow_style=False)
            
    except Exception:
        logger.exception("component_value_update_failed", component_name=component_name, path=MAIN_CONFIG_PATH)

def update_last_run(automation_id: str):
    """Update the last run time for component automation"""
    try:
        with open(COMPONENT_CONFIG_PATH, 'r') as file:
            config = yaml.safe_load(file) or {}
        
        if automation_id in config.get('active_component_automations', {}):
            config['active_component_automations'][automation_id]['last_run'] = datetime.now().isoformat()
            
            with open(COMPONENT_CONFIG_PATH, 'w') as file:
                yaml.dump(config, file, default_flow_style=False)
                
    except Exception:
        logger.exception("component_automation_last_run_update_failed", automation_id=automation_id, path=COMPONENT_CONFIG_PATH)

def main():
    """Main execution function"""
    logger.info("component_automation_check_started")
    
    automations = load_component_automations()
    
    # Handle None return (config parse error) or empty dict
    if automations is None:
        logger.error("component_automation_config_invalid")
        return
    
    if not automations:
        logger.info("no_component_automations_configured")
        return
    
    logger.info("component_automations_loaded", count=len(automations))
    
    for automation_id, config in automations.items():
        if not config or not isinstance(config, dict):
            logger.warning("component_automation_skipped", automation_id=automation_id, reason="invalid_configuration")
            continue
        
        if should_run_component_automation(config):
            execute_component_automation(automation_id, config)
        else:
            logger.info("component_automation_skipped", automation_id=automation_id, reason="not_due")
    
    logger.info("component_automation_check_completed")

if __name__ == "__main__":
    main()
