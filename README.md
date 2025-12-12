# Infrastructure and Service Information Model (ISIM) component

This repository consists of three subcomponents:
* REST API in the folder `isim_rest`,
* database adapter in the folder `neo4j_adapter`,
* GraphQL subcomponent in the folder `isim_graphql`.

Database adapter is intended to be an installable package, hence it contains poetry files.
It contains a cleaner that can be executed according to instructions in the adapter's README.md.

For more details, please, see README.md files in subcomponents.

The necessary infrastructure to run this project properly consists of:
- Neo4J database for results
- ISIM Django service with REST API to upload and read data
- ISIM NodeJS GraphQL API to read data
- OPTIONALLY: init container uploading Neo4J dump file to the database

All components can be deployed with Docker. There is a `compose.yaml` file spawning all components.


# How to run

## Running the app

After running:
```
docker compose up -d
```
, the ISIM REST API is available at http://localhost:8000. The GraphQL API is available
at http://localhost:4001/graphql.

If you need to rebuild the image (e. g. there is a new version of the application) run:
```
docker compose up -d --build
```

# Configuration
Configuration files are located in the [config](config) folder. Currently, the project provides configuration file
for local (`config.yaml`) and dockerized (`config_docker.yaml`) deployment. 

The configuration is rather simple, the ini files contain a single section

```yaml
neo4j:
  password: supertestovaciheslo
  bolt: bolt://neo4j:7687
  user: neo4j
```

- bolt: URI of the Neo4j database
- user: user in the Neo4j database
- password: password to Neo4j database

Another configuration file (`config_organization.yml`) in the same folder defines constituency of users.
Its default version contains a name of organization, and hosts described by their IP addresses, domain names, 
and subnets: 

```yaml
name: "test"
hosts:
  - ip_address: "127.0.0.1"
    domain_names: ["test.cz"]
    subnets: ["127.0.0.0/24"]
```

# How to work with the application

## ISIM REST
ISIM REST component allows users to upload and obtain information about missions and assets. Example upload input for assets can look like this:
```json
{
    "hosts": [
        {
            "ip_address": "10.0.0.1",
            "tag": ["smth"],
            "domain_names": ["test.com"],
            "uris": ["http://test.com"],
            "subnets": ["10.0.0.0/16"]
        }
    ],
	"subnets": [
		{
			"ip_range": "10.0.0.0/16",
			"note": "basic net A",
			"contacts": ["test@test.test"],
			"parents": ["10.0.0.0/8"],
			"org_units": ["ORG A"]
		},
        {
			"ip_range": "10.0.0.0/8",
			"note": "basic net",
			"contacts": ["test@test.test"],
			"org_units": ["ORG A", "ORG B"]
		}
	],
	"org_units": [
		{
			"name": "ORG A",
			"locations": ["NY"],
			"parents": ["ORG B"]
		},
		{
			"name": "ORG B",
			"locations": ["NY", "Brno"]
		}
	],
	"devices": [
		{
			"name": "DevA",
			"ip_address": "10.0.0.1",
			"org_units": ["ORG A"]
		}
	],
	"software_versions": [
		{
			"version": "v1",
			"port": 22,
			"protocol": "tcp",
			"service": "ssh",
			"ip_addresses": ["10.0.0.1"],
			"tag": ["xd1"]
		}
	],
	"applications": [
		{
			"device": "DevA",
			"name": "TestAppA"
			
		}
	]
}
```
When you POST this input to the `/assets` endpoint, the application creates the corresponding assets.  

Similarly, input for missions can look like this:
```json
{
    "nodes": {
        "missions": [
						{
                "id": 1,
                "name": "Public-Facing Services",
                "criticality": 5,
                "description": "This mission represents services that must be available for public."
            }
        ],
        "services": [
            {
                "id": 11,
                "name": "WEB"
            }
        ],
        "aggregations": {
            "or": [],
            "and": []
        },
        "hosts": [
            {
                "id": 30,
                "hostname": "webserver",
                "ip": "10.0.0.1"
            }
        ]
    },
    "relationships": {
        "one_way": [],
        "two_way": [],
        "dependencies": [],
        "supports": [
            {
                "from": "Public-Facing Services",
                "to": "WEB"
            }
        ],
        "has_identity": [
            {
                "from": "WEB",
                "to": "webserver"
            }
        ]
    }
}
```

When you POST this input to the `/missions` endpoint, the application creates the corresponding mission.  

API simply returns.
```text
"Processed successfully"
```

The application allows users to list information from the point of view of the IP addresses by asking the specialized `/asset_info` endpoint. There 
are also other endpoints allowing to query returning information directly from Neo4j without additional postprocessing.

Example of the `/asset_info` output (corresponding to the input above):
```json
[ 
    {
        "ip": "10.0.0.1", 
        "domain_names": [
            "test.com"
        ], 
        "subnets": [
            "10.0.0.0/16"
        ], 
        "contacts": [
            "test@test.test"
        ], 
        "missions": [
            "Public-Facing Services"
        ], 
        "nodes": [{
            "degree_centrality": null, 
            "pagerank_centrality": null, 
            "topology_degree": null, 
            "topology_betweenness": null
        }], 
        "critical": 1
    }
]
```

## ISIM GRAPHQL
ISIM GraphQL provides GraphQL API over selected entities. Detailed schema is below.

Working with the example data from ISIM REST section above, you can try out the following query displaying the same data
as the `/asset_info` endpoint:
```graphql
query IPaddresses {
  ips {
    address
    subnets {
      range
      contacts {
        name
      }
    }
    domain_names {
      domain_name
    }
    nodes {
      host {
        components {
          missions {
            name
          }
        }
      }
    }
  }
}
```

with the output
```json
{
  "data": {
    "ips": [
      {
        "address": "10.0.0.1",
        "subnets": [
          {
            "range": "10.0.0.0/16",
            "contacts": [
              {
                "name": "test@test.test"
              }
            ]
          }
        ],
        "domain_names": [
          {
            "domain_name": "test.com"
          }
        ],
        "nodes": [
          {
            "host": {
              "components": [
                {
                  "missions": [
                    {
                      "name": "Public-Facing Services"
                    }
                  ]
                }
              ]
            }
          }
        ]
      }
    ]
  }
}
```


# API reference
REST API reference is available as an OpenAPI document [here](./docs/api_reference.yaml).
GraphQL API schema is available as a [separate file](./isim_graphql/src/schema.graphql), too.

# Optional data preload

The application itself is dockerized. For local non-production deployment, repository offers a simple docker compose file
deploying instance of Neo4j, the ISIM rest and GraphQL as well as optional loading of initial data to Neo4j. This can be turned on by:
- Editing the `compose.yaml` file: 
  1) uncomment the `neo4j_load_data` service
  2) uncomment `#      - ${DATA_PATH}:/tmp/dumps/neo4j.dump` line
  3) uncomment `depends_on` section in `neo4j` service

If you want to load the initial data from Neo4j dump, you can either:
- create `.env` file in this directory containing the environment variable with your path `DATA_PATH=xyz`
- create env file and use `--env-file` argument when running `docker compose` command
- set the environment variable in your shell
- replace the ${DATA_PATH} occurances with your path

The data loading option was tested with [dataset from Cyberczech cyber defence exercise](https://github.com/Resilmesh-EU/datasets/blob/main/CRUSOE%20Datasets/cyber-czech-neo4j-May-6-2024-16-41-30.dump).

> [!WARNING]
> Be aware that `neo4j_load_data` container overwrites the target database data. If you are using the application in production
> and you need data persistence, you SHOULD NOT run this container after your initial setup.

# Tests

Tests are available in `isim_rest/test` folder. 
Test data contain example inputs for `/assets` and `/missions` endpoints.
Tests were executed using `python manage.py test` inside `isim` container
after connecting to it using `sudo docker exec -it <container_id> bash`.

# Versions Used During Testing
ISIM was successfully tested with the following OS configurations and docker versions. 
Versions of software packages can be found in `poetry.lock` and `pyproject.toml` files.
These versions of software packages are automatically deployed when docker is used according to 
instructions from this README.md file.

|Operating System|Docker Version|Docker Compose Version| Memory   |CPU Architecture|Number of Cores|
|----------------|--------------|----------------------|----------|----------------|---------------|
|Ubuntu 24.04.2 LTS|28.0.4|v2.34.0| 32.0 GiB |x86_64|16 cores|
|Ubuntu 24.04.1 LTS|26.1.3|v2.14.0| 32.0 GiB |x86_64|6 cores|
|Ubuntu 22.04.5 LTS|28.0.4|v2.34.0| 64.0 GiB |x86_64|16 cores|

# Guidelines for Defining Missions
Guidelines on how to define missions are listed in [mission guidelines](docs/mission_guidelines.md).