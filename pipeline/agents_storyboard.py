# pipeline/agents_storyboard.py —— 分镜 Agent（模块三：v1.1 新增）
# 脚本 → 镜头表（结构化：镜号/时段/画面/口播词/素材需求）
# 复用 structured_spec 的 Schema + with_structured_output 校验重试模式
import re
from structured_spec import StoryboardSchedule, generate_storyboard

def create_storyboard_node(llm):
    def storyboard_node(state):
        try:
            schedule = generate_storyboard(llm, state["script"])
        except Exception as e:
            print(f"⚠ 分镜生成失败（降级为空镜头表）：{e}")
            return {"storyboard": {"shots": []}}
        issues = validate_storyboard(schedule.model_dump())
        print("\n===== 分镜 Agent（镜头表）=====")
        for s in schedule.shots:
            print(f"  [{s.shot_no:02d}] {s.start}｜{s.scene[:24]}… | 参考需求：{s.material_need[:20]}")
        print("镜头数校验:", issues if issues else f"✅ {len(schedule.shots)} 镜")
        return {"storyboard": schedule.model_dump(), "storyboard_issues": issues}
    return storyboard_node

# 校验：分镜是后续素材 Agent 的输入，必须规则化兜底
def validate_storyboard(storyboard: dict) -> list[str]:
    issues = []
    shots = storyboard.get("shots", [])
    if not (3 <= len(shots) <= 8):
        issues.append(f"镜头数 {len(shots)} 不在 3~8")
    return issues
