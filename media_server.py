# media_server.py —— Pexels 视频素材 MCP server（v1.2.1，独立于 text 检索）
# 提供 search_videos_batch（一次会话批量查询，避免 N 次子进程）
# 运行环境：主环境（python3.11，有 httpx；PEXELS_API_KEY 在 .env）
import os, sys, json
# Windows 控制台 cp936 无法编码 ▶/⚠，重配 utf-8 防子进程也崩
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import httpx
from mcp.server.fastmcp import FastMCP

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
mcp = FastMCP("video-search")

def _search(query: str, per_page: int = 5) -> list[dict]:
    """检索 Pexels 视频，返回结构化候选（供 UI 选择/本地合成）"""
    if not PEXELS_API_KEY:
        print("⚠ 未配置 PEXELS_API_KEY", file=sys.stderr, flush=True)
        return []
    r = httpx.get("https://api.pexels.com/videos/search",
                  params={"query": query, "per_page": per_page},
                  headers={"Authorization": PEXELS_API_KEY}, timeout=20)
    r.raise_for_status()
    data = r.json()
    out = []
    for v in data.get("videos", []):
        files = v.get("video_files", [])
        # 选分辨率最优的可下载文件
        best = max(files, key=lambda f: (f.get("quality") == "hd", f.get("height", 0))) if files else {}
        out.append({
            "video_id": v.get("id"),
            "duration": v.get("duration", 0),
            "thumbnail_url": v.get("image", ""),
            "video_url": best.get("link", "") or v.get("url", ""),
        })
    return out

@mcp.tool()
def search_videos_batch(queries: list[str], per_page: int = 5) -> str:
    """按视觉关键词批量检索视频，返回 JSON：{query: [候选video]}"""
    return json.dumps({q: _search(q, per_page) for q in queries}, ensure_ascii=False)

@mcp.tool()
def search_videos(query: str, per_page: int = 5) -> str:
    """单个关键词检索视频"""
    return json.dumps(_search(query, per_page), ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
