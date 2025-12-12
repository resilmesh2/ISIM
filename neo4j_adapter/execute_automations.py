#!/usr/bin/env python3
# type: ignore
"""
Execute scheduled risk calculations based on frequency
Location: /app/execute_automations.py
"""
import yaml
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/automation.log"),
    ]
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://resilmesh_sap_neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

def should_run_automation(automation: Dict[str, Any]) -> bool:
    """Check if automation should run based on frequency and last run time"""
    frequency = automation.get('update_frequency', 'manual')
    
    # Never run manual automations
    if frequency == 'manual':
        logger.info(f"Skipping manual automation")
        return False
    
    last_run = automation.get('last_run')
    if not last_run:
        # Never been run, so run it
        logger.info(f"Automation never run before, running now")
        return True
    
    # Parse last run time
    try:
        last_run_time = datetime.fromisoformat(last_run)
    except:
        # If we can't parse, run it
        logger.warning(f"Cannot parse last_run time, running anyway")
        return True
    
    now = datetime.now()
    time_since_last_run = now - last_run_time
    
    # Check based on frequency
    if frequency == 'minute':
        should_run = time_since_last_run >= timedelta(minutes=1)
        logger.info(f"Minute check: last run {time_since_last_run} ago, should run: {should_run}")
        return should_run
    elif frequency == 'hourly':
        should_run = time_since_last_run >= timedelta(hours=1)
        logger.info(f"Hourly check: last run {time_since_last_run} ago, should run: {should_run}")
        return should_run
    elif frequency == 'daily':
        should_run = time_since_last_run >= timedelta(days=1)
        logger.info(f"Daily check: last run {time_since_last_run} ago, should run: {should_run}")
        return should_run
    elif frequency == 'weekly':
        should_run = time_since_last_run >= timedelta(weeks=1)
        logger.info(f"Weekly check: last run {time_since_last_run} ago, should run: {should_run}")
        return should_run
    
    return False

def load_automations() -> Dict[str, Any]:
    """Load automation configurations from risk_assessment_config.yaml"""
    config_path = "/config/risk_assessment_config.yaml"
    
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file) or {}
            automations = config.get('active_automations', {})
            
            # Filter out None or invalid automation entries
            valid_automations = {}
            for automation_id, automation_config in automations.items():
                if automation_config and isinstance(automation_config, dict):
                    valid_automations[automation_id] = automation_config
                else:
                    logger.warning(f"Skipping invalid automation {automation_id}")
            
            return valid_automations
    except Exception as e:
        logger.error(f"Failed to load automations: {e}")
        return {}
    
def update_last_run(automation_id: str):
    """Update the last run time in the config"""
    config_path = "/config/risk_assessment_config.yaml"
    
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file) or {}
        
        if 'active_automations' in config and automation_id in config['active_automations']:
            config['active_automations'][automation_id]['last_run'] = datetime.now().isoformat()
            
            with open(config_path, 'w') as file:
                yaml.dump(config, file, default_flow_style=False)
            
            logger.info(f"Updated last_run for {automation_id}")
                
    except Exception as e:
        logger.error(f"Failed to update last run time: {e}")
        
def execute_automation(automation_id: str, config: dict):
    """Execute a single automation"""
    
    logger.info(f"Executing automation {automation_id}: {config.get('formula_name')}")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            components = config.get('components', [])
            formula_config = config.get('formula_config', {})
            target_type = config.get('target_type')
            target_values = config.get('target_values', [])
            target_property = config.get('target_property', 'Risk Score')
            
            calculation_method = config.get('calculation_method', 'weighted_avg')
            custom_formula = config.get('custom_formula', '')
            
            logger.info(f"Using calculation method: {calculation_method}")
            logger.info(f"Target property: '{target_property}'")
            
            # Build calculation
            calculation = build_calculation(components, formula_config, calculation_method, custom_formula)
            
            # Format property name for Neo4j
            if ' ' in target_property or '-' in target_property:
                formatted_property = f"`{target_property}`"
            else:
                formatted_property = target_property
            
            # Build query based on target type - use MATCH structure like in risk_api.py
            if target_type == 'all':
                query = f"""
                MATCH (n:Node)
                SET n.{formatted_property} = {calculation}
                RETURN count(n) as nodes_updated, avg(n.{formatted_property}) as avg_risk
                """
            elif target_type == 'subnet':
                subnet_list = "', '".join(target_values)
                query = f"""
                MATCH (subnet:Subnet)<-[:PART_OF]-(ip:IP)<-[:HAS_ASSIGNED]-(n:Node)
                WHERE subnet.range IN ['{subnet_list}']
                SET n.{formatted_property} = {calculation}
                RETURN count(n) as nodes_updated, avg(n.{formatted_property}) as avg_risk
                """
            elif target_type == 'ip':
                ip_list = "', '".join(target_values)
                query = f"""
                MATCH (n:Node)-[:HAS_ASSIGNED]->(ip:IP)
                WHERE ip.address IN ['{ip_list}']
                SET n.{formatted_property} = {calculation}
                RETURN count(n) as nodes_updated, avg(n.{formatted_property}) as avg_risk
                """
            else:
                query = f"""
                MATCH (n:Node)
                SET n.{formatted_property} = {calculation}
                RETURN count(n) as nodes_updated, avg(n.{formatted_property}) as avg_risk
                """
            
            result = session.run(query)
            record = result.single()
            
            if record:
                nodes_updated = record['nodes_updated']
                avg_risk = record['avg_risk']
                logger.info(f"Updated {nodes_updated} nodes. Average {target_property}: {avg_risk}")
                
                # Update automation metadata
                update_last_run(automation_id)
                
    except Exception as e:
        logger.error(f"Error executing automation {automation_id}: {e}")
    finally:
        driver.close()

# def build_where_clause(target_type: str, target_values: list) -> str:
#     """Build WHERE clause for Neo4j query based on target type"""
#     if target_type == 'all':
#         return "1=1"  # Always true
#     elif target_type == 'subnet':
#         # Fix: Use proper string formatting for IN clause
#         subnet_list = "', '".join(target_values)
#         return f"(n)<-[:HAS_ASSIGNED]-(:IP)-[:PART_OF]->(:Subnet {{range: IN ['{subnet_list}']}})"
#     elif target_type == 'ip':
#         # Fix: Use proper string formatting for IN clause  
#         ip_list = "', '".join(target_values)
#         return f"(n)<-[:HAS_ASSIGNED]-(:IP {{address: IN ['{ip_list}']}})"
#     else:
#         return "1=1"
    
def build_calculation(components, formula_config, method='weighted_avg', custom_formula=''):
    """Build calculation using live Neo4j property values per node"""
    
    logger.info(f"Building calculation with method: {method}")
    
    if method == 'weighted_avg':
        weighted_terms = []
        total_weight = 0
        
        for comp in components:
            comp_name = comp.get('name', '').replace(' ', '_').lower()
            weight = formula_config.get(comp_name, 0)
            # Use the actual Neo4j property, not currentValue
            neo4j_property = comp.get('neo4jProperty', comp_name)
            
            if weight > 0:
                # Reference the property on each node (n.property_name)
                if ' ' in neo4j_property or '-' in neo4j_property:
                    property_ref = f"COALESCE(n.`{neo4j_property}`, 0.0)"
                else:
                    property_ref = f"COALESCE(n.{neo4j_property}, 0.0)"
                
                weighted_terms.append(f"({property_ref} * {weight})")
                total_weight += weight
        
        if not weighted_terms or total_weight == 0:
            return "0.0"
        
        calculation = " + ".join(weighted_terms)
        return f"(({calculation}) / {total_weight})"
    
    elif method == 'max':
        property_refs = []
        for comp in components:
            neo4j_property = comp.get('neo4jProperty', comp.get('name', ''))
            if ' ' in neo4j_property or '-' in neo4j_property:
                property_refs.append(f"COALESCE(n.`{neo4j_property}`, 0.0)")
            else:
                property_refs.append(f"COALESCE(n.{neo4j_property}, 0.0)")
        
        if not property_refs:
            return "0.0"
        
        # Build nested CASE statements for max
        if len(property_refs) == 1:
            return property_refs[0]
        else:
            max_calc = property_refs[0]
            for prop_ref in property_refs[1:]:
                max_calc = f"CASE WHEN {prop_ref} > {max_calc} THEN {prop_ref} ELSE {max_calc} END"
            return max_calc
    
    elif method == 'sum':
        property_refs = []
        for comp in components:
            neo4j_property = comp.get('neo4jProperty', comp.get('name', ''))
            if ' ' in neo4j_property or '-' in neo4j_property:
                property_refs.append(f"COALESCE(n.`{neo4j_property}`, 0.0)")
            else:
                property_refs.append(f"COALESCE(n.{neo4j_property}, 0.0)")
        
        return " + ".join(property_refs) if property_refs else "0.0"
    
    elif method == 'custom_formula' and custom_formula:
        formula = custom_formula
        for comp in components:
            comp_name = comp.get('name', '')
            neo4j_property = comp.get('neo4jProperty', comp_name)
            
            # Replace component name with actual property reference
            if ' ' in neo4j_property or '-' in neo4j_property:
                property_ref = f"COALESCE(n.`{neo4j_property}`, 0.0)"
            else:
                property_ref = f"COALESCE(n.{neo4j_property}, 0.0)"
            
            formula = formula.replace(comp_name, property_ref)
        return formula
    
    else:
        logger.warning(f"Unknown method {method}, defaulting to weighted_avg")
        return build_calculation(components, formula_config, 'weighted_avg')

def main():
    """Main execution function"""
    logger.info("="*50)
    logger.info("Starting scheduled automation check")
    
    automations = load_automations()
    logger.info(f"Found {len(automations)} automation(s)")
    
    if not automations:
        logger.info("No automations configured")
        return
    
    for automation_id, config in automations.items():
        # Skip if config is None or not a dictionary
        if not config or not isinstance(config, dict):
            logger.warning(f"Skipping automation {automation_id} - invalid or missing configuration")
            continue
            
        frequency = config.get('update_frequency', 'manual')
        logger.info(f"Checking automation {automation_id} (frequency: {frequency})")
        
        if should_run_automation(config):
            execute_automation(automation_id, config)
        else:
            logger.info(f"Skipping {automation_id} - not due to run yet")
    
    logger.info("Automation execution complete")
    logger.info("="*50)

if __name__ == "__main__":
    main()