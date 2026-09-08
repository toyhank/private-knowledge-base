class RetrievalService:
    """Dense retrieval seam; future hybrid retrievers can return the same Hit schema."""

    def __init__(self, embedding, vector_store, settings):
        self.embedding, self.vector_store, self.settings = embedding, vector_store, settings

    def retrieve(self, query, document_ids):
        if not document_ids:
            return []
        return self.vector_store.search(
            self.embedding.embed_query(query), document_ids, self.settings.retrieval_top_k
        )
