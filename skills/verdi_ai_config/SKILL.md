---
name: verdi_ai_config
description: >
  Verdi AI/LLM 本地模型 URL 配置指南: 通过 OPENAI_BASE_URL 配置
  Ollama/vLLM/任意 OpenAI 兼容端点。支持 GPT/Llama/Qwen/Gemini/
  Claude/GLM/Kimi/Mixtral 40+ 模型。从 llm_info.json 提取。
version: 1.0.0
---
# Verdi AI Assistant — 本地模型 URL 配置指南

## 配置原理

Verdi AI Assistant 使用 **OpenAI Python 客户端库** (`openai.OpenAI`) 连接 LLM。
因此配置本地模型只需设置标准 OpenAI 环境变量：

```
┌─────────────────────────────────────────────────────┐
│  Verdi AI Assistant                                  │
│  ($VERDI_HOME/bin/agentic)                          │
│                                                      │
│  ┌──────────────────┐    ┌───────────────────────┐ │
│  │ verdilearn/vllm  │    │ openai.OpenAI client  │ │
│  │ _engine.py       │───▶│ OPENAI_BASE_URL ──────│─┼──▶ Local Model
│  │ llm_info.json    │    │ OPENAI_API_KEY        │ │    (Ollama/vLLM/etc)
│  └──────────────────┘    └───────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 快速配置

### 方法 1: Ollama 本地模型
```bash
# 1. 启动 Ollama 并拉取模型
ollama pull qwen3:8b

# 2. 设置环境变量
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="ollama"       # Ollama 不需要真实 key

# 3. 启用 Verdi AI Assistant
export VERDI_ASSISTANT_ENABLE=1
export VERDI_AGENTIC_DISABLE_REDIRECT=1

# 4. 启动 Verdi
verdi
```

### 方法 2: vLLM 本地服务
```bash
# 1. 启动 vLLM 服务
python -m vllm.entrypoints.openllm_server \
    --model /path/to/model \
    --port 8000

# 2. 设置环境变量
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="local"

# 3. 启动 Verdi
export VERDI_ASSISTANT_ENABLE=1
verdi
```

### 方法 3: 任何 OpenAI 兼容 API
```bash
export OPENAI_BASE_URL="http://your-server:8080/v1"
export OPENAI_API_KEY="your-key"
export VERDI_ASSISTANT_ENABLE=1
verdi
```

## 高级配置

### 自定义模型（不在 llm_info.json 中）

编辑 `$VERDI_HOME/share/NPI/python/verdilearn/vllm/llm_info.json`，
在 `COMPLETION_INFO` 中添加新模型：

```json
{
    "COMPLETION_INFO": {
        "my-local-model": {
            "token_limit": 32768,
            "engine": "OpenAICompletionEngine",
            "client_library": "openai.OpenAI",
            "response_token_limit": 8192
        }
    }
}
```

### 修改默认模型

在 `llm_info.json` 中修改 `"default"` 条目：

```json
"default": {
    "token_limit": 32768,
    "engine": "OpenAICompletionEngine",
    "client_library": "openai.OpenAI",
    "response_token_limit": 8192
}
```

### 环境变量参考

| 变量 | 用途 | 示例 |
|---|---|---|
| `OPENAI_BASE_URL` | 模型端点 URL | `http://localhost:11434/v1` |
| `OPENAI_API_KEY` | API 密钥 | `ollama` / `sk-xxx` |
| `VERDI_ASSISTANT_ENABLE` | 启用 AI Assistant | `1` |
| `VERDI_AGENTIC_DISABLE_REDIRECT` | 调试模式（不重定向输出） | `1` |
| `VERDI_HOME` | Verdi 安装路径 | `/tools/Synopsys/verdi/Y-2026.03-SP2` |

## 支持的模型列表

从 `$VERDI_HOME/share/NPI/python/verdilearn/vllm/llm_info.json` 提取：

### OpenAI 系列
| 模型 | Token Limit | Engine |
|---|---|---|
| gpt-4o | 128,000 | OpenAI |
| gpt-4.1 | 128,000 | OpenAI |
| gpt-5.1 | 128,000 | OpenAI |
| gpt-5.2 | 128,000 | OpenAI |
| o1 | 200,000 | OpenAI |

### Llama 系列
| 模型 | Token Limit | Engine |
|---|---|---|
| Meta-Llama-3.1-70B-Instruct | 8,192 | Llama |
| Meta-Llama-3.3-70B-Instruct | 128,000 | Llama |

### Qwen 系列
| 模型 | Token Limit | Engine |
|---|---|---|
| qwen3-coder-480b-a35b-inst-fp8 | 262,144 | OpenAI |
| qwen3-235b-a22b-fp8 | 262,144 | OpenAI |
| qwen3-next-80b-a3b-instruct | 262,144 | OpenAI |
| qwen3.5-397b-a17b | 262,144 | OpenAI |
| qwen3.6-27b | 262,144 | OpenAI |

### Claude 系列
| 模型 | Token Limit | Engine |
|---|---|---|
| claude-sonnet-4/4.5/5 | 200,000 | OpenAI |
| claude-haiku-4.5 | 200,000 | OpenAI |
| claude-opus-4.5/4.6 | 200,000 | OpenAI |

### GLM 系列
| 模型 | Token Limit | Engine |
|---|---|---|
| GLM-4.7 | 200,000 | OpenAI |
| glm-5.1 | 200,000 | OpenAI |
| glm-5.2 | 200,000 | OpenAI |

### 其他
| 模型 | Token Limit | Engine |
|---|---|---|
| gemini-2.5-pro | 1,048,576 | OpenAI |
| Kimi-K2-Thinking | 256,000 | OpenAI |
| Mixtral-8x22B | 65,536 | Base |

### Embedding 模型
| 模型 | Engine |
|---|---|
| text-embedding-3-small/large | OpenAI |
| nomic-embed-text-v1.5 | Nomic |
| bge-large-en-v1.5 / bge-m3 | BGE |
| gemini-embedding-001 | Gemini |
| titan-embed-text-v2 | Titan |

## verdilearn 包结构

```
$VERDI_HOME/share/NPI/python/verdilearn/
├── vllm/              # LLM 引擎 (OpenAI client)
│   ├── llm_info.json  # 模型配置 (40+ models)
│   ├── _engine.py     # OpenAI/Llama/Base completion engines
│   ├── llm.so         # 编译后的 LLM 调用库
│   └── _embedding.so  # Embedding 引擎
├── agentic/           # Agentic AI 框架 (MCP server)
├── assist/            # Verdi Assistant
├── msgdb/             # Message database
├── ddt/               # Data-driven testing
├── diagnosis/         # Diagnosis engine
├── database/          # Database utilities
└── utility/           # Utilities
```

## 启动入口

| 入口 | 路径 | 用途 |
|---|---|---|
| agentic | `$VERDI_HOME/bin/agentic` | MCP server (stdio/SSE/HTTP) |
| rca_agent | `$VERDI_HOME/bin/rca_agent` | RCA analysis agent |
| verdi | `$VERDI_HOME/bin/verdi` | Verdi GUI (含 AI Assistant) |

## Pitfalls
- `OPENAI_BASE_URL` 必须以 `/v1` 结尾
- `llm_info.json` 中的模型名必须与 API 端点的模型名匹配
- 本地模型需要支持 OpenAI Chat Completions API 格式
- `VERDI_ASSISTANT_ENABLE=1` 必须设置才能启用 AI 功能
- Token limit 超过模型实际限制会被截断
- Embedding 模型需要单独配置 (EMBEDDING_INFO section)
