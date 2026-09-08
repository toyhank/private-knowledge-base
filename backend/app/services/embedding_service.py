from threading import RLock


class EmbeddingService:
    def __init__(self, settings):
        self.settings = settings
        self._model = None
        self.lock = RLock()

    @property
    def model(self):
        with self.lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                try:
                    model_path = self.settings.embedding_model
                    if self.settings.models_local_only:
                        from huggingface_hub import snapshot_download

                        try:
                            model_path = snapshot_download(
                                self.settings.embedding_model,
                                cache_dir=str(self.settings.model_cache),
                                local_files_only=True,
                            )
                        except Exception:
                            pass
                    model = SentenceTransformer(
                        model_path,
                        device=self.settings.embedding_device,
                        cache_folder=str(self.settings.model_cache),
                        local_files_only=self.settings.models_local_only,
                        trust_remote_code=False,
                    )
                    if model.get_sentence_embedding_dimension() != self.settings.embedding_dimensions:
                        raise ValueError("Embedding 维度与配置不一致，请使用新 collection 重新建库")
                    model.max_seq_length = self.settings.chunk_size + 2
                    self._model = model
                except Exception as exc:
                    raise RuntimeError(
                        "BGE embedding 加载失败；请运行 scripts/download_models.py 并检查设备配置"
                    ) from exc
            return self._model

    @property
    def tokenizer(self):
        return self.model.tokenizer

    def embed_documents(self, texts):
        with self.lock:
            return self.model.encode(
                texts,
                batch_size=self.settings.embedding_batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).tolist()

    def embed_query(self, query):
        return self.embed_documents([query])[0]
