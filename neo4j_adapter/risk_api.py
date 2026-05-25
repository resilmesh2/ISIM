#!/usr/bin/env python3
# type: ignore
"""
Risk Assessment API for Angular integration
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import yaml
from flask import Flask, jsonify, request
from flask_cors import CORS
from neo4j import GraphDatabase
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleSpec,
    ScheduleState,
)

from isim_common.config import LoggingConfig
from isim_common.observability import configure_logging

configure_logging("isim-automation", LoggingConfig(level=os.getenv("LOG_LEVEL", "INFO")))

app = Flask(__name__)
CORS(app, 
     origins=['http://localhost:4201', 'http://localhost:3000','http://resilmesh-sap-isim-automation:5000' '*'],  # Angular dev server + Node.js
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization'],
     supports_credentials=True)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://resilmesh-sap-neo4j:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


logger = logging.getLogger(__name__)

# Config file path
CONFIG_PATH = "/config/risk_assessment_config.yaml"
COMPONENT_CONFIG_PATH = "/config/component_automation_config.yaml"

TEMPORAL_URL = os.environ.get("TEMPORAL_URL", "temporal:7233")

#IMPORTANT -- POST COMMANDS NEED TO BE SENT TO PORT 5000

def load_config() -> Optional[Dict[str, Any]]:
    """Load configuration from YAML file"""
    try:
        with open(CONFIG_PATH, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.error(f"Config file not found: {CONFIG_PATH}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config file: {e}")
        return None

def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to YAML file"""
    try:
        with open(CONFIG_PATH, 'w') as file:
            yaml.dump(config, file, default_flow_style=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving config file: {e}")
        return False

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "risk-assessment-api"})

@app.route('/api/formulas/predefined', methods=['GET'])
def get_predefined_formulas():
    """Get all predefined risk formulas"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
            
        predefined = config.get('predefined_formulas', {})
        formulas: List[Dict[str, Any]] = []
        
        for formula_id, formula_data in predefined.items():
            formulas.append({
                "id": formula_id,
                "name": formula_data.get('name'),
                "description": formula_data.get('description'),
                "components": formula_data.get('components', {}),
                "created_by": formula_data.get('created_by', 'system'),
                "created_date": formula_data.get('created_date'),
                "type": "predefined"
            })
        
        return jsonify({"formulas": formulas})
    except Exception as e:
        logger.error(f"Error getting predefined formulas: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/formulas/custom', methods=['GET'])
def get_custom_formulas():
    """Get all custom user-created formulas"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
            
        custom = config.get('custom_formulas', {})
        formulas: List[Dict[str, Any]] = []
        
        for formula_id, formula_data in custom.items():
            formulas.append({
                "id": formula_id,
                "name": formula_data.get('name'),
                "description": formula_data.get('description'),
                "components": formula_data.get('components', {}),
                "created_by": formula_data.get('created_by'),
                "created_date": formula_data.get('created_date'),
                "type": "custom"
            })
        
        return jsonify({"formulas": formulas})
    except Exception as e:
        logger.error(f"Error getting custom formulas: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/formulas/custom', methods=['POST'])
def create_custom_formula():
    """Create a new custom formula"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required_fields = ['name', 'description', 'components']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate components weights sum to 1.0
        components = data['components']
        if not isinstance(components, dict):
            return jsonify({"error": "Components must be a dictionary"}), 400
            
        total_weight = sum(components.values())
        if abs(total_weight - 1.0) > 0.01:  # Allow small floating point errors
            return jsonify({"error": f"Component weights must sum to 1.0, got {total_weight}"}), 400
        
        # Load current config
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        # Generate unique ID for formula
        formula_id = str(uuid.uuid4())[:8]  # Short UUID
        
        # Create formula object
        formula = {
            "name": data['name'],
            "description": data['description'],
            "components": components,
            "created_by": data.get('created_by', 'user'),
            "created_date": datetime.now().strftime('%Y-%m-%d'),
            "modified_date": datetime.now().strftime('%Y-%m-%d')
        }
        
        if 'custom_formulas' not in config:
            config['custom_formulas'] = {}
        config['custom_formulas'][formula_id] = formula
        
        # Save config
        if save_config(config):
            return jsonify({
                "message": "Formula created successfully",
                "formula_id": formula_id,
                "formula": formula
            })
        else:
            return jsonify({"error": "Failed to save formula"}), 500
            
    except Exception as e:
        logger.error(f"Error creating custom formula: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/formulas/active', methods=['GET'])
def get_active_formula():
    """Get currently active formula"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
            
        active = config.get('active_formula', {})
        formula_type = active.get('type', 'predefined')
        formula_name = active.get('name', 'balanced_security')
        
        # Get formula details from appropriate section
        if formula_type == 'predefined':
            formula_data = config.get('predefined_formulas', {}).get(formula_name, {})
        else:
            formula_data = config.get('custom_formulas', {}).get(formula_name, {})
        
        return jsonify({
            "active_formula": {
                "id": formula_name,
                "type": formula_type,
                "name": formula_data.get('name'),
                "description": formula_data.get('description'),
                "components": formula_data.get('components', {})
            }
        })
    except Exception as e:
        logger.error(f"Error getting active formula: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/formulas/active', methods=['PUT'])
def set_active_formula():
    """Set active formula"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        if 'formula_id' not in data or 'type' not in data:
            return jsonify({"error": "Missing formula_id or type"}), 400
        
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        # Validate formula exists
        formula_id = data['formula_id']
        formula_type = data['type']
        
        if formula_type == 'predefined':
            if formula_id not in config.get('predefined_formulas', {}):
                return jsonify({"error": "Predefined formula not found"}), 404
        elif formula_type == 'custom':
            if formula_id not in config.get('custom_formulas', {}):
                return jsonify({"error": "Custom formula not found"}), 404
        else:
            return jsonify({"error": "Invalid formula type"}), 400
        
        # Update active formula
        config['active_formula'] = {
            "type": formula_type,
            "name": formula_id
        }
        
        # Save config
        if save_config(config):
            return jsonify({"message": "Active formula updated successfully"})
        else:
            return jsonify({"error": "Failed to save config"}), 500
            
    except Exception as e:
        logger.error(f"Error setting active formula: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/formulas/custom/<formula_id>', methods=['DELETE'])
def delete_custom_formula(formula_id: str):
    """Delete a custom formula"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        # Check if formula exists
        custom_formulas = config.get('custom_formulas', {})
        if formula_id not in custom_formulas:
            return jsonify({"error": "Formula not found"}), 404
        
        # Remove formula
        del custom_formulas[formula_id]
        
        # If this was the active formula, reset to default
        active = config.get('active_formula', {})
        if active.get('type') == 'custom' and active.get('name') == formula_id:
            config['active_formula'] = {
                "type": "predefined",
                "name": "balanced_security"
            }
        
        # Save config
        if save_config(config):
            return jsonify({"message": "Formula deleted successfully"})
        else:
            return jsonify({"error": "Failed to save config"}), 500
            
    except Exception as e:
        logger.error(f"Error deleting formula: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/components/custom', methods=['GET'])
def get_custom_components():
    """Get all custom components"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        # Filter only custom components from available_components
        available_components = config.get('available_components', {})
        custom_components = []
        
        for component_key, component_data in available_components.items():
            if component_data.get('type') == 'custom':
                custom_components.append({
                    'id': component_key,
                    'name': component_data.get('name', component_key),
                    'description': component_data.get('description', ''),
                    'type': component_data.get('type', 'custom'),
                    'maxValue': component_data.get('max_value', 10),
                    'neo4jProperty': component_data.get('neo4j_property', component_key),
                    'icon': component_data.get('icon', '🔧')
                })
        
        return jsonify(custom_components)
        
    except Exception as e:
        logger.error(f"Error getting custom components: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/components/custom/<component_id>', methods=['DELETE'])
def delete_custom_component(component_id: str):
    """Delete a custom component and its automation"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        available_components = config.get('available_components', {})
        component_key_to_delete = None
        
        # Find component... (existing code)
        try:
            target_id = int(component_id)
        except ValueError:
            component_key_to_delete = component_id
        else:
            for component_key, component_data in available_components.items():
                generated_id = hash(component_key) % 100000
                if generated_id == target_id:
                    component_key_to_delete = component_key
                    break
        
        if not component_key_to_delete:
            return jsonify({"error": "Component not found"}), 404
            
        if component_key_to_delete not in available_components:
            return jsonify({"error": "Component not found"}), 404
            
        component = available_components[component_key_to_delete]
        
        if component.get('type') != 'custom':
            return jsonify({"error": "Cannot delete non-custom component"}), 400
        
        # DELETE TEMPORAL SCHEDULE FIRST
        neo4j_prop = component.get('neo4j_property', component_key_to_delete)
        schedule_id = f"component-schedule-{neo4j_prop}"
        
        async def delete_temporal_schedule():
            try:
                client = await get_temporal_client()
                handle = client.get_schedule_handle(schedule_id)
                await handle.delete()
                logger.info(f"Deleted Temporal schedule: {schedule_id}")
                return True
            except Exception as e:
                logger.warning(f"Could not delete Temporal schedule {schedule_id}: {e}")
                return False
        
        temporal_deleted = asyncio.run(delete_temporal_schedule())
        
        # Remove the component (existing code continues...)
        del available_components[component_key_to_delete]
        
        if not save_config(config):
            return jsonify({"error": "Failed to save config"}), 500
        
        # Remove automations... (existing code)
        try:
            component_config = load_component_config()
            if component_config and 'active_component_automations' in component_config:
                automations_to_delete = []
                
                for auto_id, automation in component_config['active_component_automations'].items():
                    if (automation.get('component_id') == component_key_to_delete or
                        auto_id == f"comp_auto_{component_key_to_delete}" or
                        automation.get('neo4j_property') == component.get('neo4j_property')):
                        automations_to_delete.append(auto_id)
                
                for auto_id in automations_to_delete:
                    del component_config['active_component_automations'][auto_id]
                    logger.info(f"Deleted automation {auto_id}")
                
                if automations_to_delete:
                    save_component_config(component_config)
                    
        except Exception as e:
            logger.error(f"Error removing automations: {e}")
            
        return jsonify({
            "success": True,
            "message": f"Component {component_key_to_delete} deleted successfully",
            "temporal_schedule_deleted": temporal_deleted
        })
        
    except Exception as e:
        logger.error(f"Error deleting custom component: {e}")
        return jsonify({"error": str(e)}), 500
       
@app.route('/api/components/neo4j-property/<neo4j_property>', methods=['DELETE'])
def delete_neo4j_property(neo4j_property: str):
    """Delete a component property from all nodes in Neo4j"""
    driver = None
    try:
        logger.info(f"Starting Neo4j property deletion for: {neo4j_property}")
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        logger.info(f"Neo4j driver created successfully")
        
        # Use a write transaction to ensure the changes are committed
        def delete_property_transaction(tx, formatted_prop):
            # First check how many nodes have this property
            check_query = f"""
            MATCH (n:Node)
            WHERE n.{formatted_prop} IS NOT NULL
            RETURN count(n) as nodeCount
            """
            
            logger.info(f"Checking existing nodes with query: {check_query}")
            check_result = tx.run(check_query)
            check_record = check_result.single()
            nodes_with_property = check_record["nodeCount"] if check_record else 0
            
            logger.info(f"Found {nodes_with_property} nodes with property {neo4j_property}")
            
            if nodes_with_property == 0:
                return 0, nodes_with_property, 0
            
            # Delete the property from all nodes that have it
            delete_query = f"""
            MATCH (n:Node)
            WHERE n.{formatted_prop} IS NOT NULL
            REMOVE n.{formatted_prop}
            RETURN count(n) as nodesUpdated
            """
            
            logger.info(f"Executing Neo4j deletion query: {delete_query}")
            delete_result = tx.run(delete_query)
            
            delete_record = delete_result.single()
            nodes_updated = delete_record["nodesUpdated"] if delete_record else 0
            
            logger.info(f"Transaction reports {nodes_updated} nodes updated")
            
            # Verify deletion within the same transaction
            verify_result = tx.run(check_query)
            verify_record = verify_result.single()
            remaining_nodes = verify_record["nodeCount"] if verify_record else 0
            
            logger.info(f"Verification within transaction: {remaining_nodes} nodes still have the property")
            
            return nodes_updated, nodes_with_property, remaining_nodes

        # Format property name for Neo4j query
        formatted_prop = f"`{neo4j_property}`" if ' ' in neo4j_property or '-' in neo4j_property else neo4j_property
        logger.info(f"Formatted property name: {formatted_prop}")
        
        # Execute the deletion in a write transaction
        with driver.session() as session:
            nodes_updated, nodes_found, remaining_nodes = session.execute_write(
                delete_property_transaction, formatted_prop
            )
            
            logger.info(f"Transaction completed: {nodes_updated} nodes updated, {remaining_nodes} remaining")
            
            return jsonify({
                "success": True,
                "message": f"Property {neo4j_property} deleted from {nodes_updated} nodes in Neo4j",
                "nodesUpdated": nodes_updated,
                "nodesFound": nodes_found,
                "remainingNodes": remaining_nodes,
                "transactionCommitted": True
            })
            
    except Exception as e:
        logger.error(f"Error deleting Neo4j property {neo4j_property}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error args: {e.args}")
        return jsonify({
            "success": False,
            "error": f"Failed to delete Neo4j property: {str(e)}",
            "property": neo4j_property
        }), 500
        
    finally:
        if driver:
            driver.close()
            
@app.route('/api/components/neo4j-property-test/<neo4j_property>', methods=['GET'])
def test_neo4j_property_deletion(neo4j_property: str):
    """Test endpoint to check if Neo4j property deletion would work"""
    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            # Format property name for Neo4j query
            formatted_prop = f"`{neo4j_property}`" if ' ' in neo4j_property or '-' in neo4j_property else neo4j_property
            
            # Check how many nodes have this property
            check_query = f"""
            MATCH (n:Node)
            WHERE n.{formatted_prop} IS NOT NULL
            RETURN count(n) as nodeCount, collect(n.{formatted_prop})[0..5] as sampleValues
            """
            
            logger.info(f"Testing Neo4j query: {check_query}")
            result = session.run(check_query)
            
            record = result.single()
            node_count = record["nodeCount"]
            sample_values = record["sampleValues"]
            
            logger.info(f"Found {node_count} nodes with property {neo4j_property}")
            
            return jsonify({
                "success": True,
                "message": f"Found {node_count} nodes with property '{neo4j_property}'",
                "nodeCount": node_count,
                "sampleValues": sample_values,
                "formattedProperty": formatted_prop,
                "originalProperty": neo4j_property,
                "neo4jUri": NEO4J_URI,
                "neo4jUser": NEO4J_USER
            })
            
    except Exception as e:
        logger.error(f"Error testing Neo4j property: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to test Neo4j property: {str(e)}"
        }), 500
        
    finally:
        if driver:
            driver.close()

@app.route('/api/components/available', methods=['GET'])
def get_risk_available_components():
    """Get all available risk components from config"""
    try:
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
            
        available_components = config.get('available_components', {})
        component_list: List[Dict[str, Any]] = []
        
        # Convert YAML structure to the format Angular expects
        for component_key, component_data in available_components.items():
            component_list.append({
                "id": hash(component_key) % 100000,  # Generate consistent ID from key
                "name": component_data.get('name'),
                "description": component_data.get('description'),
                "type": component_data.get('type'),
                "icon": component_data.get('icon'),
                "weight": 0.2,  # Default weight
                "maxValue": component_data.get('max_value', 10),
                "currentValue": component_data.get('max_value', 10) / 2,  # Default to half max
                "neo4jProperty": component_data.get('neo4j_property'),
                "isComposite": component_data.get('type') in ['composite', 'centrality'],
                "statistics": {
                    "avg": component_data.get('max_value', 10) / 2,
                    "max": component_data.get('max_value', 10),
                    "min": component_data.get('min_value', 0)
                }
            })
        
        return jsonify({"available_components": component_list})
        
    except Exception as e:
        logger.error(f"Error getting available components: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/risk/components/custom', methods=['POST'])
def save_custom_component():
    """Save a custom component and create automation skeleton"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        required_fields = ['name', 'type', 'maxValue']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Load risk assessment config
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        # Create component key from name
        component_key = data['name'].lower().replace(' ', '_').replace('-', '_')
        component_key = ''.join(c for c in component_key if c.isalnum() or c == '_')
        
        # Handle duplicate names
        if component_key in config.get('available_components', {}):
            component_key = f"{component_key}_{int(datetime.now().timestamp())}"
        
        # Create component in main config
        # IMPORTANT: Force type to 'custom' for ALL user-created components
        # The category they selected (security, compliance, etc.) is stored separately
        new_component = {
            "name": data['name'],
            "description": data.get('description', f"{data['type'].capitalize()} component for risk assessment"),
            "type": "custom",  # ALWAYS set to 'custom' for user-created components
            "category": data['type'],  # Store the actual category they selected
            "icon": data.get('icon', '🔧'),
            "min_value": 0,
            "max_value": data['maxValue'],
            "neo4j_property": data.get('neo4jProperty', component_key)
        }
        
        if 'available_components' not in config:
            config['available_components'] = {}
        config['available_components'][component_key] = new_component
        
        # Save main config
        if not save_config(config):
            return jsonify({"error": "Failed to save configuration"}), 500
        
        # Now create automation skeleton in component automation config
        component_config = load_component_config()
        
        # Check for None (parse error)
        if component_config is None:
            logger.error("Component automation config has syntax errors")
            logger.warning("Could not create automation skeleton due to config errors")
            return jsonify({
                "success": True,
                "component_key": component_key,
                "message": f"Component created but automation skeleton could not be added due to config errors"
            }), 200
        
        # Safe to proceed with automation skeleton
        if not component_config:
            component_config = get_default_component_config()
        
        # Create automation ID
        auto_id = f"comp_auto_{component_key}"
        
        # Create skeleton automation entry
        skeleton_automation = {
            'component_name': data['name'],
            'component_id': component_key,
            'neo4j_property': data.get('neo4jProperty', component_key),
            'update_frequency': 'manual',
            'calculation_method': 'query_result',
            'target_property': data.get('neo4jProperty', component_key),
            'enabled': False,  # Start disabled until configured
            'created_at': datetime.now().isoformat(),
            'last_run': None,
        }

        # Add to automations
        if 'active_component_automations' not in component_config:
            component_config['active_component_automations'] = {}
        
        component_config['active_component_automations'][auto_id] = skeleton_automation
        
        # Save component automation config
        if not save_component_config(component_config):
            logger.warning("Failed to save automation skeleton, but component was created")
        
        logger.info(f"Created component '{data['name']}' with key '{component_key}' and automation skeleton")
        
        return jsonify({
            "success": True,
            "component_key": component_key,
            "automation_id": auto_id,
            "message": f"Component created with automation skeleton. Edit query in config file at automation ID: {auto_id}"
        }), 200
        
    except Exception as e:
        logger.error(f"Error saving custom component: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/components/custom/<component_identifier>/config', methods=['GET', 'OPTIONS'])
def get_custom_component_config(component_identifier):
    """Get configuration for a custom component from the automation config"""
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        config = load_component_config()
        if config is None:
            return jsonify({
                "component_identifier": component_identifier,
                "automation": None,
                "error": "Configuration file has syntax errors"
            }), 500
        
        automations = config.get('active_component_automations', {})
        
        for auto_id, automation in automations.items():
            if (automation.get('component_id') == component_identifier or 
                automation.get('component_name', '').lower().replace(' ', '_') == component_identifier.lower() or
                automation.get('target_property') == component_identifier):
                
                # Return automation without data_source
                return jsonify({
                    "component_identifier": component_identifier,
                    "automation": {
                        "id": auto_id,
                        "component_name": automation.get('component_name'),
                        "component_id": automation.get('component_id'),
                        "neo4j_property": automation.get('neo4j_property'),
                        "update_frequency": automation.get('update_frequency', 'manual'),
                        "calculation_method": automation.get('calculation_method'),
                        "target_property": automation.get('target_property'),
                        "enabled": automation.get('enabled', False),
                        "last_run": automation.get('last_run'),
                        "notes": automation.get('notes')
                    }
                })
        
        return jsonify({
            "component_identifier": component_identifier,
            "automation": None,
            "message": "No automation found for this component"
        })
        
    except Exception as e:
        logger.error(f"Error getting component config: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/components/custom/<component_identifier>/execute', methods=['POST', 'OPTIONS'])
def execute_component_query(component_identifier):
    """Execute a query for a component and update Neo4j"""
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        query = data.get('query')
        update_neo4j = data.get('update_neo4j', True)
        target_property = data.get('target_property', component_identifier)
        
        logger.info(f"Execute called for {component_identifier}")
        logger.info(f"Query from request: {query}")
        
        if not query:
            config = load_component_config()
            logger.info(f"No query in request, loading from config")
            automations = config.get('active_component_automations', {})
            
            for auto_id, automation in automations.items():
                if (automation.get('component_id') == component_identifier or
                    automation.get('neo4j_property') == component_identifier or
                    automation.get('target_property') == component_identifier):
                    query = automation.get('data_source', {}).get('query')
                    target_property = automation.get('target_property', component_identifier)
                    logger.info(f"Found query in automation {auto_id}: {query}")
                    break
        
        if not query:
            return jsonify({"error": "No query provided"}), 400
        
        logger.info(f"Final query to execute: {query}")
        
        # Check if query contains TODO/placeholder text
        if '# TODO' in query or 'TODO:' in query or 'MATCH (n:Node) RETURN 0 as value' in query:
            return jsonify({
                "error": "Query not configured",
                "message": "Please edit the query in component_automation_config.yaml file. Replace the TODO section with your actual query.",
                "user_action_required": "Edit the automation query in the config file"
            }), 400
        
        # Security check - prevent destructive operations
        query_upper = query.upper()
        destructive_keywords = [
            'DELETE', 'REMOVE', 'DROP', 'DETACH', 'DESTROY', 
            'TRUNCATE', 'SET n = {}', 'CREATE INDEX', 'CREATE CONSTRAINT',
            'DROP INDEX', 'DROP CONSTRAINT', 'STOP DATABASE', 'START DATABASE'
        ]
        
        for keyword in destructive_keywords:
            if keyword in query_upper:
                logger.warning(f"Blocked potentially destructive query containing '{keyword}' from component {component_identifier}")
                return jsonify({
                    "error": "Query contains potentially destructive operations",
                    "message": f"Query cannot contain '{keyword}'. Only read operations (MATCH, RETURN) and safe SET operations for the component property are allowed.",
                    "blocked_keyword": keyword
                }), 400
        
        # Additional check for comments that might be malformed
        if query.strip().startswith('#'):
            return jsonify({
                "error": "Invalid query format",
                "message": "Query cannot start with a comment. Please provide a valid Cypher query.",
                "hint": "Remove comment lines or ensure your query starts with MATCH"
            }), 400
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        nodes_updated = 0
        
        try:
            with driver.session() as session:
                # Execute the query to get the value
                result = session.run(query)
                record = result.single()
                
                logger.info(f"Query result record: {record}")
                
                # FIXED VALUE EXTRACTION
                if record is not None:
                    try:
                        # The record object has the value, but we need to check if it exists
                        if 'value' in record.keys():
                            value = record['value']
                            if value is not None:
                                value = float(value)
                            else:
                                value = 0
                                logger.warning("Query returned null value")
                        else:
                            value = 0
                            logger.warning("No 'value' field in query result")
                    except (KeyError, TypeError) as e:
                        logger.warning(f"Could not extract value from record: {e}")
                        value = 0
                else:
                    value = 0
                    logger.warning("Query returned no records")
                
                logger.info(f"Extracted value: {value}")
                
                # Update all nodes with this property value
                if update_neo4j:
                    update_query = f"""
                    MATCH (n:Node)
                    SET n.{target_property} = $value
                    RETURN count(n) as updated_count
                    """
                    
                    update_result = session.run(update_query, value=value)
                    update_record = update_result.single()
                    nodes_updated = update_record['updated_count'] if update_record else 0
                    
                    logger.info(f"Updated {nodes_updated} nodes with {target_property} = {value}")
                    
                    # Update risk scores
                    update_risk_scores(session, target_property, value)
            
            driver.close()
            
            return jsonify({
                "success": True,
                "value": value,
                "component_id": component_identifier,
                "nodes_updated": nodes_updated,
                "property_updated": target_property
            }), 200
            
        except Exception as e:
            driver.close()
            error_message = str(e)
            
            # Check for common Neo4j syntax errors
            if "SyntaxError" in error_message:
                if "Invalid input '#'" in error_message:
                    return jsonify({
                        "error": "Query syntax error",
                        "message": "Query contains invalid syntax. Comments should be removed or the query should start with a valid Cypher statement like MATCH.",
                        "hint": "Edit the query in component_automation_config.yaml and remove the TODO comments"
                    }), 400
                else:
                    return jsonify({
                        "error": "Query syntax error",
                        "message": "The query contains invalid Cypher syntax. Please check your query in the config file.",
                        "details": error_message
                    }), 400
            
            logger.error(f"Query execution failed: {e}")
            return jsonify({"error": f"Query failed: {str(e)}"}, 500)
            
    except Exception as e:
        logger.error(f"Error executing component query: {e}")
        return jsonify({"error": str(e)}), 500
           
@app.route('/api/components/neo4j/update', methods=['POST', 'OPTIONS'])
def update_neo4j_property():
    """Directly update a Neo4j property for all nodes"""
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        property_name = data.get('property')
        value = data.get('value')
        
        if not property_name:
            return jsonify({"error": "Property name required"}), 400
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            query = f"""
            MATCH (n:Node)
            SET n.{property_name} = $value
            RETURN count(n) as updated_count
            """
            
            result = session.run(query, value=value)
            record = result.single()
            nodes_updated = record['updated_count'] if record else 0
            
            update_risk_scores(session, property_name, value)
            
        driver.close()
        
        return jsonify({
            "success": True,
            "property": property_name,
            "value": value,
            "nodes_updated": nodes_updated
        }), 200
        
    except Exception as e:
        logger.error(f"Error updating Neo4j property: {e}")
        return jsonify({"error": str(e)}), 500
    
def update_risk_scores(session, component_property, component_value):
    """Update risk scores for nodes after component value change"""
    try:
        config = load_config()
        if not config:
            logger.warning("No risk configuration found, skipping risk score update")
            return
            
        automations = config.get('active_automations', {})
        if not automations:
            logger.info("No active risk automations to update")
            return
        
        for auto_id, automation in automations.items():
            if not automation:
                continue
                
            components = automation.get('components', [])
            
            for comp in components:
                if comp.get('neo4jProperty') == component_property:
                    calculation_method = automation.get('calculation_method', 'weighted_avg')
                    
                    if calculation_method == 'weighted_avg':
                        weight_calculations = []
                        total_weight = 0
                        
                        for c in components:
                            weight = c.get('weight', 0.33)
                            total_weight += weight
                            prop = c.get('neo4jProperty')
                            max_val = c.get('maxValue', 10)
                            
                            weight_calculations.append(
                                f"(COALESCE(n.{prop}, 0) / {max_val}) * {weight}"
                            )
                        
                        calculation = " + ".join(weight_calculations)
                        
                        risk_query = f"""
                        MATCH (n:Node)
                        SET n.`Risk Score` = ({calculation}) * 10
                        RETURN avg(n.`Risk Score`) as avg_risk
                        """
                        
                        result = session.run(risk_query)
                        record = result.single()
                        avg_risk = record['avg_risk'] if record else 0
                        
                        logger.info(f"Updated Risk Score values. Average risk: {avg_risk}")
                        
                        automation['last_run'] = datetime.now().isoformat()
                        automation['avg_risk_score'] = float(avg_risk)
                        config['active_automations'][auto_id] = automation
                        save_config(config)
                        
    except Exception as e:
        logger.error(f"Error updating risk scores: {e}")

@app.route('/api/components/custom/<component_id>/config', methods=['PUT'])
def update_custom_component_config(component_id):
    """Update configuration for a custom component"""
    try:
        data = request.get_json()
        
        config = load_component_config()
        
        if config is None:
            logger.error("Cannot update config - file has syntax errors")
            return jsonify({"error": "Configuration file has syntax errors, cannot update"}), 500
        
        if not config:
            config = get_default_component_config()
        
        if 'active_component_automations' not in config:
            config['active_component_automations'] = {}
        
        automations = config['active_component_automations']
        
        # Look for existing automation
        existing_auto_id = None
        skeleton_auto_id = f"comp_auto_{component_id}"
        
        if skeleton_auto_id in automations:
            existing_auto_id = skeleton_auto_id
        else:
            # Search by component properties
            for auto_id, automation in automations.items():
                if automation.get('component_id') == component_id:
                    existing_auto_id = auto_id
                    break
        
        # Update or create automation entry (without data_source)
        if existing_auto_id:
            # Update only update_frequency and enabled status
            automations[existing_auto_id].update({
                'update_frequency': data.get('update_frequency', 'manual'),
                'enabled': data.get('enabled', False),
                'last_modified': datetime.now().isoformat()
            })
        else:
            # Create new automation without data_source
            new_auto_id = f"comp_auto_{component_id}_{int(datetime.now().timestamp())}"
            automations[new_auto_id] = {
                'component_id': component_id,
                'component_name': data.get('component_name'),
                'neo4j_property': data.get('neo4j_property', component_id),
                'update_frequency': data.get('update_frequency', 'manual'),
                'calculation_method': 'query_result',
                'target_property': data.get('target_property', component_id),
                'enabled': data.get('enabled', False),
                'created_at': datetime.now().isoformat()
            }
        
        # Save updated config
        if save_component_config(config):
            return jsonify({
                "success": True,
                "message": "Component configuration updated",
                "automation_id": existing_auto_id or new_auto_id
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
            
    except Exception as e:
        logger.error(f"Error updating component config: {e}")
        return jsonify({"error": str(e)}), 500
    
def build_calculation(components, formula_config, method='weighted_avg', custom_formula=''):
    """Build calculation based on selected method using Neo4j properties with proper formatting"""
    
    logger.info(f"Building calculation with method: {method}")
    
    if method == 'weighted_avg':
        weighted_terms = []
        total_weight = 0
        missing_components = []
        
        for comp in components:
            comp_name = comp.get('name', '').replace(' ', '_').lower()
            weight = formula_config.get(comp_name, 0)
            neo4j_property = comp.get('neo4jProperty', comp_name)
            
            # Check if component has valid property
            if not neo4j_property:
                missing_components.append(comp_name)
                logger.warning(f"Component '{comp_name}' has no neo4jProperty, skipping")
                continue
                
            if weight > 0:
                # Use COALESCE to handle missing properties gracefully with proper formatting
                if ' ' in neo4j_property or '-' in neo4j_property:
                    property_ref = f"COALESCE(n.`{neo4j_property}`, 0.0)"
                else:
                    property_ref = f"COALESCE(n.{neo4j_property}, 0.0)"
                
                weighted_terms.append(f"({property_ref} * {weight})")
                total_weight += weight
        
        # Log missing components for admin awareness
        if missing_components:
            logger.warning(f"Missing components in calculation: {missing_components}")
        
        # Handle case where all components are missing
        if not weighted_terms or total_weight == 0:
            logger.warning("No valid components found for calculation, returning 0.0")
            return "0.0"
        
        calculation = " + ".join(weighted_terms)
        return f"(({calculation}) / {total_weight})"
    
    elif method == 'max':
        property_refs = []
        missing_components = []
        
        for comp in components:
            neo4j_property = comp.get('neo4jProperty', comp.get('name', ''))
            comp_name = comp.get('name', 'unknown')
            
            if not neo4j_property:
                missing_components.append(comp_name)
                continue
                
            if ' ' in neo4j_property or '-' in neo4j_property:
                property_refs.append(f"COALESCE(n.`{neo4j_property}`, 0.0)")
            else:
                property_refs.append(f"COALESCE(n.{neo4j_property}, 0.0)")
        
        if missing_components:
            logger.warning(f"Missing components in max calculation: {missing_components}")
        
        if not property_refs:
            logger.warning("No valid properties for max calculation")
            return "0.0"
        
        if len(property_refs) == 1:
            return property_refs[0]
        else:
            max_calc = property_refs[0]
            for prop_ref in property_refs[1:]:
                max_calc = f"CASE WHEN {prop_ref} > {max_calc} THEN {prop_ref} ELSE {max_calc} END"
            return max_calc
    
    elif method == 'sum':
        property_refs = []
        missing_components = []
        
        for comp in components:
            neo4j_property = comp.get('neo4jProperty', comp.get('name', ''))
            comp_name = comp.get('name', 'unknown')
            
            if not neo4j_property:
                missing_components.append(comp_name)
                continue
                
            if ' ' in neo4j_property or '-' in neo4j_property:
                property_refs.append(f"COALESCE(n.`{neo4j_property}`, 0.0)")
            else:
                property_refs.append(f"COALESCE(n.{neo4j_property}, 0.0)")
        
        if missing_components:
            logger.warning(f"Missing components in sum calculation: {missing_components}")
        
        return " + ".join(property_refs) if property_refs else "0.0"
    
    elif method == 'geometric_mean':
        property_refs = []
        missing_components = []
        
        for comp in components:
            neo4j_property = comp.get('neo4jProperty', comp.get('name', ''))
            comp_name = comp.get('name', 'unknown')
            
            if not neo4j_property:
                missing_components.append(comp_name)
                continue
                
            if ' ' in neo4j_property or '-' in neo4j_property:
                prop_ref = f"COALESCE(n.`{neo4j_property}`, 0.0)"
            else:
                prop_ref = f"COALESCE(n.{neo4j_property}, 0.0)"
            property_refs.append(f"CASE WHEN {prop_ref} > 0 THEN {prop_ref} ELSE 0.1 END")
        
        if missing_components:
            logger.warning(f"Missing components in geometric mean calculation: {missing_components}")
        
        if not property_refs:
            return "0.0"
        
        n = len(property_refs)
        product = " * ".join(property_refs)
        return f"(({product})^(1.0/{n}))"

    elif method == 'custom_formula' and custom_formula:
        formula = custom_formula
        missing_replacements = []
        
        for comp in components:
            comp_name = comp.get('name', '')
            neo4j_property = comp.get('neo4jProperty', comp_name)
            
            if not neo4j_property:
                missing_replacements.append(comp_name)
                # Replace with 0.0 for missing components
                formula = formula.replace(comp_name, "0.0")
                continue
            
            if ' ' in neo4j_property or '-' in neo4j_property:
                property_ref = f"COALESCE(n.`{neo4j_property}`, 0.0)"
            else:
                property_ref = f"COALESCE(n.{neo4j_property}, 0.0)"
            
            formula = formula.replace(comp_name, property_ref)
        
        if missing_replacements:
            logger.warning(f"Replaced missing components with 0.0 in custom formula: {missing_replacements}")
        
        return formula
    
    else:
        logger.warning(f"Unknown method {method}, defaulting to weighted_avg")
        return build_calculation(components, formula_config, 'weighted_avg')
           
@app.route('/api/risk/apply-configuration', methods=['POST'])
def apply_risk_configuration():
    try:
        data = request.get_json()
        
        components = data.get('components', [])
        target_type = data.get('targetType')
        target_values = data.get('targetValues', [])
        calculation_mode = data.get('calculationMode', 'setValue')
        update_frequency = data.get('updateFrequency', 'manual')
        target_property = data.get('targetProperty', 'Risk Score')
        formula_name = data.get('formulaName', 'Custom Formula')
        
        calculation_method = data.get('calculationMethod', 'weighted_avg')
        custom_formula = data.get('customFormula', '')
        
        logger.info(f"Received calculation method: {calculation_method}")
        
        formula_config = {}
        for comp in components:
            comp_name = comp.get('name', '').replace(' ', '_').lower()
            formula_config[comp_name] = float(comp.get('weight', 0))
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            if target_type == 'network':
                conditions = []
                for network in target_values:
                    prefix = '.'.join(network.split('.')[:2])
                    conditions.append(f"ip.address STARTS WITH '{prefix}.'")
                where_clause = " OR ".join(conditions)
                match_clause = f"""
                MATCH (subnet:Subnet)<-[:PART_OF]-(ip:IP)<-[:HAS_ASSIGNED]-(n:Node)
                WHERE {where_clause}
                """
            elif target_type == 'subnet':
                subnet_list = "', '".join(target_values)
                match_clause = f"""
                MATCH (subnet:Subnet)<-[:PART_OF]-(ip:IP)<-[:HAS_ASSIGNED]-(n:Node)
                WHERE subnet.range IN ['{subnet_list}']
                """
            elif target_type == 'ip':
                ip_list = "', '".join(target_values)
                match_clause = f"""
                MATCH (n:Node)-[:HAS_ASSIGNED]->(ip:IP)
                WHERE ip.address IN ['{ip_list}']
                """
            else:
                match_clause = "MATCH (n:Node)"
            
            calculation = build_calculation(components, formula_config, calculation_method, custom_formula)
            
            logger.info(f"Calculation: {calculation}")
            
            prop_name = f"`{target_property}`" if ' ' in target_property else target_property
            
            query = f"""
            {match_clause}
            WITH n, {calculation} AS rawScore
            SET n.{prop_name} = 
                CASE
                    WHEN rawScore < 0 THEN 0.0
                    WHEN rawScore > 10 THEN 10.0
                    ELSE rawScore
                END
            RETURN count(n) AS nodesUpdated,
                   round(avg(n.{prop_name}), 2) AS avgRiskScore
            """
            
            result = session.run(query)
            record = result.single()
            
            nodes_updated = record.get('nodesUpdated', 0) if record else 0
            avg_score = record.get('avgRiskScore') if record else None
            
            if avg_score is None or (isinstance(avg_score, float) and (avg_score != avg_score)):
                avg_score = 0.0
            else:
                avg_score = float(avg_score)
            
            if nodes_updated is None:
                nodes_updated = 0
        
        driver.close()
        
        config = load_config()
        if not config:
            config = {}
        
        automation_data = {
            'formula_name': formula_name,
            'formula_config': formula_config,
            'components': components,
            'target_type': target_type,
            'target_values': target_values,
            'calculation_mode': calculation_mode,
            'calculation_method': calculation_method,
            'custom_formula': custom_formula,
            'target_property': target_property,
            'update_frequency': update_frequency,
            'enabled': True,
            'created_date': datetime.now().isoformat(),
            'nodes_updated': nodes_updated,
            'avg_risk_score': avg_score
        }

        if update_frequency != 'manual':
            if 'active_automations' not in config:
                config['active_automations'] = {}
            
            automation_id = str(uuid.uuid4())[:8]
            config['active_automations'][automation_id] = automation_data
            logger.info(f"Saving automation {automation_id}")
        
        config['last_risk_calculation'] = {
            'formula_name': formula_name,
            'applied_to': f"{target_type}: {', '.join(map(str, target_values[:3]))}{'...' if len(target_values) > 3 else ''}",
            'nodes_updated': nodes_updated,
            'average_risk_score': avg_score,
            'timestamp': datetime.now().isoformat(),
            'update_frequency': update_frequency,
            'target_property': target_property,
            'calculation_mode': calculation_mode,
            'calculation_method': calculation_method,
            'custom_formula': custom_formula, 
            'components': {comp['name']: {'weight': comp.get('weight', 0), 'value': comp.get('currentValue', 0)} for comp in components}
        }
        
        if save_config(config):
            logger.info(f"Successfully saved automation to config")
        else:
            logger.error("Failed to save automation to config")
        
        if update_frequency != 'manual':
            schedule_data = {
                'automation_id': automation_id,
                'formula_name': formula_name,
                'update_frequency': update_frequency,
                'execution_endpoint': f"{os.getenv('RISK_API_URL', 'http://resilmesh-sap-isim-automation:5000')}/api/automations/execute/{automation_id}"
            }
            
            try:
                interval_map = {
                    'minute': timedelta(minutes=1),
                    'hourly': timedelta(hours=1),
                    'daily': timedelta(days=1),
                    'weekly': timedelta(weeks=1),
                    'monthly': timedelta(days=30)
                }
                
                interval = interval_map.get(update_frequency, timedelta(hours=1))
                schedule_id = f"automation-schedule-{automation_id}"
                
                async def create_automation_schedule():
                    client = await get_temporal_client()
                    
                    await client.create_schedule(
                        schedule_id,
                        Schedule(
                            action=ScheduleActionStartWorkflow(
                                "RiskFormulaCalculationWorkflow",
                                schedule_data,
                                id=f"risk-formula-calc-{automation_id}",
                                task_queue="risk-calculations",
                            ),
                            spec=ScheduleSpec(
                                intervals=[ScheduleIntervalSpec(every=interval)]
                            ),
                            state=ScheduleState(
                                note=f"{formula_name} - {update_frequency}",
                                paused=False
                            )
                        )
                    )
                    logger.info(f"Created Temporal schedule {schedule_id} with note: {formula_name}")
                
                asyncio.run(create_automation_schedule())
                logger.info(f"Temporal schedule created for automation {automation_id}")
                
            except Exception as e:
                logger.error(f"Failed to create Temporal schedule: {e}")
        
        return jsonify({
            'success': True,
            'nodesUpdated': nodes_updated,
            'avgRiskScore': avg_score,
            'automationEnabled': update_frequency != 'manual',
            'automation_id': automation_id if update_frequency != 'manual' else None
        })
        
    except Exception as e:
        logger.error(f"Error applying configuration: {e}")
        return jsonify({'error': str(e)}), 500
                         
def load_component_config() -> Optional[Dict[str, Any]]:
    """Load component automation configuration"""
    try:
        with open(COMPONENT_CONFIG_PATH, 'r') as file:
            config = yaml.safe_load(file)
            # If file exists but is empty/None, return default structure
            if config is None:
                return get_default_component_config()
            return config
    except FileNotFoundError:
        logger.info(f"Component config not found, creating new: {COMPONENT_CONFIG_PATH}")
        default_config = get_default_component_config()
        save_component_config(default_config)
        return default_config
    except yaml.YAMLError as e:
        logger.error(f"Error parsing component config: {e}")
        # IMPORTANT: Don't return empty dict on parse error!
        # Return None to indicate error without overwriting
        return None

def get_default_component_config():
    """Get default component configuration structure"""
    return {
        'active_component_automations': {},
        'component_automation_history': {
            'last_execution': {
                'timestamp': None,
                'components_updated': 0,
                'average_value': 0
            }
        }
    }

def save_component_config(config: Dict[str, Any]) -> bool:
    """Save component automation configuration with backup"""
    try:
        # Create backup before saving
        if os.path.exists(COMPONENT_CONFIG_PATH):
            backup_path = f"{COMPONENT_CONFIG_PATH}.backup"
            with open(COMPONENT_CONFIG_PATH, 'r') as src:
                with open(backup_path, 'w') as dst:
                    dst.write(src.read())
            logger.info(f"Created backup at {backup_path}")
        
        # Save the new config
        with open(COMPONENT_CONFIG_PATH, 'w') as file:
            yaml.dump(config, file, default_flow_style=False, indent=2, sort_keys=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"Error saving component config: {e}")
        # Try to restore from backup if save failed
        backup_path = f"{COMPONENT_CONFIG_PATH}.backup"
        if os.path.exists(backup_path):
            logger.info("Attempting to restore from backup...")
            try:
                with open(backup_path, 'r') as src:
                    with open(COMPONENT_CONFIG_PATH, 'w') as dst:
                        dst.write(src.read())
                logger.info("Restored from backup")
            except:
                logger.error("Failed to restore from backup")
        return False   
@app.route('/api/components/automation/save', methods=['POST'])
def save_component_automation():
    """Save component automation configuration"""
    try:
        data = request.get_json()
        
        component_name = data.get('componentName')
        component_id = data.get('componentId')
        data_source = data.get('dataSource', {})
        update_frequency = data.get('updateFrequency', 'manual')
        calculation_method = data.get('calculationMethod', 'query_result')
        duration_hours = data.get('durationHours')  # How long to run (optional)
        custom_query = data.get('customQuery')
        target_property = data.get('targetProperty', component_id)
        
        config = load_component_config()
        
        # Generate automation ID
        automation_id = f"comp_auto_{str(uuid.uuid4())[:8]}"
        
        # Calculate expiration if duration specified
        expires_at = None
        if duration_hours and duration_hours > 0:
            expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()
        
        # Build automation entry
        automation_data = {
            'component_name': component_name,
            'component_id': component_id,
            'data_source': {
                'type': data_source.get('type', 'neo4j_query'),
                'query': custom_query if custom_query else data_source.get('query')
            },
            'update_frequency': update_frequency,
            'calculation_method': calculation_method,
            'target_property': target_property,
            'enabled': True,
            'created_at': datetime.now().isoformat(),
            'last_run': None,
            'expires_at': expires_at
        }
        
        # Save to active automations
        if 'active_component_automations' not in config:
            config['active_component_automations'] = {}
        
        config['active_component_automations'][automation_id] = automation_data
        
        if save_component_config(config):
            logger.info(f"Saved component automation {automation_id} for {component_name}")
            return jsonify({
                'success': True,
                'automationId': automation_id,
                'message': f'Automation saved for {component_name}'
            })
        else:
            return jsonify({'error': 'Failed to save automation'}), 500
            
    except Exception as e:
        logger.error(f"Error saving component automation: {e}")
        return jsonify({'error': str(e)}), 500
   
@app.route('/api/components/automation/test', methods=['POST'])
def test_component_query():
    """Test a component automation query"""
    try:
        data = request.get_json()
        query = data.get('query')
        source_type = data.get('sourceType', 'neo4j_query')
        
        if source_type == 'neo4j_query' and query:
            # Security check
            query_upper = query.upper()
            destructive_keywords = [
                'DELETE', 'REMOVE', 'DROP', 'DETACH', 'DESTROY',
                'TRUNCATE', 'SET n = {}', 'CREATE INDEX', 'CREATE CONSTRAINT'
            ]
            
            for keyword in destructive_keywords:
                if keyword in query_upper:
                    return jsonify({
                        'success': False,
                        'message': f"Query cannot contain '{keyword}'. Only read operations are allowed for testing."
                    }), 400
            
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            
            with driver.session() as session:
                result = session.run(query)
                records = list(result)
                
                if records and 'value' in records[0]:
                    value = records[0]['value']
                    return jsonify({
                        'success': True,
                        'value': value,
                        'message': f'Query returned value: {value}'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Query must return a "value" field'
                    })
                    
            driver.close()
        else:
            return jsonify({'error': 'Invalid source type or missing query'}), 400
            
    except Exception as e:
        logger.error(f"Error testing component query: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/components/automation/<component_id>', methods=['GET'])
def get_component_automation(component_id):
    """Get automation configuration for a specific component"""
    try:
        # Load component automation config
        config = load_component_config()
        if not config:
            return jsonify({"error": "Configuration file not found"}), 404
        
        # Search for automation matching this component
        automations = config.get('active_component_automations', {})
        
        for auto_id, automation in automations.items():
            if automation.get('component_id') == component_id or \
               automation.get('target_property') == component_id:
                return jsonify({
                    "automation_id": auto_id,
                    "automation": automation
                })
        
        # If no specific automation, check available components for defaults
        available = config.get('available_components', {})
        if component_id in available:
            component_data = available[component_id]
            # Return default configuration based on component type
            default_config = {
                "component_id": component_id,
                "component_name": component_data.get('name'),
                "data_source": {
                    "type": "neo4j_query",
                    "query": f"MATCH (n:Node) RETURN avg(n.{component_id}) as value"
                },
                "update_frequency": "hourly",
                "calculation_method": "query_result",
                "target_property": component_id
            }
            return jsonify({"automation": default_config})
        
        return jsonify({"message": "No automation configured"}), 404
        
    except Exception as e:
        logger.error(f"Error fetching automation config: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/components/<int:component_id>/apply-automation', methods=['POST'])
def apply_component_automation(component_id):
    """Apply automation configuration to a component"""
    try:
        data = request.get_json()
        automation_id = data.get('automation_id')
        
        # Load configurations
        config = load_component_config()
        risk_config = load_config()
        
        if not config or not risk_config:
            return jsonify({"error": "Configuration files not found"}), 404
        
        # Get the automation
        automations = config.get('active_component_automations', {})
        automation = automations.get(automation_id)
        
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        # Execute the automation logic
        result = execute_automation_logic(automation)
        
        # Update last run time
        automation['last_run'] = datetime.now().isoformat()
        config['active_component_automations'][automation_id] = automation
        save_component_config(config)
        
        return jsonify({
            "status": "success",
            "automation_id": automation_id,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Error applying automation: {e}")
        return jsonify({"error": str(e)}), 500

def execute_automation_logic(automation):
    """Execute the actual automation logic based on data source"""
    data_source = automation.get('data_source', {})
    source_type = data_source.get('type')
    
    if source_type == 'neo4j_query':
        # Execute Neo4j query
        query = data_source.get('query')
        if query:
            try:
                driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                with driver.session() as session:
                    result = session.run(query)
                    value = result.single()['value'] if result else 0
                driver.close()
                return {"value": value, "source": "neo4j"}
            except Exception as e:
                logger.error(f"Neo4j query failed: {e}")
                return {"error": str(e)}
    
    elif source_type == 'static_value':
        return {"value": data_source.get('value', 0), "source": "static"}
    
    elif source_type == 'calculation':
        # Execute calculation logic
        formula = data_source.get('formula', '')
        # Add calculation logic here
        return {"value": 0, "source": "calculation"}
    
    return {"value": 0, "source": "unknown"}

@app.route('/api/components/automations/list', methods=['GET'])
def list_component_automations():
    """List all available automations"""
    try:
        config = load_component_config()
        if not config:
            return jsonify({"automations": []})
        
        automations = config.get('active_component_automations', {})
        automation_list = []
        
        for auto_id, automation in automations.items():
            automation_list.append({
                "id": auto_id,
                "name": automation.get('component_name'),
                "frequency": automation.get('update_frequency'),
                "enabled": automation.get('enabled', False),
                "last_run": automation.get('last_run')
            })
        
        return jsonify({"automations": automation_list})
        
    except Exception as e:
        logger.error(f"Error listing automations: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/components/automation/active', methods=['GET'])
def get_active_component_automations():
    """Get all active component automations"""
    try:
        config = load_component_config()
        automations = config.get('active_component_automations', {})
        
        # Filter out expired automations
        active = {}
        now = datetime.now()
        
        for auto_id, auto_data in automations.items():
            if auto_data.get('expires_at'):
                expires = datetime.fromisoformat(auto_data['expires_at'])
                if expires < now:
                    continue  # Skip expired
            active[auto_id] = auto_data
        
        return jsonify({
            'success': True,
            'automations': active
        })
    except Exception as e:
        logger.error(f"Error getting component automations: {e}")
        return jsonify({'error': str(e)}), 500
 
@app.route('/api/components/automation/<automation_id>/pause', methods=['PUT'])
def pause_risk_automation(automation_id):
    """Pause a risk formula automation"""
    try:
        config = load_config()  # Main config
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'error': 'Automation not found'}), 404
        
        automations[automation_id]['enabled'] = False
        
        if save_config(config):  # Save main config
            logger.info(f"Paused risk automation {automation_id}")
            return jsonify({'success': True, 'message': 'Automation paused'})
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error pausing risk automation: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/components/automation/<automation_id>/resume', methods=['PUT'])
def resume_risk_automation(automation_id):
    """Resume a risk formula automation"""
    try:
        config = load_config()  # Main config
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'error': 'Automation not found'}), 404
        
        automations[automation_id]['enabled'] = True
        
        if save_config(config):  # Save main config
            logger.info(f"Resumed risk automation {automation_id}")
            return jsonify({'success': True, 'message': 'Automation resumed'})
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error resuming risk automation: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/risk/automations/active', methods=['GET'])
def get_active_risk_formula_automations():
    """Get all active risk formula automations for the UI"""
    try:
        config = load_config()
        if not config:
            return jsonify({'error': 'Config file not found'}), 500
            
        automations = config.get('active_automations', {})
        
        # Transform for frontend consumption
        transformed_automations = {}
        for auto_id, automation in automations.items():
            transformed_automations[auto_id] = {
                **automation,
                'componentName': automation.get('formula_name', 'Unknown Formula'),
                'component_name': automation.get('formula_name', 'Unknown Formula'),
                'enabled': automation.get('enabled', True)  # Default to enabled if not specified
            }
        
        return jsonify({
            'success': True,
            'automations': transformed_automations
        })
    except Exception as e:
        logger.error(f"Error getting risk formula automations: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/components/automation/<automation_id>', methods=['DELETE'])
def delete_risk_automation(automation_id):
    """Delete a risk formula automation"""
    try:
        config = load_config()  # Main config
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'error': 'Automation not found'}), 404
        
        automation_name = automations[automation_id].get('formula_name', automation_id)  # Use formula_name
        del automations[automation_id]
        
        if save_config(config):  # Save main config
            logger.info(f"Deleted risk automation {automation_id}")
            return jsonify({'success': True, 'message': f'Risk automation {automation_name} deleted'})
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting risk automation: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/components/automation/<automation_id>/workflow', methods=['GET'])
def get_automation_workflow(automation_id):
    """Get automation workflow configuration"""
    try:
        config = load_config()
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'error': 'Automation not found'}), 404
        
        automation = automations[automation_id]
        
        # Return workflow structure
        workflow = {
            'components': automation.get('components', []),
            'formula': automation.get('custom_formula', ''),
            'calculation_method': automation.get('calculation_method', 'weighted_avg')
        }
        
        return jsonify({
            'success': True,
            'workflow': workflow
        })
        
    except Exception as e:
        logger.error(f"Error getting automation workflow: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/components/automation/<automation_id>/workflow', methods=['PUT'])
def update_automation_workflow(automation_id):
    """Update automation workflow configuration"""
    try:
        data = request.get_json()
        config = load_config()
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'error': 'Automation not found'}), 404
        
        # Update the automation with workflow data
        automations[automation_id]['components'] = data.get('components', [])
        automations[automation_id]['custom_formula'] = data.get('formula', '')
        
        if save_config(config):
            return jsonify({'success': True, 'message': 'Workflow updated'})
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error updating automation workflow: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/components/automation/<automation_id>', methods=['PUT'])
def update_automation_configuration(automation_id):
    """Update general automation configuration"""
    try:
        data = request.get_json()
        config = load_config()
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'error': 'Automation not found'}), 404
        
        # Update automation properties
        for key, value in data.items():
            if key in ['enabled', 'components', 'formula', 'update_frequency']:
                automations[automation_id][key] = value
        
        if save_config(config):
            return jsonify({'success': True, 'message': 'Automation updated'})
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
            
    except Exception as e:
        logger.error(f"Error updating automation: {e}")
        return jsonify({'error': str(e)}), 500
    
    # Temporal scheduling endpoints
async def get_temporal_client():
    """Connect to Temporal server"""
    return await Client.connect(TEMPORAL_URL)

@app.route('/api/components/schedule/start', methods=['POST'])
def start_component_schedule():
    """Start a Temporal schedule for component calculation"""
    try:
        data = request.get_json()
        component_id = data.get('component_id')
        update_frequency = data.get('update_frequency', 'hourly')
        
        if not component_id:
            return jsonify({'success': False, 'error': 'component_id required'}), 400
        
        schedule_id = f"component-schedule-{component_id}"
        
        interval_map = {
            'minute': timedelta(minutes=1),
            'hourly': timedelta(hours=1),
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'monthly': timedelta(days=30)
        }
        
        interval = interval_map.get(update_frequency, timedelta(hours=1))
        
        # Prepare workflow input with execution endpoint
        workflow_input = {
            'component_id': component_id,
            'component_name': data.get('component_name'),
            'neo4j_property': data.get('neo4j_property'),
            'execution_endpoint': f"{os.getenv('RISK_API_URL', 'http://resilmesh-sap-isim-automation:5000')}/api/components/execute/{component_id}",
            'update_frequency': update_frequency
        }
        
        async def create_schedule():
            client = await get_temporal_client()
            
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        "ComponentCalculationWorkflow",
                        workflow_input,  # Pass the workflow input with execution endpoint
                        id=f"component-calc-{component_id}",
                        task_queue="component-calculations",
                    ),
                    spec=ScheduleSpec(
                        intervals=[ScheduleIntervalSpec(every=interval)]
                    ),
                    state=ScheduleState(
                        note=f"Component {component_id} calculation",
                        paused=False
                    )
                )
            )
            logger.info(f"Created Temporal schedule {schedule_id} with execution endpoint")
        
        asyncio.run(create_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Temporal schedule created for component {component_id}',
            'schedule_id': schedule_id,
            'frequency': update_frequency
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to start component schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/risk/components/schedule/pause', methods=['POST'])
def pause_component_schedule():
    """Pause a Temporal schedule"""
    try:
        data = request.get_json()
        component_id = data.get('component_id')
        schedule_id = f"component-schedule-{component_id}"
        
        async def pause_schedule():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            await handle.pause(note="Paused by user")
        
        asyncio.run(pause_schedule())
        logger.info(f"Paused Temporal schedule {schedule_id}")
        
        return jsonify({'success': True, 'message': f'Paused schedule for {component_id}'}), 200
        
    except Exception as e:
        logger.error(f"Failed to pause schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/risk/components/schedule/resume', methods=['POST'])
def resume_component_schedule():
    """Resume a paused Temporal schedule"""
    try:
        data = request.get_json()
        component_id = data.get('component_id')
        schedule_id = f"component-schedule-{component_id}"
        
        async def resume_schedule():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            await handle.unpause(note="Resumed by user")
        
        asyncio.run(resume_schedule())
        logger.info(f"Resumed Temporal schedule {schedule_id}")
        
        return jsonify({'success': True, 'message': f'Resumed schedule for {component_id}'}), 200
        
    except Exception as e:
        logger.error(f"Failed to resume schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/components/schedule/delete/<component_id>', methods=['DELETE'])
def delete_component_schedule(component_id):
    """Delete a Temporal schedule"""
    try:
        schedule_id = f"component-schedule-{component_id}"
        
        async def delete_schedule():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            await handle.delete()
            logger.info(f"Deleted schedule {schedule_id}")
        
        asyncio.run(delete_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Schedule {schedule_id} deleted successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to delete schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/components/schedule/update/<component_id>', methods=['PUT'])
def update_component_schedule(component_id):
    """Update Temporal schedule frequency for component"""
    try:
        data = request.get_json()
        new_frequency = data.get('update_frequency', 'hourly')
        schedule_id = f"component-schedule-{component_id}"
        
        async def update_schedule():
            client = await get_temporal_client()
            
            try:
                handle = client.get_schedule_handle(schedule_id)
                await handle.delete()
                logger.info(f"Deleted old schedule {schedule_id}")
            except:
                logger.info(f"No existing schedule to delete: {schedule_id}")
            
            interval_map = {
                'minute': timedelta(minutes=1),
                'hourly': timedelta(hours=1),
                'daily': timedelta(days=1),
                'weekly': timedelta(weeks=1),
                'monthly': timedelta(days=30)
            }
            
            interval = interval_map.get(new_frequency, timedelta(hours=1))
            
            workflow_input = {
                'component_id': component_id,
                'component_name': data.get('component_name'),
                'neo4j_property': data.get('neo4j_property'),
                'execution_endpoint': f"{os.getenv('RISK_API_URL', 'http://resilmesh-sap-isim-automation:5000')}/api/components/execute/{component_id}",
                'update_frequency': new_frequency
            }
            
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        "ComponentCalculationWorkflow",
                        workflow_input,
                        id=f"component-calc-{component_id}",
                        task_queue="component-calculations",
                    ),
                    spec=ScheduleSpec(
                        intervals=[ScheduleIntervalSpec(every=interval)]
                    ),
                    state=ScheduleState(
                        note=f"Updated component {component_id}",
                        paused=False
                    )
                )
            )
            logger.info(f"Created new schedule {schedule_id} with {new_frequency}")
        
        asyncio.run(update_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Schedule updated for component {component_id}',
            'frequency': new_frequency
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to update schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/components/schedule/status/<component_id>', methods=['GET'])
def get_component_schedule_status(component_id):
    """Get status of component Temporal schedule"""
    try:
        schedule_id = f"component-schedule-{component_id}"
        
        async def get_status():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            description = await handle.describe()
            
            is_paused = description.schedule.state.paused
            
            # Extract frequency from interval
            interval = description.schedule.spec.intervals[0].every if description.schedule.spec.intervals else None
            frequency = 'unknown'
            if interval:
                total_seconds = interval.total_seconds()
                if total_seconds == 60:
                    frequency = 'minute'
                elif total_seconds == 3600:
                    frequency = 'hourly'
                elif total_seconds == 86400:
                    frequency = 'daily'
                elif total_seconds == 604800:
                    frequency = 'weekly'
                elif total_seconds >= 2592000:
                    frequency = 'monthly'
            
            return {
                'success': True,
                'exists': True,
                'schedule_id': schedule_id,
                'paused': is_paused,
                'running': not is_paused,
                'frequency': frequency,
                'next_run': str(description.info.next_action_times[0]) if description.info.next_action_times else None,
                'note': description.schedule.state.note
            }
        
        result = asyncio.run(get_status())
        logger.info(f"Schedule status for {component_id}: {result}")
        return jsonify(result), 200
        
    except Exception as e:
        logger.warning(f"Schedule not found: {schedule_id} - {str(e)}")
        return jsonify({
            'success': True,
            'exists': False,
            'running': False,
            'paused': True
        }), 200
           
@app.route('/api/risk/components/schedule/trigger', methods=['POST'])
def trigger_component_now():
    """Trigger immediate execution of a Temporal schedule"""
    try:
        data = request.get_json()
        component_id = data.get('component_id')
        schedule_id = f"component-schedule-{component_id}"
        
        async def trigger_schedule():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            await handle.trigger()
        
        asyncio.run(trigger_schedule())
        logger.info(f"Triggered immediate execution for {schedule_id}")
        
        return jsonify({'success': True, 'message': f'Triggered execution for {component_id}'}), 200
        
    except Exception as e:
        logger.error(f"Failed to trigger schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/risk/components/schedules/list', methods=['GET'])
def list_all_component_schedules():
    """List all Temporal component schedules"""
    try:
        async def list_schedules():
            client = await get_temporal_client()
            schedules = []
            
            async for schedule in client.list_schedules():
                if schedule.id.startswith('component-schedule-'):
                    component_id = schedule.id.replace('component-schedule-', '')
                    schedules.append({
                        'component_id': component_id,
                        'schedule_id': schedule.id,
                        'paused': schedule.info.paused
                    })
            
            return schedules
        
        schedules = asyncio.run(list_schedules())
        return jsonify({'success': True, 'schedules': schedules}), 200
        
    except Exception as e:
        logger.error(f"Failed to list schedules: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/components/execute/criticality', methods=['POST'])
def execute_criticality_calculation():
    """Execute full ISIM calculations (betweenness, degree, normalize, criticality, cvss, risk score)"""
    try:
        logger.info("Executing full ISIM calculation pipeline")
        
        import subprocess
        import sys
        
        result = subprocess.run(
            [sys.executable, '/app/isim_calcs.py'],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            logger.error(f"ISIM calculations failed: {result.stderr}")
            return jsonify({
                'success': False,
                'error': f'ISIM calculations failed: {result.stderr}'
            }), 500
        
        logger.info("ISIM calculations completed successfully")
        
        with neo4j_driver.session() as session:
            stats_query = """
            MATCH (n:Node)
            WHERE n.criticality IS NOT NULL
            RETURN 
                count(n) AS nodesUpdated,
                round(avg(n.criticality), 2) AS avgCriticality,
                round(max(n.criticality), 2) AS maxCriticality,
                round(min(n.criticality), 2) AS minCriticality
            """
            
            result = session.run(stats_query)
            record = result.single()
            
            nodes_updated = record['nodesUpdated'] if record else 0
            avg_criticality = record['avgCriticality'] if record else 0
        
        logger.info(f"Criticality calculation complete: {nodes_updated} nodes updated, avg: {avg_criticality}")
        
        return jsonify({
            'success': True,
            'component': 'criticality',
            'nodes_updated': nodes_updated,
            'avg_value': float(avg_criticality) if avg_criticality else 0
        }), 200
        
    except subprocess.TimeoutExpired:
        logger.error("ISIM calculations timed out after 5 minutes")
        return jsonify({'success': False, 'error': 'Calculation timeout'}), 500
    except Exception as e:
        logger.error(f"Criticality calculation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/components/execute/cvss_score', methods=['POST'])
def execute_cvss_calculation():
    """Execute CVSS score calculation - queries existing CVE data"""
    try:
        logger.info("Executing CVSS score calculation")

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
        
        with neo4j_driver.session() as session:
            result = session.run(set_cvss_query)
            record = result.single()
            
            nodes_updated = record['nodesUpdated'] if record else 0
            avg_cvss = record['globalAverageCvss'] if record else 0
        
        logger.info(f"CVSS calculation complete: {nodes_updated} nodes updated")
        
        return jsonify({
            'success': True,
            'component': 'cvss_score',
            'nodes_updated': nodes_updated,
            'avg_value': float(avg_cvss) if avg_cvss else 0
        }), 200
        
    except Exception as e:
        logger.error(f"CVSS calculation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/components/execute/threatScore', methods=['POST'])
def execute_threat_calculation():
    """Execute threat score calculation by running threat_calcs.py"""
    try:
        logger.info("Executing threat score calculation")
        
        import subprocess
        import sys
        
        result = subprocess.run(
            [sys.executable, '/app/threat_calcs.py'],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            logger.info("Threat calculation completed successfully")
            
            count_query = """
            MATCH (n:Node)
            WHERE n.threatScore IS NOT NULL
            RETURN count(n) AS nodesUpdated,
                   round(avg(n.threatScore), 2) AS avgThreatScore
            """
            
            with neo4j_driver.session() as session:
                record = session.run(count_query).single()
                nodes_updated = record['nodesUpdated'] if record else 0
                avg_threat = record['avgThreatScore'] if record else 0
            
            return jsonify({
                'success': True,
                'component': 'threatScore',
                'nodes_updated': nodes_updated,
                'avg_value': float(avg_threat) if avg_threat else 0
            }), 200
        else:
            logger.error(f"Threat calculation failed: {result.stderr}")
            return jsonify({
                'success': False,
                'error': result.stderr
            }), 500
            
    except subprocess.TimeoutExpired:
        logger.error("Threat calculation timed out")
        return jsonify({'success': False, 'error': 'Calculation timed out'}), 500
    except Exception as e:
        logger.error(f"Threat calculation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/components/execute/<component_id>', methods=['POST'])
def execute_component_calculation(component_id):
    """Execute calculation for a specific component"""
    try:
        logger.info(f"Executing calculation for component: {component_id}")
        
        # Map component IDs to their execution functions
        execution_map = {
            'criticality': execute_criticality_calculation,
            'cvss_score': execute_cvss_calculation,
            'threatScore': execute_threat_calculation
        }
        
        if component_id in execution_map:
            # Call the appropriate execution function
            return execution_map[component_id]()
        else:
            # For custom components, just return success
            logger.info(f"No specific calculation for {component_id}")
            return jsonify({
                'success': True,
                'component': component_id,
                'message': 'Component has no automatic calculation'
            }), 200
            
    except Exception as e:
        logger.error(f"Component execution failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

#Temporal Risk Formula scheduling
@app.route('/api/automations/schedule/start', methods=['POST'])
def start_automation_schedule():
    """Start a Temporal schedule for a risk formula automation"""
    try:
        data = request.get_json()
        automation_id = data.get('automation_id')
        update_frequency = data.get('update_frequency', 'hourly')
        
        if not automation_id:
            return jsonify({'success': False, 'error': 'automation_id required'}), 400
        
        schedule_id = f"automation-schedule-{automation_id}"
        
        interval_map = {
            'minute': timedelta(minutes=1),
            'hourly': timedelta(hours=1),
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'monthly': timedelta(days=30)
        }
        
        interval = interval_map.get(update_frequency, timedelta(hours=1))
        
        async def create_schedule():
            client = await get_temporal_client()
            
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        "RiskFormulaCalculationWorkflow",
                        data,
                        id=f"risk-formula-calc-{automation_id}",
                        task_queue="risk-calculations",
                    ),
                    spec=ScheduleSpec(
                        intervals=[ScheduleIntervalSpec(every=interval)]
                    ),
                    state=ScheduleState(
                        note=f"{formula_name} - {update_frequency}",
                        paused=False
                    )
                )
            )
            logger.info(f"Created Temporal schedule {schedule_id}")
        
        asyncio.run(create_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Temporal schedule created for automation {automation_id}',
            'schedule_id': schedule_id,
            'frequency': update_frequency
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to start automation schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automations/execute/<automation_id>', methods=['POST'])
def execute_automation_endpoint(automation_id):
    """Execute a risk formula automation - called by Temporal or manual trigger"""
    try:
        config = load_config()
        if not config:
            return jsonify({'success': False, 'error': 'Config file not found'}), 500
            
        automations = config.get('active_automations', {})
        
        if automation_id not in automations:
            return jsonify({'success': False, 'error': 'Automation not found'}), 404
        
        automation = automations[automation_id]
        
        if not automation.get('enabled', True):
            return jsonify({'success': False, 'error': 'Automation is paused'}), 400
        
        logger.info(f"Executing automation {automation_id}: {automation.get('formula_name')}")
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        try:
            with driver.session() as session:
                components = automation.get('components', [])
                formula_config = automation.get('formula_config', {})
                target_type = automation.get('target_type', 'all')
                target_values = automation.get('target_values', [])
                target_property = automation.get('target_property', 'Risk Score')
                
                calculation_method = automation.get('calculation_method', 'weighted_avg')
                custom_formula = automation.get('custom_formula', '')
                
                logger.info(f"Using calculation method: {calculation_method}")
                logger.info(f"Target property: '{target_property}'")
                
                calculation = build_calculation(components, formula_config, calculation_method, custom_formula)
                
                if ' ' in target_property or '-' in target_property:
                    formatted_property = f"`{target_property}`"
                else:
                    formatted_property = target_property
                
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
                elif target_type == 'network':
                    conditions = []
                    for network in target_values:
                        prefix = '.'.join(network.split('.')[:2])
                        conditions.append(f"ip.address STARTS WITH '{prefix}.'")
                    where_clause = ' OR '.join(conditions)
                    query = f"""
                    MATCH (n:Node)-[:HAS_ASSIGNED]->(ip:IP)
                    WHERE {where_clause}
                    SET n.{formatted_property} = {calculation}
                    RETURN count(n) as nodes_updated, avg(n.{formatted_property}) as avg_risk
                    """
                else:
                    query = f"""
                    MATCH (n:Node)
                    SET n.{formatted_property} = {calculation}
                    RETURN count(n) as nodes_updated, avg(n.{formatted_property}) as avg_risk
                    """
                
                logger.info(f"Executing query: {query}")
                result = session.run(query)
                record = result.single()
                
                if record:
                    nodes_updated = record['nodes_updated']
                    avg_risk = record['avg_risk'] if record['avg_risk'] is not None else 0
                    
                    automation['last_run'] = datetime.now().isoformat()
                    automation['nodes_updated'] = nodes_updated
                    automation['avg_risk_score'] = round(avg_risk, 2)
                    
                    if save_config(config):
                        logger.info(f"Updated {nodes_updated} nodes. Average {target_property}: {avg_risk}")
                    
                    return jsonify({
                        'success': True,
                        'automation_id': automation_id,
                        'nodes_updated': nodes_updated,
                        'avg_risk_score': round(avg_risk, 2),
                        'target_property': target_property,
                        'message': f'Successfully updated {nodes_updated} nodes'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'error': 'No results returned from query'
                    }), 500
                    
        except Exception as e:
            logger.error(f"Error executing automation query: {e}")
            return jsonify({
                'success': False,
                'error': f'Query execution failed: {str(e)}'
            }), 500
        finally:
            driver.close()
            
    except Exception as e:
        logger.error(f"Error executing automation {automation_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/automations/execute/base-risk', methods=['POST'])
def execute_base_risk_automation():
    """Execute base risk calculation - hardcoded 3-component formula"""
    try:
        logger.info("Executing base-risk automation")
        
        target_property = "Risk Score"
        
        calculation = """
        (
            (COALESCE(n.criticality, 0.0) * 0.333) +
            (COALESCE(n.cvss_score, 0.0) * 0.333) +
            (COALESCE(n.threatScore, 0.0) * 0.333)
        ) / 1.0
        """
        
        query = f"""
        MATCH (n:Node)
        SET n.`{target_property}` = {calculation}
        RETURN count(n) as nodes_updated, 
               avg(n.`{target_property}`) as avg_risk
        """
        
        with neo4j_driver.session() as session:
            result = session.run(query)
            record = result.single()
            
            nodes_updated = record['nodes_updated'] if record else 0
            avg_risk = record['avg_risk'] if record and record['avg_risk'] is not None else 0
        
        logger.info(f"Base-risk calculation complete: {nodes_updated} nodes updated, avg: {avg_risk}")
        
        return jsonify({
            'success': True,
            'automation_id': 'base-risk',
            'nodes_updated': nodes_updated,
            'avg_risk_score': round(avg_risk, 2),
            'target_property': target_property,
            'message': f'Successfully updated {nodes_updated} nodes'
        }), 200
        
    except Exception as e:
        logger.error(f"Base-risk calculation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automations/schedule/pause/<automation_id>', methods=['POST'])
def pause_automation_schedule(automation_id):
    """Pause a Temporal schedule for risk formula automation"""
    try:
        schedule_id = f"automation-schedule-{automation_id}"
        
        async def pause_schedule():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            await handle.pause()
            logger.info(f"Paused schedule {schedule_id}")
        
        asyncio.run(pause_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Schedule paused for automation {automation_id}'
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to pause schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automations/schedule/resume/<automation_id>', methods=['POST'])
def resume_automation_schedule(automation_id):
    """Resume a Temporal schedule for risk formula automation"""
    try:
        schedule_id = f"automation-schedule-{automation_id}"
        
        async def resume_schedule():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            await handle.unpause()
            logger.info(f"Resumed schedule {schedule_id}")
        
        asyncio.run(resume_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Schedule resumed for automation {automation_id}'
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to resume schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automations/schedule/status/<automation_id>', methods=['GET'])
def get_automation_schedule_status(automation_id):
    """Get Temporal schedule status for automation"""
    try:
        schedule_id = f"automation-schedule-{automation_id}"
        
        async def get_status():
            client = await get_temporal_client()
            handle = client.get_schedule_handle(schedule_id)
            description = await handle.describe()
            
            is_paused = description.schedule.state.paused
            
            # Extract frequency from interval
            interval = description.schedule.spec.intervals[0].every if description.schedule.spec.intervals else None
            frequency = 'unknown'
            if interval:
                total_seconds = interval.total_seconds()
                if total_seconds == 60:
                    frequency = 'minute'
                elif total_seconds == 3600:
                    frequency = 'hourly'
                elif total_seconds == 86400:
                    frequency = 'daily'
                elif total_seconds == 604800:
                    frequency = 'weekly'
                elif total_seconds >= 2592000:
                    frequency = 'monthly'
            
            return {
                'success': True,
                'exists': True,
                'running': not is_paused,
                'paused': is_paused,
                'frequency': frequency,
                'next_run': str(description.info.next_action_times[0]) if description.info.next_action_times else None
            }
        
        result = asyncio.run(get_status())
        return jsonify(result), 200
        
    except Exception as e:
        logger.warning(f"Schedule not found: {schedule_id}")
        return jsonify({
            'success': True,
            'exists': False,
            'running': False
        }), 200

@app.route('/api/automations/schedule/update/<automation_id>', methods=['PUT'])
def update_automation_schedule(automation_id):
    """Update Temporal schedule frequency for automation"""
    try:
        data = request.get_json()
        new_frequency = data.get('update_frequency', 'hourly')
        schedule_id = f"automation-schedule-{automation_id}"
        
        async def update_schedule():
            client = await get_temporal_client()
            
            try:
                handle = client.get_schedule_handle(schedule_id)
                await handle.delete()
                logger.info(f"Deleted old schedule {schedule_id}")
            except:
                logger.info(f"No existing schedule to delete: {schedule_id}")
            
            interval_map = {
                'minute': timedelta(minutes=1),
                'hourly': timedelta(hours=1),
                'daily': timedelta(days=1),
                'weekly': timedelta(weeks=1),
                'monthly': timedelta(days=30)
            }
            
            interval = interval_map.get(new_frequency, timedelta(hours=1))
            
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        "RiskFormulaCalculationWorkflow",
                        data,
                        id=f"risk-formula-calc-{automation_id}",
                        task_queue="risk-calculations",
                    ),
                    spec=ScheduleSpec(
                        intervals=[ScheduleIntervalSpec(every=interval)]
                    ),
                    state=ScheduleState(
                        note=f"Updated automation {automation_id}",
                        paused=False
                    )
                )
            )
            logger.info(f"Created new schedule {schedule_id} with {new_frequency}")
        
        asyncio.run(update_schedule())
        
        return jsonify({
            'success': True,
            'message': f'Schedule updated for automation {automation_id}',
            'frequency': new_frequency
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to update schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automations/schedule/delete/<automation_id>', methods=['DELETE'])
def delete_automation_schedule(automation_id):
    try:
        schedule_id = f"automation-schedule-{automation_id}"
        logger.info(f"Attempting to delete Temporal automation schedule: {schedule_id}")
        
        async def delete_schedule():
            try:
                client = await get_temporal_client()
                logger.info(f"Connected to Temporal at {TEMPORAL_URL}")
                
                handle = client.get_schedule_handle(schedule_id)
                logger.info(f"Got handle for schedule {schedule_id}")
                
                await handle.delete()
                logger.info(f"Successfully deleted schedule {schedule_id}")
                return {'deleted': True, 'message': 'Schedule deleted successfully'}
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error deleting schedule {schedule_id}: {error_msg}")
                
                if 'not found' in error_msg.lower() or 'no rows' in error_msg.lower():
                    return {'deleted': False, 'message': 'Schedule not found', 'warning': error_msg}
                else:
                    raise e
        
        result = asyncio.run(delete_schedule())
        
        return jsonify({
            'success': True,
            'schedule_id': schedule_id,
            **result
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to delete automation schedule {automation_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'schedule_id': f"automation-schedule-{automation_id}"
        }), 500

@app.route('/api/components/scan-neo4j', methods=['GET'])
def scan_neo4j_for_components():
    """Scan Neo4j nodes for custom properties not in config"""
    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            exclude = [
                'name','id','Risk Score','threatScore','cvss_score','criticality',
                'betweenness', 'degree', 'normalizedBetweeness', 'normalizedDegree',
                'topology_betweenness', 'topology_degree'
            ]

            query = """
            MATCH (n:Node)
            WITH keys(n) AS properties
            UNWIND properties AS prop
            WITH DISTINCT prop, $exclude AS exclude
            WHERE NOT (prop IN exclude)
            RETURN collect(DISTINCT prop) AS customProperties
            """

            result = session.run(query, exclude=exclude)
            record = result.single()
            custom_properties = record["customProperties"] if record else []

            
            # Load current config
            config = load_config()
            if not config:
                config = {'available_components': {}}
            
            existing_components = config.get('available_components', {})
            existing_neo4j_props = set()
            
            # Collect existing neo4j properties
            for comp_key, comp_data in existing_components.items():
                if comp_data.get('neo4jProperty'):
                    existing_neo4j_props.add(comp_data['neo4jProperty'])
            
            # Find new properties not in config
            new_properties = []
            for prop in custom_properties:
                if prop not in existing_neo4j_props:
                    # Get sample value and count
                    sample_query = f"""
                    MATCH (n:Node)
                    WHERE n.`{prop}` IS NOT NULL
                    RETURN count(n) as nodeCount, 
                           avg(n.`{prop}`) as avgValue,
                           min(n.`{prop}`) as minValue,
                           max(n.`{prop}`) as maxValue
                    """
                    
                    sample_result = session.run(sample_query)
                    sample_record = sample_result.single()
                    
                    if sample_record and sample_record["nodeCount"] > 0:
                        new_properties.append({
                            'neo4jProperty': prop,
                            'name': prop.replace('_', ' ').title(),
                            'nodeCount': sample_record["nodeCount"],
                            'avgValue': float(sample_record["avgValue"] or 0),
                            'minValue': float(sample_record["minValue"] or 0),
                            'maxValue': float(sample_record["maxValue"] or 100)
                        })
            
            return jsonify({
                "success": True,
                "newProperties": new_properties,
                "existingProperties": list(existing_neo4j_props),
                "totalCustomProperties": len(custom_properties)
            })
            
    except Exception as e:
        logger.error(f"Error scanning Neo4j: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if driver:
            driver.close()

@app.route('/api/components/import-from-neo4j', methods=['POST'])
def import_components_from_neo4j():
    """Import discovered Neo4j properties as components"""
    try:
        data = request.json
        properties_to_import = data.get('properties', [])
        
        config = load_config()
        if not config:
            config = {'available_components': {}}
        
        if 'available_components' not in config:
            config['available_components'] = {}
        
        imported_count = 0
        
        for prop_data in properties_to_import:
            neo4j_property = prop_data.get('neo4jProperty')
            if not neo4j_property:
                continue
            
            component_key = f"custom_{neo4j_property.replace(' ', '_').replace('-', '_').lower()}"
            
            config['available_components'][component_key] = {
                'id': component_key,
                'name': prop_data.get('name', neo4j_property.replace('_', ' ').title()),
                'neo4jProperty': neo4j_property,
                'neo4j_property': neo4j_property,
                'weight': 0,
                'currentValue': float(prop_data.get('avgValue', 0)),
                'maxValue': float(prop_data.get('maxValue', 10)),
                'type': 'custom',
                'icon': '🔧',
                'description': f'Imported from ISIM: {neo4j_property}',
                'isComposite': False,
                'source': 'neo4j_import',
                'imported_at': datetime.now().isoformat(),
                'statistics': {
                    'avg': float(prop_data.get('avgValue', 0)),
                    'max': float(prop_data.get('maxValue', 0)),
                    'min': float(prop_data.get('minValue', 0)),
                    'nodeCount': int(prop_data.get('nodeCount', 0))
                }
            }
            
            imported_count += 1
            logger.info(f"Imported component: {component_key} with Neo4j property: {neo4j_property}")
        
        if save_config(config):
            return jsonify({
                "success": True,
                "message": f"Imported {imported_count} components from Neo4j",
                "importedCount": imported_count
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
            
    except Exception as e:
        logger.error(f"Error importing components: {e}")
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    #Start Flask API
    logger.info("Starting Risk Assessment API on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
