import { databaseConfig } from "./db_config";
import neo4j from "neo4j-driver";
import { toGraphQLTypeDefs } from "@neo4j/introspector";
const fs = require("fs");

const driver = neo4j.driver(
  databaseConfig.uri,
  neo4j.auth.basic(databaseConfig.user, databaseConfig.password),
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
  fs.writeFile("schema.graphql", result.typeDefs, (err) => {
    if (err) throw err;
    console.log("Updated schema.graphql");
    process.exit(0);
  });
});
