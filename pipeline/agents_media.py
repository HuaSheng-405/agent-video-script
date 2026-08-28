# pipeline/agents_media.py —— 视觉素材 Agent（v1.2.1 新增，独立节点）
# 分镜的 visual_keywords → Pexels 视频检索 → video_candidates（供 UI 选择 / 本地合成）
# 关键：批量调用（一次会话，避免 N 次子进程）+ 时长 ±50% 过滤并按贴近镜头时长排序
import json, re

def _shot_duration_sec(start: str) -> int:
    """从 '0-8s' 解析镜头时长（秒）"""
    m = re.search(r"(\d+)-(\d+)s", start or "")
    return (int(m.group(2)) - int(m.group(1))) if m else 8

def create_media_node(media_tools):
    if not media_tools:
        def noop(state):
            print("⚠ 未接入 Pexels，跳过视频候选（文本模式仍可用）")
            return {"video_candidates": {}}
        return noop

    batch_tool = next(t for t in media_tools if t.name == "search_videos_batch")

    async def media_node(state):
        shots = (state.get("storyboard") or {}).get("shots", [])
        items = [{"shot_no": s.get("shot_no"), "keywords": s.get("visual_keywords") or [],
                  "duration": _shot_duration_sec(s.get("start", ""))} for s in shots]
        queries = list(dict.fromkeys(k for i in items for k in i["keywords"]))
        if not queries:
            return {"video_candidates": {}}
        # 一次会话查所有关键词
        raw = await batch_tool.ainvoke({"queries": queries, "per_page": 5})
        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, list):
            text = "".join(c.get("text", "") for c in raw if isinstance(c, dict))
        else:
            text = str(raw)
        try:
            hits = json.loads(text)
        except Exception:
            hits = {}

        candidates = {}
        for it in items:
            pool = []
            for kw in it["keywords"]:
                pool += hits.get(kw, [])
            seen, filtered = set(), []
            lo, hi = it["duration"] * 0.5, it["duration"] * 1.5
            for c in pool:
                cid = c.get("video_id")
                if cid in seen:
                    continue
                seen.add(cid)
                d = c.get("duration", 0)
                if lo <= d <= hi:          # 时长 ±50% 过滤
                    filtered.append(c)
            filtered.sort(key=lambda c: abs(c.get("duration", 0) - it["duration"]))  # 越贴近镜头时长越靠前
            candidates[it["shot_no"]] = filtered[:5]
            print(f"  ▶ 视频候选 镜{it['shot_no']}（目标 {it['duration']}s）：{len(filtered)} 个")
        return {"video_candidates": candidates}
    return media_node
