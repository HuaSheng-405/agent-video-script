# prototype_v02.py —— 视频脚本 Agent 生产线 v0.2（主项目验证性原型）
# 结构：策划(带检索工具) → 编剧(子图: 大纲→初稿→润色) → 质检(规则层+LLM打分层) → FAIL 回退(≤2次)
# 素材检索：MCP 调用 rag-video-script/material_server.py（跨环境，检索进程 = llm env）
import asyncio, os, re
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
from typing import TypedDict, Annotated
from langchain_deepseek import ChatDeepSeek
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_mcp_adapters.client import MultiServerMCPClient
from structured_spec import generate_spec, validate_spec

# 运行时按机器调整
LLM_ENV_PY = r"E:/Anaconda/envs/llm/python.exe"
MATERIAL_SERVER = r"D:/learn/llm/rag-video-script/material_server.py"

llm = ChatDeepSeek(model="deepseek-chat")

class ScriptState(TypedDict):
    plan: str
    outline: str
    draft: str
    script: str
    feedback: str

def outline_node(s: ScriptState) -> dict:
    msg = f"根据策划列出 3 点大纲：\n{s['plan']}"
    if s.get("feedback"):
        msg += f"\n\n【质检批注，请针对性改进】\n{s['feedback']}"
    return {"outline": llm.invoke(msg).content}

def draft_node(s: ScriptState) -> dict:
    return {"draft": llm.invoke(
        f"根据大纲写 60 秒口播初稿（开头 3 秒钩子，结尾 CTA。"
        f"口播词 250 字左右，宁少勿多，删掉所有铺垫性重复）\n{s['outline']}").content}

def polish_node(s: ScriptState) -> dict:
    r = llm.invoke([("system", "你是润色师，把初稿改得更口语化、更紧凑，保留钩子和 CTA。"),
                    ("user", f"初稿：\n{s['draft']}")])
    return {"script": r.content}

def build_writer_subgraph():
    b = StateGraph(ScriptState)
    b.add_node("outline", outline_node)
    b.add_node("draft", draft_node)
    b.add_node("polish", polish_node)
    b.add_edge(START, "outline"); b.add_edge("outline", "draft")
    b.add_edge("draft", "polish"); b.add_edge("polish", END)
    return b.compile()

def rule_check(text: str):
    import re
    spoken = re.sub(r"【[^】]*】|（[^）]*）|[#*>\-|=]|\d+-\d+秒|[\U0001F300-\U0001FAFF]", "", text)
    n = len(spoken)
    issues = []
    if not (150 <= n <= 450):
        issues.append(f"口播词 {n} 字，目标 250 字左右——请删减铺垫和重复例子，保留钩子与核心类比")
    if not re.search(r"(关注|点赞|评论|扣|私信|转发)", text):
        issues.append("缺少 CTA——请在结尾补一句互动号召")
    return (len(issues) == 0), issues

def llm_score(text: str) -> int:
    r = llm.invoke(f"给以下短视频脚本的【开头钩子】吸引力打分（1-5 的整数）：\n{text[:150]}\n只输出一个 1-5 的数字。")
    m = re.search(r"[1-5]", r.content)
    return int(m.group()) if m else 3

class State(TypedDict):
    topic: str
    plan: str
    script: str
    spec: dict          # v1.0：成片规格（结构化输出）
    spec_error: str     # v1.0：规格生成失败的错误记录（None=成功）
    first_fail_reason: str   # 首次质检失败原因（评估用；只记录第一条）
    qc_report: str
    retry_count: int
    messages: Annotated[list, add_messages]

async def run_topic(topic: str, material_tools: list | None = None) -> dict:
    """跑一个主题，返回最终状态（评估体系复用此函数）
    material_tools 传入已加载的工具时复用（同一 MCP 连接/同一索引），否则自建"""
    if material_tools is None:
        mcp_client = MultiServerMCPClient({
            "material": {"command": LLM_ENV_PY, "args": [MATERIAL_SERVER], "transport": "stdio"},
        })
        material_tools = await mcp_client.get_tools()
        print("检索工具已接入:", [t.name for t in material_tools])

    planner = create_agent(
        llm, tools=material_tools,
        system_prompt=(
            "你是短视频选题策划专家。先调用 search_material 检索相关素材，"
            "再基于素材给出：① 标题（含钩子）② 大纲（3 要点，标注素材来源）。"
            "只输出策划，不写脚本。"
        ),
    )
    writer_sub = build_writer_subgraph()

    async def plan_node(state: State) -> dict:
        result = await planner.ainvoke({"messages": [("user", f"主题：{state['topic']}")]})
        print("\n===== 策划（含素材参考）=====\n", result["messages"][-1].content)
        return {"plan": result["messages"][-1].content}

    def write_node(state: State) -> dict:
        r = writer_sub.invoke({"plan": state["plan"], "feedback": state.get("qc_report", "")})
        print("\n===== 编剧子图输出 =====\n", r["script"][:200], "...")
        return {"script": r["script"]}

    def qc_node(state: State) -> dict:
        text = state["script"]
        ok, issues = rule_check(text)
        score = llm_score(text)
        report = f"规则层：{'✅ 通过' if ok else '❌ ' + '；'.join(issues)}\nLLM 钩子评分：{score}/5"
        print("\n===== 质检报告 =====\n" + report)
        retry = state.get("retry_count", 0)
        if not (ok and score >= 3):
            retry += 1
            # 评估用：只记录【首次】失败原因（后续重试的最终报告会覆盖 qc_report）
            if not state.get("first_fail_reason"):
                reason = "；".join(issues) if issues else f"钩子评分 {score}/5"
                return {"qc_report": report, "retry_count": retry,
                        "first_fail_reason": f"❌ {reason}"}
        return {"qc_report": report, "retry_count": retry}

    def spec_node(state: State) -> dict:
        """v1.0 组件一：脚本文本 → 结构化成片规格（校验失败自动重试 ≤3）
        增强：3 次仍失败 → 降级为 spec=None（记录错误，不中断整条流水线）"""
        try:
            spec = generate_spec(llm, state["script"])
        except Exception as e:
            print(f"⚠ 成片规格生成失败（降级为 None）：{e}")
            return {"spec": None, "spec_error": str(e)}
        issues = validate_spec(spec)
        print("\n===== 成片规格（ScriptSpec）=====")
        print(spec.model_dump_json(indent=2))
        print("规格业务校验:", issues if issues else "✅ 通过")
        return {"spec": spec.model_dump(), "spec_error": None}

    def route_after_qc(state: State) -> str:
        lines = state["qc_report"].split("\n")
        rule_ok = "✅ 通过" in lines[0]
        m = re.search(r"(\d)/5", lines[-1])
        score = int(m.group(1)) if m else 0
        passed = rule_ok and score >= 3
        if not passed and state["retry_count"] <= 2:
            print(f">>> 回退重写（第 {state['retry_count']} 次）")
            return "write"
        if not passed:
            print(">>> 重试超限，强制放行（仍转成片规格）")
        return "spec"   # 通过或强制放行 → 都生成成片规格

    g = StateGraph(State)
    g.add_node("plan", plan_node)
    g.add_node("write", write_node)
    g.add_node("qc", qc_node)
    g.add_node("spec", spec_node)
    g.add_edge(START, "plan"); g.add_edge("plan", "write"); g.add_edge("write", "qc")
    g.add_conditional_edges("qc", route_after_qc, {"write": "write", "spec": "spec"})
    g.add_edge("spec", END)
    team = g.compile()
    return await team.ainvoke({"topic": topic, "retry_count": 0})

if __name__ == "__main__":
    asyncio.run(run_topic("给大学生讲清楚什么是RAG"))
