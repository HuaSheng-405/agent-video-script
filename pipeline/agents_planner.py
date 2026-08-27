# pipeline/agents_planner.py —— 策划 Agent（模块一）
# 工厂模式：依赖注入（llm/material_tools 显式传入）→ 返回「图节点函数」
# 可插拔：换 Agent 实现只改这里，graph.py 的表格不用动（接口不变）
from langchain.agents import create_agent

def create_planner(llm, material_tools):
    """工厂：返回 plan_node（依赖注入后即可单独测试）"""
    planner = create_agent(
        llm, tools=material_tools,
        system_prompt=(
            "你是短视频选题策划专家。先调用 search_material 检索相关素材，"
            "再基于素材给出：① 标题（含钩子）② 大纲（3 要点，标注素材来源）。"
            "只输出策划，不写脚本。"
        ),
    )

    async def plan_node(state):
        result = await planner.ainvoke({"messages": [("user", f"主题：{state['topic']}")]})
        plan = result["messages"][-1].content
        print("\n===== 策划（含素材参考）=====\n", plan)
        return {"plan": plan}

    return plan_node
