import math

import pytest

from backend.app.config import Settings


class CharacterTokenizer:
    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(i, i + 1) for i in range(len(text))]}


class FakeEmbedding:
    tokenizer = CharacterTokenizer()

    def embed_documents(self, texts):
        result = []
        for text in texts:
            vec = [float(word in text) for word in ["北京", "住宿", "餐饮", "报销"]]
            if not any(vec):
                vec = [0.01] * 4
            norm = math.sqrt(sum(v * v for v in vec))
            result.append([v / norm for v in vec])
        return result

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class FakeReranker:
    def rerank(self, query, hits):
        ranked = [
            h.model_copy(update={"score": 0.98 if "北京" in query and "600" in h.chunk.text else 0.01})
            for h in hits
        ]
        return sorted(ranked, key=lambda h: h.score, reverse=True)


class FakeLLM:
    def __init__(self, answer="北京出差住宿标准为每人每晚 600 元。[1]"):
        self.answer = answer
        self.messages = []

    def complete(self, messages):
        self.messages = messages
        return self.answer


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        model_cache=tmp_path / "models",
        embedding_dimensions=4,
        frontend_dist=tmp_path / "no-ui",
        chunk_size=80,
        chunk_overlap=12,
    )
