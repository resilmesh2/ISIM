#!/usr/bin/env python3
# type: ignore
"""
Risk Assessment API for Angular integration
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import yaml
import logging
from datetime import datetime
import uuid
from typing import Dict, Any, Optional, List
import threading
import time
import subprocess
import json
from neo4j import GraphDatabase
import os

app = Flask(__name__)
CORS(app, 
     origins=['http://localhost:4200', 'http://localhost:3000', '*'],  # Angular dev server + Node.js
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization'],
     supports_credentials=True)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config file path
CONFIG_PATH = "/config/risk_assessment_config.yaml"

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
    """Save a custom component to config file"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required_fields = ['name', 'type', 'maxValue']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        config = load_config()
        if not config:
            return jsonify({"error": "Config file not found"}), 500
        
        # Create component key from name
        component_key = data['name'].lower().replace(' ', '_').replace('-', '_')
        component_key = ''.join(c for c in component_key if c.isalnum() or c == '_')
        
        # Create component in YAML format
        new_component = {
            "name": data['name'],
            "description": data.get('description', f"{data['name']} component"),
            "type": data['type'],
            "icon": data.get('icon', '🔧'),
            "min_value": 0,
            "max_value": data['maxValue'],
            "neo4j_property": data.get('neo4jProperty', component_key)
        }
        
        if 'available_components' not in config:
            config['available_components'] = {}
        config['available_components'][component_key] = new_component
        
        # Save config
        if save_config(config):
            return jsonify({
                "success": True,
                "message": "Component saved to configuration",
                "component": new_component
            })
        else:
            return jsonify({"error": "Failed to save component"}), 500
            
    except Exception as e:
        logger.error(f"Error saving custom component: {e}")
        return jsonify({"error": str(e)}), 500

def build_calculation(components, formula_config, method='weighted_avg', custom_formula=''):
    """Build calculation based on selected method"""
    
    logger.info(f"Building calculation with method: {method}")
    
    if method == 'weighted_avg':
        weighted_terms = []
        total_weight = 0
        
        for comp in components:
            comp_name = comp.get('name', '').replace(' ', '_').lower()
            weight = formula_config.get(comp_name, 0)
            current_value = float(comp.get('currentValue', 0))
            
            if weight > 0:
                weighted_terms.append(f"({current_value} * {weight})")
                total_weight += weight
        
        if not weighted_terms:
            return "0"
        
        calculation = " + ".join(weighted_terms)
        return f"(({calculation}) / {total_weight})"
    
    elif method == 'max':
        values = []
        for comp in components:
            current_value = float(comp.get('currentValue', 0))
            values.append(str(current_value))
        
        if not values:
            return "0"
        
        if len(values) == 1:
            return values[0]
        else:
            # Build nested CASE WHEN for finding maximum
            max_calc = values[0]
            for val in values[1:]:
                max_calc = f"CASE WHEN {val} > {max_calc} THEN {val} ELSE {max_calc} END"
            return max_calc
    
    elif method == 'sum':
        terms = []
        for comp in components:
            current_value = float(comp.get('currentValue', 0))
            terms.append(str(current_value))
        return " + ".join(terms) if terms else "0"
    
    elif method == 'geometric_mean':
        values = []
        for comp in components:
            current_value = float(comp.get('currentValue', 0))
            # Avoid zero in geometric mean
            values.append(f"CASE WHEN {current_value} > 0 THEN {current_value} ELSE 0.1 END")
        
        if not values:
            return "0"
        
        n = len(values)
        product = " * ".join(values)
        # Use ^ operator instead of pow function
        return f"(({product})^(1.0/{n}))"

    elif method == 'custom_formula' and custom_formula:
        # Replace component names with their values
        formula = custom_formula
        for comp in components:
            comp_name = comp.get('name', '')
            current_value = float(comp.get('currentValue', 0))
            # Replace component name with its value in the formula
            formula = formula.replace(comp_name, str(current_value))
        return formula
    
    else:
        # Default to weighted average
        logger.warning(f"Unknown method {method}, defaulting to weighted_avg")
        return build_calculation(components, formula_config, 'weighted_avg')

@app.route('/api/risk/apply-configuration', methods=['POST'])
def apply_risk_configuration():
    """Apply risk configuration from drag-drop interface"""
    try:
        data = request.get_json()
        
        # Extract all user inputs
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
        
        # Build formula configuration
        formula_config = {}
        for comp in components:
            comp_name = comp.get('name', '').replace(' ', '_').lower()
            formula_config[comp_name] = float(comp.get('weight', 0))
        
        # Execute on Neo4j
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            # Build match clause based on target
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
            
            # Build calculation based on selected method
            calculation = build_calculation(components, formula_config, calculation_method, custom_formula)
            
            logger.info(f"Calculation: {calculation}")
            
            # Execute query
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
            avg_score = record.get('avgRiskScore', 0) if record else 0
        
        driver.close()
        
        # PROPERLY SAVE AUTOMATION INFO TO EXISTING CONFIG
        config = load_config()
        if not config:
            config = {}
        
        # Create automation tracking data
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
            'created_date': datetime.now().isoformat(),
            'nodes_updated': nodes_updated,
            'avg_risk_score': avg_score
        }

        # Add sections if they don't exist
        if update_frequency != 'manual':
            if 'active_automations' not in config:
                config['active_automations'] = {}
            
            automation_id = str(uuid.uuid4())[:8]
            config['active_automations'][automation_id] = automation_data
            logger.info(f"Saving automation {automation_id}")
        
        # Always save last calculation info
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
        
        # Save the updated config
        if save_config(config):
            logger.info(f"Successfully saved automation to config. Frequency: {update_frequency}")
        else:
            logger.error("Failed to save automation to config")
        
        return jsonify({
            'success': True,
            'nodesUpdated': nodes_updated,
            'avgRiskScore': avg_score,
            'automationEnabled': update_frequency != 'manual'
        })
        
    except Exception as e:
        logger.error(f"Error applying configuration: {e}")
        return jsonify({'error': str(e)}), 500
          
if __name__ == '__main__':
    #Start Flask API
    logger.info("Starting Risk Assessment API on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)