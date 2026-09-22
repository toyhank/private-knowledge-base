from threading import RLock


class RerankerService:
    def __init__(self, settings):
        self.settings = settings
        self._model = None
        self.lock = RLock()

    def rerank(self, query, documents):
        if not documents:
            return []
        with self.lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                try:
                    model_path = self.settings.reranker_model
                    if self.settings.models_local_only:
                        from huggingface_hub import snapshot_download

                        try:
                            model_path = snapshot_download(
                                self.settings.reranker_model,
                                cache_dir=str(self.settings.model_cache),
                                local_files_only=True,
                            )
                        except Exception:  # noqa: BLE001 - fall back to the configured local model path
                            model_path = self.settings.reranker_model
                    self._model = CrossEncoder(
                        model_path,
                        device=self.settings.reranker_device,
                        max_length=self.settings.reranker_max_length,
                        cache_folder=str(self.settings.model_cache),
                        local_files_only=self.settings.models_local_only,
                        trust_remote_code=False,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        "BGE reranker 加载失败；请下载模型并检查设备配置，系统未降级重排"
                    ) from exc
            import torch

            scores = self._model.predict(
                [(query, hit.chunk.text) for hit in documents],
                batch_size=self.settings.reranker_batch_size,
                activation_fn=torch.nn.Sigmoid(),
                show_progress_bar=False,
            )
            ranked = [hit.model_copy(update={"score": float(score)}) for hit, score in zip(documents, scores)]
            return sorted(ranked, key=lambda hit: hit.score, reverse=True)
