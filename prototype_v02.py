# prototype_v02.py —— 薄入口：只负责装配与运行（逻辑全部移到 pipeline/ 包）
# 接口保持兼容：run_topic(topic, material_tools=None) / LLM_ENV_PY / MATERIAL_SERVER（eval_run 依赖）
import asyncio
from langchain_deepseek import ChatDeepSeek
from langchain_mcp_adapters.client import MultiServerMCPClient
from pipeline.graph import build_pipeline

# 运行时按机器调整
LLM_ENV_PY = r"E:/Anaconda/envs/llm/python.exe"
MATERIAL_SERVER = r"D:/learn/llm/rag-video-script/material_server.py"

llm = ChatDeepSeek(model="deepseek-chat")

async def run_topic(topic: str, material_tools: list | None = None) -> dict:
    if material_tools is None:
        mcp_client = MultiServerMCPClient({
            "material": {"command": LLM_ENV_PY, "args": [MATERIAL_SERVER], "transport": "stdio"},
        })
        material_tools = await mcp_client.get_tools()
        print("检索工具已接入:", [t.name for t in material_tools])
    team = build_pipeline(llm, material_tools)
    return await team.ainvoke({"topic": topic, "retry_count": 0})

if __name__ == "__main__":
    asyncio.run(run_topic("给大学生讲清楚什么是RAG"))
