# Infrastructure and Service Information Model (ISIM) component

This repository consists of two subcomponents:
* REST API in the folder `isim_rest`,
* database adapter in the folder `neo4j_adapter`.

Database adapter is intended to be an installable package, hence it contains poetry files.

For more details, please, see README.md files in subcomponents.

# How to run

The application itself is dockerized. For local non-production deployment, repository offers a simple docker compose file
deploying instance of Neo4j, the ISIM rest as well as optional loading of initial data to Neo4j. This can be turned off by simply 
commenting out the `neo4j_load_data` service in the compose file and the dependency on it from `neo4j` service.

If you want to load the initial data from Neo4j dump, you can either:
- create `.env` file in this directory containing the environment variable with your path `DATA_PATH=xyz`
- create env file and use `--env-file` argument when running `docker compose` command
- set the environment variable in your shell
- replace the ${DATA_PATH} occurances with your path

After running:
```
docker compose up -d
```
, the ISIM REST API is available at 'http://localhost:8000'.

If you need to rebuild the image (e. g. there is a new version of the application) run:
```
docker compose up -d --build
```

# Configuration
Configuration files are located in the [config](config) folder. Currently, the project provides configuration file
for local (`config.ini`) and dockerized (`config_docker.ini`) deployment. 

The configuration is rather simple, the ini files contains a single section

```ini
[neo4j_config]
bolt = bolt://localhost:7687
user = neo4j
password = supertestovaciheslo
```

- bolt: URI of the Neo4j database
- user: user in the Neo4j database
- password: password to Neo4j database


# API reference
API reference is available as an OpenAPI document [here](./docs/api_reference.yaml)