import neo4j from "neo4j-driver";
import { toGraphQLTypeDefs } from "@neo4j/introspector";
import {writeFile} from 'fs';

const uri = "bolt://localhost:7687";
const user = "neo4j";
const password = "supertestovaciheslo";

const driver = neo4j.driver(
  uri,
  neo4j.auth.basic(user, password),
  {
    encrypted: false,
    logging: neo4j.logging.console("debug"),
  }
);

const sessionFactory = () => driver.session({defaultAccessMode: neo4j.session.READ})

/*
 * Generate schema from existing database
 */
const schemaInferenceOptions = {
  alwaysIncludeRelationships: false,
};

toGraphQLTypeDefs(sessionFactory, schemaInferenceOptions).then((result) => {
  console.log(result);
  writeFile("schema_generated.graphql", result.typeDefs, (err) => {
    if (err) throw err;
    console.log("Updated schema.graphql");
    process.exit(0);
  });
});
