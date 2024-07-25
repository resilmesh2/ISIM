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
