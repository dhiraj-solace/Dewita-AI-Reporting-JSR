import hashlib
import math
import re
from pathlib import Path
from typing import Any

VECTOR_STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "vector_store"
COLLECTION_NAME = "devita_gold_sql_examples"
EMBEDDING_DIMENSIONS = 256


class HashEmbeddingFunction:
    @staticmethod
    def name() -> str:
        return "devita_hash_embedding"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [_hash_embedding(document) for document in input]

    def embed_query(self, input: str) -> list[float]:
        return _hash_embedding(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return [_hash_embedding(document) for document in input]


def is_vector_store_available() -> bool:
    try:
        _collection()
    except Exception:
        return False
    return True


def upsert_gold_example(attempt: dict[str, Any]) -> None:
    collection = _collection()
    attempt_id = str(attempt.get("id") or "")
    question = str(attempt.get("user_question") or "")
    sql = str(attempt.get("final_sql") or "")
    if not attempt_id or not question or not sql:
        return
    collection.upsert(
        ids=[attempt_id],
        documents=[question],
        embeddings=[_hash_embedding(question)],
        metadatas=[
            {
                "attempt_id": attempt_id,
                "user_question": question,
                "sql": sql,
            }
        ],
    )


def search_gold_examples(question: str, limit: int = 3) -> list[dict[str, str]]:
    collection = _collection()
    result = collection.query(query_embeddings=[_hash_embedding(question)], n_results=limit)
    metadatas = result.get("metadatas") or [[]]
    return [
        {
            "user_question": str(metadata.get("user_question") or ""),
            "sql": str(metadata.get("sql") or ""),
        }
        for metadata in metadatas[0]
        if metadata.get("user_question") and metadata.get("sql")
    ]


def _collection() -> Any:
    import chromadb

    VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _hash_embedding(document: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in _tokens(document):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", value.lower())
