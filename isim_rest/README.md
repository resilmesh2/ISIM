# ISIM REST

The `isim_rest` contains REST API for Neo4j database.

## How to Run
It is necessary to fill Neo4j password in `conf.ini` and set up virtual environment using `poetry`.
Neo4j database needs the APOC plugin.

REST API can be started using 

```bash
poetry run python manage.py runserver
```

