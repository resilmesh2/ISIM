# GraphQL API for Neo4j

GraphQL API endpoint for selected vertices and relationships from Neo4j DB.

## Configure

Before running the project, you should set your Neo4j connection string and credentials in `src/db_config.js` (fill and rename `db_config.js.template` file) or in `.env`. For example:

_.env_

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=letmein
```

## Running the project

The GraphQL is provided as a docker container. It is executed with other containers from ISIM.
Please, see the root README.md  
