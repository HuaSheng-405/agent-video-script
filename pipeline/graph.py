# pipeline/graph.py —— 流水线组装表（可插拔的核心）
# 原则：增删/替换 Agent 只改这个文件；各 Agent 模块只管自己的实现
from langgraph.graph import StateGraph, START, END
from pipeline.state import PipelineState
from pipeline.agents_planner import create_planner
from pipeline.agents_writer import build_writer_subgraph
from pipeline.agents_storyboard import create_storyboard_node
from pipeline.agents_material import create_material_node
from pipeline.agents_media import create_media_node
from pipeline.agents_qc import create_qc_node
from structured_spec import generate_spec, validate_spec

def build_pipeline(llm, material_tools, media_tools=None):
    """五段式流水线：策划 → 编剧子图 → 分镜 → 素材(文本) → 素材(视频) → 质检(回退) → 成片规格
    v1.2.1：media_tools 为 None 时跳过视频（纯文本模式，仍可跑）"""

    # ---- 各 Agent 实例化（工厂依赖注入） ----
    plan_node = create_planner(llm, material_tools)
    writer_sub = build_writer_subgraph(llm)
    storyboard_node = create_storyboard_node(llm)
    material_node = create_material_node(material_tools)
    media_node = create_media_node(media_tools)
    qc_node = create_qc_node(llm)

    # ---- 组装节点（属于图的编排逻辑，不放 Agent 模块里） ----
    def write_node(state):
        r = writer_sub.invoke({"plan": state["plan"], "feedback": state.get("qc_report", "")})
        print("\n===== 编剧子图输出 =====\n", r["script"][:200], "...")
        return {"script": r["script"]}

    def spec_node(state):
        """组装（v1.1.1）：脚本 + 分镜 Agent 的镜头表 + 素材命中 → 成片规格
        镜头表直接复用分镜 Agent 产物（单一数据源），LLM 只产出四个文案字段"""
        hits = state.get("material_hits", {})
        extra = "\n".join(f"需[{k[:12]}] → {v[:80]}" for k, v in hits.items()) if hits else ""
        shots = (state.get("storyboard") or {}).get("shots", [])
        try:
            spec = generate_spec(llm, state["script"], storyboard_shots=shots, extra_context=extra)
        except Exception as e:
            print(f"⚠ 成片规格组装失败（降级为 None）：{e}")
            return {"spec": None, "spec_error": str(e)}
        issues = validate_spec(spec)
        print("\n===== 成片规格（ScriptSpec）=====")
        print(spec.model_dump_json(indent=2))
        print("规格业务校验:", issues if issues else "✅ 通过")
        return {"spec": spec.model_dump(), "spec_error": None}

    def route_after_qc(state) -> str:
        """分级回退（v1.1）：分镜问题→重分镜；脚本问题→重写；全过→规格"""
        lines = state["qc_report"].split("\n")
        script_fail = "✅ 通过" not in lines[0]
        sb_fail = "✅ 通过" not in lines[1]
        if state["retry_count"] <= 2:
            if sb_fail:
                print(f">>> 分镜问题，回退重分镜（第 {state['retry_count']} 次，不重写脚本）")
                return "storyboard"
            if script_fail:
                print(f">>> 脚本问题，回退重写（第 {state['retry_count']} 次）")
                return "write"
        else:
            print(">>> 重试超限，强制放行（仍转成片规格）")
        return "spec"

    # ---- 图组装（可插拔表：加一个 Agent 就在这加一行） ----
    g = StateGraph(PipelineState)
    g.add_node("plan", plan_node)
    g.add_node("write", write_node)
    g.add_node("storyboard", storyboard_node)
    g.add_node("material", material_node)
    g.add_node("media", media_node)
    g.add_node("qc", qc_node)
    g.add_node("spec", spec_node)
    g.add_edge(START, "plan")
    g.add_edge("plan", "write")
    g.add_edge("write", "storyboard")
    g.add_edge("storyboard", "material")
    g.add_edge("material", "media")
    g.add_edge("media", "qc")
    g.add_conditional_edges("qc", route_after_qc, {"write": "write", "storyboard": "storyboard", "spec": "spec"})
    g.add_edge("spec", END)
    return g.compile()
