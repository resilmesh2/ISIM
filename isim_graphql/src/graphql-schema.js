import fs from "fs";
import path from "path";
import { fileURLToPath } from 'url';

/*
 * Check for GRAPHQL_SCHEMA environment variable to specify schema file
 * fallback to schema.graphql if GRAPHQL_SCHEMA environment variable is not set
 */

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const typeDefs = fs
  .readFileSync(
    process.env.GRAPHQL_SCHEMA || path.join(__dirname, "schema.graphql")
  )
  .toString("utf-8");
