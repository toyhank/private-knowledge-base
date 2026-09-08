from threading import RLock

from qdrant_client import QdrantClient, models

from ..schemas import Chunk, Hit


class VectorStore:
    def __init__(self, settings):
        self.name = settings.qdrant_collection
        self.lock = RLock()
        self.client = (
            QdrantClient(url=settings.qdrant_url, timeout=30)
            if settings.qdrant_url
            else QdrantClient(path=str(settings.data_dir / "qdrant"), force_disable_check_same_thread=True)
        )
        if not self.client.collection_exists(self.name):
            self.client.create_collection(
                self.name,
                vectors_config=models.VectorParams(
                    size=settings.embedding_dimensions, distance=models.Distance.COSINE
                ),
            )
        config = self.client.get_collection(self.name).config.params.vectors
        if not isinstance(config, models.VectorParams) or config.size != settings.embedding_dimensions:
            raise ValueError("Qdrant collection 向量维度不匹配，请选择新的 collection")
        if settings.qdrant_url:
            self.client.create_payload_index(
                self.name, "document_id", models.PayloadSchemaType.KEYWORD, wait=True
            )

    def upsert_chunks(self, chunks, vectors):
        if len(chunks) != len(vectors):
            raise ValueError("Chunk 和向量数量不匹配")
        with self.lock:
            self.client.upsert(
                self.name,
                points=[
                    models.PointStruct(id=c.chunk_id, vector=v, payload=c.model_dump())
                    for c, v in zip(chunks, vectors)
                ],
                wait=True,
            )

    def search(self, vector, document_ids, limit):
        if not document_ids:
            return []
        with self.lock:
            points = self.client.query_points(
                self.name,
                query=vector,
                limit=limit,
                query_filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))]
                ),
                with_payload=True,
            ).points
            return [Hit(chunk=Chunk(**p.payload), retrieval_score=p.score) for p in points]

    def delete_document(self, document_id):
        with self.lock:
            self.client.delete(
                self.name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id", match=models.MatchValue(value=document_id)
                            )
                        ]
                    )
                ),
                wait=True,
            )

    def chunks(self, document_id, offset=0, limit=50):
        with self.lock:
            points, _ = self.client.scroll(
                self.name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
                        models.FieldCondition(
                            key="chunk_index", range=models.Range(gte=offset, lt=offset + limit)
                        ),
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return sorted([Chunk(**p.payload) for p in points], key=lambda c: c.chunk_index)

    def close(self):
        self.client.close()
