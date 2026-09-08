import httpx


class LLMClient:
    def __init__(self, settings):
        self.settings = settings

    def complete(self, messages):
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": self.settings.llm_max_tokens,
            "stream": False,
        }
        if self.settings.llm_reasoning_effort:
            payload["reasoning_effort"] = self.settings.llm_reasoning_effort
        # Ignore proxy environment variables so local document context stays local.
        with httpx.Client(
            timeout=self.settings.llm_timeout_seconds, trust_env=False, follow_redirects=False
        ) as client:
            response = client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                json=payload,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"本地模型请求失败（HTTP {response.status_code}），请检查模型名称及服务状态"
                )
            try:
                choice = response.json()["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise RuntimeError("模型输出达到长度上限，请缩短问题或增加 LLM_MAX_TOKENS")
                answer = choice["message"]["content"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("empty content")
                return answer
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise RuntimeError("本地模型未返回有效回答，请检查模型的 OpenAI 兼容接口") from exc
