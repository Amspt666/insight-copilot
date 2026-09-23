import json
import os
import time

import requests

from . import config


class ModelError(RuntimeError):
    pass


class ModelFormatError(ModelError):
    pass


def chat_json(messages: list[dict], max_tokens=2600) -> dict:
    if not config.API_KEY:
        raise ModelError('未配置 DeepSeek 模型密钥，请在 v1.1/.env 配置有效的 LLM_API_KEY 后重启服务。')
    payload = {'model': config.MODEL, 'messages': messages, 'stream': False,
               'temperature': 0, 'max_tokens': max_tokens,
               'response_format': {'type': 'json_object'}}
    if os.getenv('LLM_THINKING', '').lower() in ('off', '0', 'false', 'disabled'):
        payload['thinking'] = {'type': 'disabled'}
    for attempt in range(config.RETRIES):
        try:
            response = requests.post(config.BASE_URL + '/chat/completions',
                                     headers={'Authorization': 'Bearer ' + config.API_KEY},
                                     json=payload, timeout=(10, config.TIMEOUT))
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < config.RETRIES:
                    time.sleep(attempt + 1)
                    continue
            if not response.ok:
                raise ModelError(f'模型服务返回 HTTP {response.status_code}；请检查模型配置或稍后重试。')
            result = response.json()
            content = result['choices'][0]['message']['content']
            if not isinstance(content, str) or len(content) > 40000:
                raise ValueError('invalid content')
            if content.strip().startswith('```'):
                content = content.strip().split('\n', 1)[1].rsplit('```', 1)[0]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError('expected object')
            return parsed
        except (requests.Timeout, requests.ConnectionError):
            if attempt + 1 == config.RETRIES:
                raise ModelError('模型连接失败或超时，请重试；没有生成查询结果。') from None
            time.sleep(attempt + 1)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelFormatError('模型没有返回有效的 JSON 对象，请重试。') from None
        except requests.RequestException:
            raise ModelError('模型请求失败，请检查接口配置。') from None
    raise ModelError('模型调用失败。')
