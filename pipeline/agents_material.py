# pipeline/agents_material.py —— 素材 Agent（v1.1.2：批量检索）
# 改动：N 次工具调用（N 个子进程）→ 1 次批量调用（1 个子进程），省子进程启动与节点重建
import json

def create_material_node(material_tools):
    # material_tools 现在有两个工具：search_material + search_material_batch
    # 按名字找批量工具（别用下标 material_tools[0]——顺序不保证）
    batch_tool = next(t for t in material_tools if t.name == "search_material_batch")

    async def material_node(state):
        shots = (state.get("storyboard") or {}).get("shots", [])
        needs = [s.get("material_need", "") for s in shots if s.get("material_need")]
        if not needs:
            return {"material_hits": {}}

        # ① 一次调用，把全部需求打包发给 MCP server
        raw = await batch_tool.ainvoke({"queries": needs, "top_k": 2})

        # ② 归一化返回值：MCP adapter 可能返回 str，也可能返回 content blocks 列表
        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, list):
            text = "".join(c.get("text", "") for c in raw if isinstance(c, dict))
        else:
            text = str(raw)

        # ③ server 返回的是 JSON 字符串：{需求: 命中文本}
        try:
            hits = json.loads(text)
            if not isinstance(hits, dict):
                raise ValueError("非字典")
        except Exception:
            # 降级：解析失败就把原始文本全部塞给每个需求（链路不断）
            hits = {need: text[:200] for need in needs}

        print(f"  ▶ 批量素材检索：{len(needs)} 个需求一次完成")
        for k, v in hits.items():
            print(f"    [{k[:12]}…] → {str(v)[:50]}…")
        return {"material_hits": hits}
    return material_node
