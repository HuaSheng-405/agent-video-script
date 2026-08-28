# pipeline/state.py —— 全流水线的唯一数据契约
# 原则：所有 State 集中定义，避免模块间循环 import；哪些字段在哪个阶段写，注释标注
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

# ========== 编剧子图 State（内部私有，父图不需要知道） ==========
class ScriptState(TypedDict):
    plan: str
    outline: str
    draft: str
    script: str
    feedback: str   # 质检批注（回退时注入）

# ========== 流水线 State（父图，全链路共享） ==========
class PipelineState(TypedDict):
    topic: str
    # 策划阶段
    plan: str
    # 编剧阶段
    script: str
    # 分镜阶段（v1.1 新增）
    storyboard: dict             # StoryboardSchedule（镜头表）
    storyboard_issues: list      # 分镜校验问题（汇入质检决策，v1.1 分层回退）
    # 素材阶段（v1.1 新增）
    material_hits: dict          # {素材需求: 检索命中摘要}
    # 视觉素材阶段（v1.2.1 新增，独立节点）
    video_candidates: dict       # {镜号: [VideoCandidate]}（Pexels 候选，供 UI 选择/本地合成）
    # 规格阶段
    spec: dict                   # ScriptSpec（成片规格）
    spec_error: str              # 规格生成失败记录（None=成功）
    # 质检阶段
    qc_report: str
    first_fail_reason: str
    retry_count: int
    # 对话历史（create_agent 内部使用）
    messages: Annotated[list, add_messages]
