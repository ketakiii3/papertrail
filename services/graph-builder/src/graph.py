"""Neo4j knowledge graph client."""

import logging
from neo4j import GraphDatabase
from shared.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    def close(self):
        self._driver.close()

    def setup_schema(self):
        """Create constraints and indexes."""
        with self._driver.session() as session:
            constraints = [
                "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.ticker IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Filing) REQUIRE f.filing_id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (cl:Claim) REQUIRE cl.claim_id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Insider) REQUIRE i.name IS UNIQUE",
                "CREATE INDEX IF NOT EXISTS FOR (cl:Claim) ON (cl.claim_date)",
                "CREATE INDEX IF NOT EXISTS FOR (f:Filing) ON (f.filed_at)",
            ]
            for c in constraints:
                session.run(c)
            logger.info("Neo4j schema initialized")

    def upsert_company(self, ticker: str, name: str, sector: str = None):
        with self._driver.session() as session:
            session.run(
                """MERGE (c:Company {ticker: $ticker})
                   SET c.name = $name, c.sector = $sector""",
                ticker=ticker, name=name, sector=sector,
            )

    def upsert_filing(self, filing_id: int, form_type: str, filed_at: str,
                      url: str, company_ticker: str):
        with self._driver.session() as session:
            session.run(
                """MERGE (f:Filing {filing_id: $filing_id})
                   SET f.form_type = $form_type, f.filed_at = $filed_at, f.url = $url
                   WITH f
                   MATCH (c:Company {ticker: $ticker})
                   MERGE (c)-[:FILED]->(f)""",
                filing_id=filing_id, form_type=form_type,
                filed_at=filed_at, url=url, ticker=company_ticker,
            )

    def upsert_claim(self, claim_id: int, text: str, claim_type: str,
                     topic: str, sentiment: str, confidence: float,
                     claim_date: str, company_ticker: str, filing_id: int,
                     speaker: str = None):
        with self._driver.session() as session:
            # Create claim node and link to filing
            session.run(
                """MERGE (cl:Claim {claim_id: $claim_id})
                   SET cl.text = $text, cl.claim_type = $claim_type,
                       cl.sentiment = $sentiment, cl.confidence = $confidence,
                       cl.claim_date = $claim_date
                   WITH cl
                   MATCH (f:Filing {filing_id: $filing_id})
                   MERGE (f)-[:CONTAINS]->(cl)""",
                claim_id=claim_id, text=text[:500], claim_type=claim_type,
                sentiment=sentiment, confidence=confidence,
                claim_date=claim_date, filing_id=filing_id,
            )

            # Link to topic
            if topic:
                session.run(
                    """MERGE (t:Topic {name: $topic})
                       WITH t
                       MATCH (cl:Claim {claim_id: $claim_id})
                       MERGE (cl)-[:ABOUT]->(t)""",
                    topic=topic, claim_id=claim_id,
                )

            # Link speaker if available
            if speaker:
                session.run(
                    """MERGE (p:Person {name: $speaker, company_ticker: $ticker})
                       WITH p
                       MATCH (cl:Claim {claim_id: $claim_id})
                       MERGE (p)-[:MADE]->(cl)""",
                    speaker=speaker, ticker=company_ticker, claim_id=claim_id,
                )

    def upsert_insider_traded(self, transaction_id: int, insider_name: str,
                              ticker: str, transaction_type: str,
                              shares: int = None, price: float = None,
                              total_value: float = None, transaction_date: str = None):
        """Insider --[TRADED]--> Company (one edge per transaction_id)."""
        with self._driver.session() as session:
            session.run(
                """MERGE (i:Insider {name: $name})
                   MERGE (c:Company {ticker: $ticker})
                   MERGE (i)-[r:TRADED {transaction_id: $tid}]->(c)
                   SET r.transaction_date = $date,
                       r.type = $type,
                       r.shares = $shares,
                       r.price = $price,
                       r.total_value = $total_value""",
                name=insider_name, ticker=ticker, tid=transaction_id,
                date=transaction_date, type=transaction_type,
                shares=shares, price=price, total_value=total_value,
            )

    def upsert_anomalous_movement(self, transaction_id: int, insider_name: str,
                                  ticker: str, car: float, car_zscore: float,
                                  volume_ratio: float, event_date: str):
        """Insider --[ANOMALOUS_MOVEMENT]--> Company (only when flagged)."""
        with self._driver.session() as session:
            session.run(
                """MERGE (i:Insider {name: $name})
                   MERGE (c:Company {ticker: $ticker})
                   MERGE (i)-[r:ANOMALOUS_MOVEMENT {transaction_id: $tid}]->(c)
                   SET r.car = $car,
                       r.car_zscore = $z,
                       r.volume_ratio = $vol,
                       r.event_date = $date""",
                name=insider_name, ticker=ticker, tid=transaction_id,
                car=car, z=car_zscore, vol=volume_ratio, date=event_date,
            )

    def add_contradiction_edge(self, claim_a_id: int, claim_b_id: int,
                               severity: str, similarity: float,
                               nli_score: float, time_gap_days: int = None):
        with self._driver.session() as session:
            session.run(
                """MATCH (a:Claim {claim_id: $a_id})
                   MATCH (b:Claim {claim_id: $b_id})
                   MERGE (a)-[r:CONTRADICTS]->(b)
                   SET r.severity = $severity, r.similarity = $similarity,
                       r.nli_score = $nli_score, r.time_gap_days = $time_gap""",
                a_id=claim_a_id, b_id=claim_b_id,
                severity=severity, similarity=similarity,
                nli_score=nli_score, time_gap=time_gap_days,
            )

    def query_company_contradictions(self, ticker: str) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(
                """MATCH (c:Company {ticker: $ticker})-[:FILED]->(f:Filing)
                          -[:CONTAINS]->(a:Claim)-[r:CONTRADICTS]->(b:Claim)
                   RETURN a.claim_id AS claim_a_id, a.text AS claim_a_text,
                          a.claim_date AS claim_a_date,
                          b.claim_id AS claim_b_id, b.text AS claim_b_text,
                          b.claim_date AS claim_b_date,
                          r.severity AS severity, r.similarity AS similarity
                   ORDER BY r.severity DESC, r.similarity DESC""",
                ticker=ticker,
            )
            return [dict(record) for record in result]

    def query_claim_graph(self, claim_id: int, depth: int = 2) -> dict:
        """Get subgraph around a claim for visualization."""
        with self._driver.session() as session:
            result = session.run(
                """MATCH path = (cl:Claim {claim_id: $claim_id})-[*1..""" + str(depth) + """]-()
                   WITH nodes(path) AS ns, relationships(path) AS rs
                   UNWIND ns AS n
                   WITH collect(DISTINCT {
                       id: id(n),
                       labels: labels(n),
                       properties: properties(n)
                   }) AS nodes, rs
                   UNWIND rs AS r
                   RETURN nodes, collect(DISTINCT {
                       source: id(startNode(r)),
                       target: id(endNode(r)),
                       type: type(r),
                       properties: properties(r)
                   }) AS edges""",
                claim_id=claim_id,
            )
            record = result.single()
            if not record:
                return {"nodes": [], "edges": []}
            return {"nodes": record["nodes"], "edges": record["edges"]}

    def get_topic_evolution(self, ticker: str, topic: str) -> list[dict]:
        """Track how claims about a topic changed over time."""
        with self._driver.session() as session:
            result = session.run(
                """MATCH (c:Company {ticker: $ticker})-[:FILED]->(f:Filing)
                          -[:CONTAINS]->(cl:Claim)-[:ABOUT]->(t:Topic {name: $topic})
                   RETURN cl.claim_id AS claim_id, cl.text AS text,
                          cl.sentiment AS sentiment, cl.claim_date AS date,
                          f.form_type AS form_type
                   ORDER BY cl.claim_date ASC""",
                ticker=ticker, topic=topic,
            )
            return [dict(record) for record in result]
