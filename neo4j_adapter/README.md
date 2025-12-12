# Neo4j Adapter

The `neo4j_adapter` contains a database adapter from ISIM. 
One of its classes is a database cleaner.

## How to Run Cleaner
The following script contains commands that execute the cleaner and its methods. 
`"neo4j_database_password"` should be replaced with a password to Neo4j database. It is
assumed that the Neo4j bolt is accessible on its standard port `7687`.

```python
from neo4j_adapter.cleaner import Cleaner
cleaner = Cleaner("neo4j_database_password")

# choose one of possible methods
cleaner.clean_old_vulnerabilities()
cleaner.clean_host_layer()
cleaner.clean_network_layer()
cleaner.clean_security_events()
```
