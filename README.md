# Infrastructure and Service Information Model (ISIM) component

This repository consists of two subcomponents:
* REST API in the folder `isim_rest`,
* database adapter in the folder `neo4j_adapter`.

Database adapter is intended to be an installable package, hence it contains poetry files.

Input JSON format:
```json
{
  "hosts": [
    {
      "ip_address": "compulsory",
      "domain_names" : ["noncompulsory"],
      "subnets": ["noncompulsory, bude obsahovat IP range v CIDR notacii ako kluce"],
      "uris": ["noncompulsory"],
       "tag": ["noncompulsory"]
    }
  ],
  "subnets": [
    {
      "ip_range": "compulsory, in CIDR notation",
      "note": "noncompulsory",
      "contacts": ["noncompulsory, e.g., email"],
      "parents": ["noncompulsory, parent subnets"],
      "org_units": ["noncompulsory"]
    }
  ],
  "software_versions": [
    {
      "service": "compulsory together with port and protocol when version is empty",
      "version": "compulsory when protocol and port are empty, in shortened CPE string format",
      "protocol": "compulsory together with port when version is empty",
      "port": "compulsory together with port when version is empty",
      "ip_addresses": ["compulsory"],
      "tag": ["noncompulsory"]
    }
  ],
  "devices": [
    {
      "name": "compulsory",
      "org_units": ["non-compulsory"],
      "manufacturer": "non-compulsory",
      "model": "non-compulsory",
      "ip_address": "non-compulsory",
      "state": ["noncompulsory"],
      "power": ["noncompulsory"]
    }
  ],
  "applications": [
    {
      "device": "compulsory",
      "name": "compulsory"
    }
  ],
  "org_units": [
    {
      "name": "compulsory",
      "locations": ["noncompulsory, napr. facility v Netboxe, ako location pre PhysicalEnvironment"],
      "parents": ["noncompulsory"]
    }
  ]
}
```

For more details, please, see README.md files in subcomponents.

# How to run

The application itself is dockerized. For local non-production deployment, repository offers a simple docker compose file
deploying instance of Neo4j, the ISIM rest as well as optional loading of initial data to Neo4j. This can be turned off by simply 
commenting out the `neo4j_load_data` service in the compose file and the dependency on it from `neo4j` service.

After running:
```
docker compose up -d --build
```
, the ISIM REST API is available at 'http://localhost:8000'