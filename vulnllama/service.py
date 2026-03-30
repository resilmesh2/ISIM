import logging
import threading
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.runnables.utils import Input, Output
from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher_utils import CypherQueryCorrector, Schema
from langchain_openai import ChatOpenAI
from neo4j import Driver, GraphDatabase
from openai import BadRequestError
from pydantic import BaseModel

from config import AppConfig, OpenAIConfig
import copy

logger = logging.getLogger(__name__)

_service_lock = threading.Lock()
_service_instance: "VulnLlamaService | None" = None

PRIORITIZATION_SPECIFICATION = """When you are asked about prioritization of CVE vulnerabilities, their sorting, comparison, and similar tasks, identify which entities user asks about first and use only instructions for relevant entities out of the following.

1. CVSS (Common Vulnerability Scoring System) vertices can be used to obtain score. CVSS score can be completely ignored when user does not ask about it.
2. IP addresses can be used with COUNT function. When IP addresses are used together with CVSS score, CVSS score should be multiplied by the count of IP addresses that are jeopardized by the vulnerability.
3. Host vertices can be used with COUNT function. When Host vertices are used together with CVSS score, CVSS score should be multiplied by the count of hosts that are jeopardized by the vulnerability.
4. Missions can be used to obtain their criticality and with SUM function. When Mission vertices are used together with CVSS score, CVSS score should be multiplied by the sum of criticalities of jeopardized missions. 
5. Criticality of vertices of type Node can be used only when user asks about prioritization according to network topology. It cannot be used together with IP addresses, Host vertices, or Missions. When used together with CVSS score, CVSS score is multiplied by the sum of final criticalities of Node vertices.
"""

def _get_llm(openai_config: OpenAIConfig, human_response: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=openai_config.response_model if human_response else openai_config.query_model,
        temperature=openai_config.human_transformer_temperature
        if human_response
        else openai_config.query_builder_temperature,
        base_url=openai_config.base_url,
        api_key=openai_config.api_token,
    )


def get_user_language(question: str, openai_config: OpenAIConfig) -> str:
    llm = _get_llm(openai_config)
    prompt_ = f"Return just the name of the language the following text is in: {question}"
    message_ = llm.invoke(prompt_)
    return message_.content


def get_query_builder_chain(graph_: Neo4jGraph, openai_config: OpenAIConfig) -> Runnable[Input, Output]:
    cypher_llm = _get_llm(openai_config)
    cypher_template = """Based on the Neo4j graph schema below, write a Cypher query that would answer the user's question.

                Schema: {schema}
                The schema has three parts - node properties, relationship properties, and the relationships.
                The first part starts with line "Node properties:". Each of the lines in the first part starts with a name of node type, followed by a space and left curly bracket. 
                An enumeration of properties and their types is inside of the curly brackets. Properties are immediately followed by colons, while types are written with capital letters.
                The second part starts with line "Relationship properties:". Each of the lines starts with a name of relationship type in capital letters, followed by a space and left curly bracket. 
                An enumeration of properties and their types is inside of the curly brackets. Properties are immediately followed by colons, while types are written with capital letters.
                This part must be used only to obtain names of properties and their types. The third part must be used to create paths with relationships.
                The third part starts with line "The relationships:". Each of the lines has the same format - (:<source_node_type>)-[:<relationship_type>]->(:<destination_node_type>).
                It means that the database contains relationships from the source node type to the destination node type that have the specified relationship type.
                The arrow "->" represents direction of the relationship. You can chain only relationships listed in this part to create your queries. Use the correct direction.

                Question: {question}

                Cypher query:"""
    cypher_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                Task: Given an input question, convert it to a Cypher query.
                Specification:
                - Return only the query, no pre-amble or additional text, no formatting such as newlines or linebreaks or backticks.
                - Try to make string comparisons case insensitive.
                - If information about datetime and timestamps is in strings, they start with "YYYY-MM-DDTHH:MM:SS.sss". Convert it from that with apoc parse.

                """ + PRIORITIZATION_SPECIFICATION,
            ),
            ("human", cypher_template),
        ]
    )
    chain = (
        RunnablePassthrough.assign(
            schema=lambda _: graph_.get_schema,
        )
        | cypher_prompt
        | cypher_llm.bind(stop=["\nCypherResult:"])
        | StrOutputParser()
    )

    class Question(BaseModel):
        question: str

    return chain.with_types(input_type=Question)


def get_visualization_query_builder_chain(graph_: Neo4jGraph, openai_config: OpenAIConfig) -> Runnable[Input, Output]:
    cypher_llm = _get_llm(openai_config)
    cypher_template = """Based on the Neo4j graph schema below, write an output Cypher query that would return all vertices 
                and edges used in input Cypher query below to determine its returned results.

                Schema: {schema}
                The schema has three parts - node properties, relationship properties, and the relationships.
                The first part starts with line "Node properties:". Each of the lines in the first part starts with a name of node type, followed by a space and left curly bracket. 
                An enumeration of properties and their types is inside of the curly brackets. Properties are immediately followed by colons, while types are written with capital letters.
                The second part starts with line "Relationship properties:". Each of the lines starts with a name of relationship type in capital letters, followed by a space and left curly bracket. 
                An enumeration of properties and their types is inside of the curly brackets. Properties are immediately followed by colons, while types are written with capital letters.
                This part must be used only to obtain names of properties and their types. The third part must be used to create paths with relationships.
                The third part starts with line "The relationships:". Each of the lines has the same format - (:<source_node_type>)-[:<relationship_type>]->(:<destination_node_type>).
                It means that the database contains relationships from the source node type to the destination node type that have the specified relationship type.
                The arrow "->" represents direction of the relationship. You can chain only relationships listed in this part to create your queries. Use the correct direction.

                Input Cypher query: {question}

                Output Cypher query:"""
    cypher_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                Task: Given an input Cypher query, convert it to a new Cypher query. Limit your results to 100 entities.
                Specification:
                - Return only the query, no pre-amble or additional text, no formatting such as newlines or linebreaks or backticks.
                - Try to make string comparisons case insensitive.
                - If information about datetime and timestamps is in strings, they start with "YYYY-MM-DDTHH:MM:SS.sss". Convert it from that with apoc parse.

                """,
            ),
            ("human", cypher_template),
        ]
    )
    chain = (
        RunnablePassthrough.assign(
            schema=lambda _: graph_.get_schema,
        )
        | cypher_prompt
        | cypher_llm.bind(stop=["\nCypherResult:"])
        | StrOutputParser()
    )

    class Question(BaseModel):
        question: str

    return chain.with_types(input_type=Question)


def get_result_to_human_markdown_chain(graph_: Neo4jGraph, openai_config: OpenAIConfig) -> Runnable[Input, Output]:
    cypher_llm = _get_llm(openai_config, human_response=True)
    cypher_template = """Based on the Neo4j graph schema and query below, interpret the result below. Use the following markdown format with three sections.
            **Result:** The explanation of the result of the query as short as possible in \"{language}\".
            **Data:**  The table containing results of the query, formatted using pipes (|) and hyphens (---). We do not mind longer tables, let's say up to 20 rows.
            **Explanation:** The explanation of the approach for obtaining the result containing 2-3 sentences.

            Schema: {schema}

            Query: {question}

            Result: {result}

            Your answer using the prescribed format:"""
    cypher_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                Task: Given an input transform the Cypher query and its result to human readable markdown.
                Specification: Return only the markdown, no pre-amble or additional text, no formatting such as newlines or linebreaks, or backticks.
                """,
            ),
            ("human", cypher_template),
        ]
    )
    chain = (
        RunnablePassthrough.assign(
            schema=lambda _: graph_.get_schema,
        )
        | cypher_prompt
        | cypher_llm.bind(stop=["\nCypherResult:"])
        | StrOutputParser()
    )

    class Question(BaseModel):
        question: str
        result: str

    return chain.with_types(input_type=Question)


def do_query(driver_: Driver, query_: str) -> str:
    if any(bad_word in query_.upper() for bad_word in ["CREATE", "DELETE", "DETACH", "REMOVE", "LOAD"]):
        return "Data modifications are not allowed."

    if "MATCH" not in query_:
        return "No MATCH statement found in the query."

    records, summary, _ = driver_.execute_query(query_, database_="neo4j")

    result_ = ""
    for r in records:
        result_ += f"{r}"

    logger.info(
        "Cypher query returned %s records in %s ms.",
        len(records),
        summary.result_available_after,
    )
    return result_


class VulnLlamaService:
    def __init__(self) -> None:
        config = AppConfig.get()
        self._openai_config = config.openai
        self._driver = GraphDatabase.driver(
            config.neo4j.bolt,
            auth=(config.neo4j.user, config.neo4j.password),
        )
        self._driver.verify_connectivity()

        self._graph = Neo4jGraph(
            url=config.neo4j.bolt,
            username=config.neo4j.user,
            password=config.neo4j.password,
        )
        self._query_builder_chain = get_query_builder_chain(self._graph, self._openai_config)
        self._visualization_query_chain = get_visualization_query_builder_chain(self._graph, self._openai_config)
        self._human_result_chain = get_result_to_human_markdown_chain(self._graph, self._openai_config)

        relationships = self._graph.structured_schema.get("relationships") or []
        corrector_schema = [Schema(el["start"], el["type"], el["end"]) for el in relationships]
        self._cypher_validation = CypherQueryCorrector(corrector_schema)

    def run_query(self, query_: str) -> str:
        try:
            return do_query(self._driver, query_)
        except Exception as exc:  # noqa: BLE001
            logger.exception("VulnLlama query failed.")
            return "Query failed with following error: " + str(exc)

    def answer(self, question: str) -> dict[str, Any]:
        language = get_user_language(question, self._openai_config)
        logger.info("Detected language: %s", language)
        query = self._query_builder_chain.invoke({"question": question})
        result = self.run_query(query)
        try:
            human_result = self._human_result_chain.invoke(
                {"question": query, "result": copy.deepcopy(result), "language": language}
            )
        except BadRequestError as exc:
            human_result = str(exc)
        visualization_query = self._visualization_query_chain.invoke({"question": query})
        return {
            "question": question,
            "language": language,
            "query": query,
            "visualization_query": visualization_query,
            "result": copy.deepcopy(result),
            "human_result": human_result,
        }


def get_vulnllama_service() -> VulnLlamaService:
    global _service_instance
    if _service_instance is not None:
        return _service_instance
    with _service_lock:
        if _service_instance is None:
            _service_instance = VulnLlamaService()
    return _service_instance
