# 视频脚本 Agent 助手（agent-video-script）

> 从 0 到 1：把「主题 → 60 秒视频口播脚本」自动化的多 Agent 流水线产品。
> 架构：LangGraph 多 Agent 流水线 + MCP 工具协议 + 两层质检，素材检索复用 rag-video-script 检索层。

## 架构

```mermaid
flowchart LR
    A[用户主题] --> P[策划 Agent<br/>先查素材再策划]
    P --> S[编剧子图<br/>大纲→初稿→润色]
    S --> Q[质检<br/>规则层+LLM打分层]
    Q -- "FAIL(≤2次回退)" --> S
    Q -- PASS --> R[输出脚本]
    P -. 跨进程 MCP .-> M[素材检索服务<br/>rag-video-script 检索层]
```

## 快速开始

前置：克隆 rag-video-script 并安装其依赖（检索服务复用其语料与 hybrid 检索）。

```bash
# 1. 检索服务依赖（llm 环境）
E:\Anaconda\envs\llm\python.exe -m pip install mcp

# 2. 主进程依赖
pip install langchain langchain-deepseek langgraph langchain-mcp-adapters python-dotenv

# 3. 运行（先确保 rag-video-script/material_server.py 存在）
python prototype_v02.py
```

## 设计决策（详见 docs/decisions.md）

| 决策 | 选择 | 理由 |
|---|---|---|
| 编排 | 父图固定流水线 + 编剧子图 | 生产流程强顺序，显式可控；子图封装编剧内部三步 |
| 质检 | 规则层(代码) + LLM 打分层(1-5) | LLM 硬判 PASS/FAIL 实测会标准漂移（详见博客） |
| 素材检索 | MCP 跨进程调用 | 环境隔离（检索=llm 环境，Agent=python3.11），复用已有检索层 |
| 回退 | ≤2 次后强制放行 | 防死循环烧 token |
| 模型分级 | 创作节点 deepseek-chat | 质量优先；本地模型可兜底 |

## 评估（20 题端到端，`eval_run.py`）

| 指标 | 基线 V1 | 改进后 | 关键改动 |
|---|---|---|---|
| 一次通过率 | 45% | **100%**（本轮样本） | 编剧 prompt 加「口播词 250 字」硬约束 |
| 平均回退 | 0.70 次 | **0.00 次** | 同上（直击头号失败原因：字数超标） |
| 成片规格生成率 | 100% | 100% | — |
| 规格校验通过率 | 95% | 100% | — |
| 平均耗时 | 136s | 137s | 索引复用后稳定 |

> 评估驱动迭代闭环：基线 45% → 失败原因分析（字数超标为头号杀手）→ 针对性改进（硬约束）→ 复测 100%。数据见 `eval_result.json`。

## 当前版本

- **v1.0（2026-08-26）✅**：策划（MCP 素材检索）→ 编剧子图 → 两层质检（规则+LLM 打分）→ 成片规格（ScriptSpec 结构化输出），回退环 + 防死循环；20 题端到端评估体系
- 设计决策与踩坑记录：`docs/decisions.md`
- 已知限制：① 单轮样本内 100%，长期稳定需多轮扩题验证 ② 分镜/素材暂合并于规格与策划环节（独立 Agent 列入 v1.1）③ 索引仅首次构建数分钟，之后复用

## 相关

- 素材检索层：[rag-video-script](https://github.com/HuaSheng-405/rag-video-script)（Recall@5=1.0 / MRR@5=0.87）
- 学习过程：[agent-learning](https://github.com/HuaSheng-405/agent-learning)（day01-11 实验）
