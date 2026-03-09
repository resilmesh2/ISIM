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
from pydantic import BaseModel

from config import AppConfig, OpenAIConfig

logger = logging.getLogger(__name__)

_service_lock = threading.Lock()
_service_instance: "VulnLlamaService | None" = None

# Specify which entities can be used in prioritization tasks and what is important about them.
# LLM chooses them when necessary and makes up its own criteria.
# Method: Directional stimulus prompting
PRIORITIZATION_SPECIFICATION = """When you are asked about prioritization of vulnerabilities, their sorting, comparison, and similar tasks, the following sentences contain description of how entities from the Neo4j database must be used.
Your approach must always adhere to these instructions numbered from 1 to 10: 
1. CVE can be used with its properties. You can further analyze CVE description.
2. CVSS (Common Vulnerability Scoring System) vertices can be used with all their properties. 
3. IP addresses and Host vertices can be used with COUNT function.
4. Subnets and Organization Units can be used to determine how widespread the vulnerability is.
5. Missions can be used with their properties and COUNT function.
6. Mission Dependency vertices can be used to consider cascading impact on missions.
7. Users and their Roles on Devices can be used together with impacts of vulnerabilities present directly in CVE properties or in CVE descriptions when they are not separately extracted. Impacts may indicate what the attacker can do with the device if impersonating a user. Roles represent levels of privileges.
8. Network Service nodes may indicate whether the vulnerability is accessible from another machine if the kind of network service matches the description of the vulnerability.
9. Vertices of type Node, their properties, and connections to other vertices of type Node can be used to estimate impact of vulnerability in the computer network.
10. Vertices of type Application can be considered if you think that vulnerability could influence their functionality and they have important functionality.

The vertices can be used with paths containing them, in final formulas, or argumentation.
Always focus your attention on the current state of the database. It is not necessary to use all node types.
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
    cypher_template = """Based on the Neo4j graph schema below, write a Cypher query that would answer the user's question:
    {schema}

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
                - Severity passed to the query must always be in English.
                - try to make string comparisons case insensitive
                - Be aware that entities with valid_from and valid_to are chronicled - this means that they were valid only for a certain time.
                The current newest information has always valid_to set to null or is empty
                - Information about datetime and timestamps is in strings, the format is "YYYY-MM-DD HH:MM:SS.sssss". Convert it from that with apoc parse

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
    and edges used in input Cypher query to determine its returned results:
    {schema}

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
                - Severity passed to the query must always be in English.
                - try to make string comparisons case insensitive
                - Be aware that entities with valid_from and valid_to are chronicled - this means that they were valid only for a certain time.
                The current newest information has always valid_to set to null or is empty
                - Information about datetime and timestamps is in strings, the format is "YYYY-MM-DD HH:MM:SS.sssss". Convert it from that with apoc parse

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
    cypher_template = """Based on the Neo4j graph schema below and query: \"{question}\", interpret the result: \"{result}\" and give 2-3 sentences of explanation. Use following format:
    **Result:** Here will be the result of the query explained as short as possible. Write everything in \"{language}\".
    **Data**  Always try to include results as a table. We do not mind longer tables, let's say up to 20 rows.
    **Explanation:** Here will be the explanation of the result.

    Schema: {schema}

    Question: {question}
    Cypher query:"""
    cypher_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                Task: Given an input transform the Cypher query result to human readable markdown.
                Specification: Return only the query, no pre-amble or additional text, no formatting such as newlines or linebreaks or backticks.
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
        human_result = self._human_result_chain.invoke(
            {"question": query, "result": result, "language": language}
        )
        visualization_query = self._visualization_query_chain.invoke({"question": query})
        return {
            "question": question,
            "language": language,
            "query": query,
            "visualization_query": visualization_query,
            "result": result,
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
