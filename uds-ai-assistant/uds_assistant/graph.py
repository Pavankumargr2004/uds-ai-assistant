"""Neo4j graph client for requirements and test traceability."""
from typing import List, Dict, Any
import os
from neo4j import GraphDatabase

class GraphStore:
    def __init__(self, uri: str = None, user: str = "neo4j", password: str = "password"):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user
        self.password = password
        auth = None if os.getenv("NEO4J_AUTH") == "none" else (self.user, self.password)
        self.driver = GraphDatabase.driver(self.uri, auth=auth)

    def close(self):
        self.driver.close()

    def add_requirement_trace(self, project: str, requirement_id: str, requirement_text: str, test_ids: List[str]):
        """Link a requirement to the generated test cases."""
        query = """
        MERGE (r:Requirement {id: $req_id, project: $project})
        SET r.text = $req_text
        WITH r
        UNWIND $test_ids AS test_id
        MERGE (t:TestCase {id: test_id, project: $project})
        MERGE (r)-[:TESTED_BY]->(t)
        """
        with self.driver.session() as session:
            session.run(query, req_id=requirement_id, project=project, req_text=requirement_text, test_ids=test_ids)

    def get_tests_for_requirement(self, project: str, requirement_id: str) -> List[str]:
        query = """
        MATCH (r:Requirement {id: $req_id, project: $project})-[:TESTED_BY]->(t:TestCase)
        RETURN t.id AS test_id
        """
        with self.driver.session() as session:
            result = session.run(query, req_id=requirement_id, project=project)
            return [record["test_id"] for record in result]

    def get_requirements_for_test(self, project: str, test_id: str) -> List[str]:
        query = """
        MATCH (r:Requirement)-[:TESTED_BY]->(t:TestCase {id: $test_id, project: $project})
        RETURN r.id AS req_id
        """
        with self.driver.session() as session:
            result = session.run(query, test_id=test_id, project=project)
            return [record["req_id"] for record in result]
