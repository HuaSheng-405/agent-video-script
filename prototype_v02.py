# prototype_v02.py —— 薄入口：只负责装配与运行（逻辑全部移到 pipeline/ 包）
# 接口保持兼容：run_topic(topic, material_tools=None, media_tools=None) / LLM_ENV_PY / MATERIAL_SERVER / MEDIA_SERVER
import asyncio, os, sys
from pathlib import Path
# Windows 控制台默认 cp936，▶/⚠/✅ 不在 GBK 里，会抛 UnicodeEncodeError 崩掉整条链
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
# 加载 .env（langchain_deepseek 认无下划线的 DEEPSEEK_API_KEY）
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
from langchain_deepseek import ChatDeepSeek
from langchain_mcp_adapters.client import MultiServerMCPClient
from pipeline.graph import build_pipeline

# 运行时按机器调整
LLM_ENV_PY = r"E:/Anaconda/envs/llm/python.exe"
MATERIAL_SERVER = r"D:/learn/llm/rag-video-script/material_server.py"
# 相对脚本定位，改名/换目录后仍有效
MEDIA_SERVER = str(Path(__file__).parent / "media_server.py")

llm = ChatDeepSeek(model="deepseek-chat")

async def run_topic(topic: str, material_tools: list | None = None,
                    media_tools: list | None = None) -> dict:
    if material_tools is None:
        mcp_client = MultiServerMCPClient({
            "material": {"command": LLM_ENV_PY, "args": [MATERIAL_SERVER], "transport": "stdio"},
        })
        material_tools = await mcp_client.get_tools()
        print("检索工具已接入:", [t.name for t in material_tools])
    if media_tools is None:
        media_client = MultiServerMCPClient({
            "media": {"command": sys.executable, "args": [MEDIA_SERVER], "transport": "stdio"},
        })
        media_tools = await media_client.get_tools()
        print("视觉检索工具已接入:", [t.name for t in media_tools])
    team = build_pipeline(llm, material_tools, media_tools)
    return await team.ainvoke({"topic": topic, "retry_count": 0})

if __name__ == "__main__":
    asyncio.run(run_topic("给大学生讲清楚什么是RAG"))
