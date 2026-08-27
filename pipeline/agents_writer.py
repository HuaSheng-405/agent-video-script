# pipeline/agents_writer.py —— 编剧子图（模块二：大纲→初稿→润色）
# 子图对父图黑盒：只暴露 invoke({"plan", "feedback"}) -> {"script"}
from langgraph.graph import StateGraph, START, END
from pipeline.state import ScriptState

def build_writer_subgraph(llm):
    def outline_node(s: ScriptState) -> dict:
        msg = f"根据策划列出 3 点大纲：\n{s['plan']}"
        if s.get("feedback"):
            msg += f"\n\n【质检批注，请针对性改进】\n{s['feedback']}"
        return {"outline": llm.invoke(msg).content}

    def draft_node(s: ScriptState) -> dict:
        # v1.1 保留字数硬约束（45%→100% 的关键改进，勿删）
        return {"draft": llm.invoke(
            f"根据大纲写 60 秒口播初稿（开头 3 秒钩子，结尾 CTA。"
            f"【硬约束】口播词 250 字左右，宁少勿多，删掉所有铺垫性重复）\n{s['outline']}").content}

    def polish_node(s: ScriptState) -> dict:
        r = llm.invoke([("system", "你是润色师，把初稿改得更口语化、更紧凑，保留钩子和 CTA。"),
                        ("user", f"初稿：\n{s['draft']}")])
        return {"script": r.content}

    b = StateGraph(ScriptState)
    b.add_node("outline", outline_node)
    b.add_node("draft", draft_node)
    b.add_node("polish", polish_node)
    b.add_edge(START, "outline"); b.add_edge("outline", "draft")
    b.add_edge("draft", "polish"); b.add_edge("polish", END)
    return b.compile()
