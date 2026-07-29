"""OpenAI 兼容的 LLM 客户端。

- 主传输：requests（常规网络环境）
- 备用传输：curl 子进程（某些沙箱/受限网络会拦截 Python TLS 指纹，curl 可通行）
- 兼容推理型模型（忽略 reasoning_content，只取正文 content）
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

import requests

from . import config


class LLMError(RuntimeError):
    pass


def _post_requests(payload: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        f"{config.LLM_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=config.LLM_TIMEOUT,
    )
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _post_curl(payload: dict[str, Any]) -> dict[str, Any]:
    # Authorization 经 -K - 从 stdin 传入：API key 不出现在 argv / 进程列表中
    p = subprocess.run(
        [
            "curl", "-sS", "--http1.1", "--max-time", str(int(config.LLM_TIMEOUT)),
            "-K", "-",
            f"{config.LLM_BASE_URL}/chat/completions",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload),
        ],
        input=f'header = "Authorization: Bearer {config.LLM_API_KEY}"\n',
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise LLMError(f"curl failed: {p.stderr[:300]}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:  # 可能是网关错误页
        raise LLMError(f"bad json from curl: {p.stdout[:300]}") from e


def chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4000,
    temperature: float = 0.0,
    model: str | None = None,
) -> str:
    """调用 chat completions，返回正文 content。失败按指数退避重试。"""
    if not config.llm_available():
        raise LLMError("未配置 LLM_API_KEY；请配置后重试，或使用回放模式。")
    payload: dict[str, Any] = {
        "model": model or config.LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    # 推理型模型（如 deepseek-v4）默认关闭思考链：思考 token 计入 max_tokens 且时延
    # 高一个量级（实测单调用 >200s，关闭后 ~25s）。LLM_THINKING=on 可重新开启。
    if os.environ.get("LLM_THINKING", "off").lower() in ("off", "0", "false", "disabled"):
        payload["thinking"] = {"type": "disabled"}
    prefer = os.environ.get("LLM_TRANSPORT", "auto")  # auto | requests | curl
    last_err: Exception | None = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            if prefer == "curl":
                data = _post_curl(payload)
            else:
                try:
                    data = _post_requests(payload)
                except (requests.ConnectionError, requests.Timeout):
                    if prefer == "requests":
                        raise
                    data = _post_curl(payload)  # 受限网络回退
            if "error" in data:
                raise LLMError(str(data["error"])[:300])
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content.strip():
                raise LLMError("模型返回空内容（可能是 max_tokens 被推理消耗）")
            return content
        except LLMError as e:
            msg_txt = str(e)
            # 仅明确的鉴权/参数类 4xx 不重试；429 限流与其余 5xx 必须重试
            # （此前用 "HTTP 4" 子串匹配，把 429 也误判为不重试）
            if msg_txt.startswith(("HTTP 400", "HTTP 401", "HTTP 403", "HTTP 404", "HTTP 422")):
                raise
            last_err = e
            time.sleep(min(2 ** attempt, 8))
        except Exception as e:  # 网络类错误，重试
            last_err = e
            time.sleep(min(2 ** attempt, 8))
    raise LLMError(f"LLM 调用失败：{last_err}")
