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
                logger.warning("Component config file is empty")
                return {}
            return config.get('active_component_automations', {})
    except yaml.YAMLError as e:
        logger.error(f"YAML syntax error in component automations: {e}")
        return None  # Return None to indicate parse error
    except Exception as e:
        logger.error(f"Failed to load component automations: {e}")
        return {}
    
def should_run_component_automation(automation: Dict[str, Any]) -> bool:
    """Check if component automation should run"""
    frequency = automation.get('update_frequency', 'manual')
    
    # Check if automation is enabled
    if not automation.get('enabled', True):
        return False
    
    # Check if expired
    if automation.get('expires_at'):
        expires = datetime.fromisoformat(automation['expires_at'])
        if datetime.now() > expires:
            logger.info(f"Automation expired at {expires}")
            return False
    
    # Never run manual automations
    if frequency == 'manual':
        return False
    
    last_run = automation.get('last_run')
    if not last_run:
        logger.info("Never run before, running now")
        return True
    
    try:
        last_run_time = datetime.fromisoformat(last_run)
    except:
        logger.warning("Cannot parse last_run time, running anyway")
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
        logger.info(f"{frequency} check: last run {time_since_last_run} ago, should run: {should_run}")
        return should_run
    
    return False

def execute_component_automation(automation_id: str, config: dict):
    """Execute component automation and update both Neo4j properties AND config"""
    
    component_name = config.get('component_name')
    logger.info(f"Executing component automation {automation_id}: {component_name}")
    
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
                    logger.info(f"Query returned value: {value}")
                    
            elif source_type == 'static_value':
                value = data_source.get('value', 0)
                logger.info(f"Using static value: {value}")
            
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
                
                logger.info(f"Updated {nodes_updated} nodes with {neo4j_property} = {value}")
                
                # ALSO update config file for UI display
                update_component_value(component_name, value)
                update_last_run(automation_id)
                
                logger.info(f"Component automation {automation_id} completed: Neo4j + config updated")
            else:
                logger.warning(f"No value or neo4j_property for {component_name}")
                
    except Exception as e:
        logger.error(f"Error executing component automation {automation_id}: {e}")
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
            
    except Exception as e:
        logger.error(f"Failed to update component value: {e}")

def update_last_run(automation_id: str):
    """Update the last run time for component automation"""
    try:
        with open(COMPONENT_CONFIG_PATH, 'r') as file:
            config = yaml.safe_load(file) or {}
        
        if automation_id in config.get('active_component_automations', {}):
            config['active_component_automations'][automation_id]['last_run'] = datetime.now().isoformat()
            
            with open(COMPONENT_CONFIG_PATH, 'w') as file:
                yaml.dump(config, file, default_flow_style=False)
                
    except Exception as e:
        logger.error(f"Failed to update last run time: {e}")

def main():
    """Main execution function"""
    logger.info("="*50)
    logger.info("Starting component automation check")
    
    automations = load_component_automations()
    
    # Handle None return (config parse error) or empty dict
    if automations is None:
        logger.error("Component automation config has syntax errors, cannot proceed")
        return
    
    if not automations:
        logger.info("No component automations configured")
        return
    
    logger.info(f"Found {len(automations)} component automation(s)")
    
    for automation_id, config in automations.items():
        if not config or not isinstance(config, dict):
            logger.warning(f"Skipping {automation_id} - invalid configuration")
            continue
        
        if should_run_component_automation(config):
            execute_component_automation(automation_id, config)
        else:
            logger.info(f"Skipping {automation_id} - not due to run")
    
    logger.info("Component automation execution complete")
    logger.info("="*50)

if __name__ == "__main__":
    main()
