# structured_spec.py —— 成片规格 Schema + 结构化生成（v1.1 版）
# Schema：分镜镜头（含素材需求）/ 镜头表 / 成片规格；统一「结构化生成 + 校验重试」
from pydantic import BaseModel, Field

class StoryboardShot(BaseModel):
    shot_no: int = Field(description="镜号")
    start: str = Field(description="时间段，如 0-3s")
    scene: str = Field(description="画面描述")
    narration: str = Field(description="该时段口播词")
    material_need: str = Field(description="本镜需参考的脚本片段/需核实的事实，如：美食探店开场白怎么写")
    visual_keywords: list[str] = Field(default_factory=list, description="本镜视觉素材检索关键词（英文，2~3 个），如 ['AI chat interface','smartphone']")

class StoryboardSchedule(BaseModel):
    shots: list[StoryboardShot] = Field(description="镜头表，3~8 个镜头")

class ScriptSpec(BaseModel):
    topic: str = Field(description="视频主题")
    title: str = Field(description="标题（含钩子）")
    hook: str = Field(description="开头 3 秒钩子原文")
    storyboard: list[StoryboardShot] = Field(description="镜头表（含素材需求）")
    cta: str = Field(description="结尾行动号召")

def _invoke_structured(llm, model, prompt: str, max_attempts: int = 3):
    """结构化生成双通道降级（v1.1 实测教训：单通道会挂）：
    通道 1：with_structured_output（tool_call 机制，返回 None 表示模型未走该通道）
    通道 2：直接文本 JSON + 手动提取解析（模型偶尔不遵守 tool_call 时的兜底）
    两通道都失败 → 抛错（由调用方降级为 None 记录）"""
    structured = llm.with_structured_output(model)
    last_err = None
    for i in range(max_attempts):
        # ---- 通道 1 ----
        try:
            out = structured.invoke(prompt)
            if out is not None:
                return out if isinstance(out, model) else model.model_validate(out)
        except Exception as e:
            last_err = e
            print(f"⚠ 通道1 失败（第 {i + 1} 次）：{e}")
        # ---- 通道 2：绕过 tool_call，直接索要 JSON 文本 ----
        try:
            import json, re
            txt = llm.invoke(prompt + "\n\n严格只输出一个 JSON 对象，不要任何其他文字。").content
            m = re.search(r"\{.*\}", txt, re.S)
            if m:
                out = model.model_validate(json.loads(m.group(0)))
                print(f"  ↳ 通道2 JSON 解析成功")
                return out
            print(f"⚠ 通道2 无 JSON 内容（第 {i + 1} 次）")
        except Exception as e2:
            last_err = e2
            print(f"⚠ 通道2 失败（第 {i + 1} 次）：{e2}")
    raise RuntimeError(f"{model.__name__} 生成 {max_attempts} 次（双通道）均失败：{last_err}")

def generate_storyboard(llm, script_text: str) -> StoryboardSchedule:
    """脚本 → 镜头表（分镜 Agent 使用）"""
    return _invoke_structured(llm, StoryboardSchedule,
        f"将以下口播脚本拆分为镜头表（每镜头：镜号/时间段/画面描述/口播词/素材需求/视觉关键词）。"
        f"【硬约束】严格 3~8 个镜头，60 秒视频每个镜头 5~15 秒。"
        f"【material_need 定义】必须写成『需参考哪类脚本片段/需核实哪个事实』，例如『关于AI幻觉的脚本写法』"
        f"『开卷考试类比的脚本参考』——不要写成画面素材需求（如截图/动效），因为素材库是文字脚本。"
        f"【visual_keywords 定义】本镜面画对应的英文视觉检索关键词 2~3 个（用于 Pexels 视频检索），"
        f"例如美食探店镜头 → ['food vlog','restaurant','cooking'];数字人出镜镜头 → ['AI presenter','digital avatar']。"
        f"只写能真正搜到视频的泛化词，不要写极具体/抽象词。\n{script_text}")

class SpecMeta(BaseModel):
    """规格组装只需要 LLM 生成这四个文案字段（镜头表由分镜 Agent 提供，不重造）"""
    topic: str = Field(description="视频主题")
    title: str = Field(description="标题（含钩子）")
    hook: str = Field(description="开头 3 秒钩子原文")
    cta: str = Field(description="结尾行动号召")

def generate_spec(llm, script_text: str, storyboard_shots: list[dict], extra_context: str = "") -> ScriptSpec:
    """组装（v1.1.1）：LLM 只产出 SpecMeta，镜头表直接采用分镜 Agent 的产物
    为什么：让 LLM 重新拆镜头 = 重复劳动 + 与已质检镜头表不一致 + 校验波动（实测 3/20 校验失败）"""
    meta = _invoke_structured(llm, SpecMeta,
        f"根据脚本产出成片规格的四个文案字段：\n{script_text}\n"
        + (f"\n【素材命中参考】\n{extra_context}" if extra_context else ""))

    # 程序化组装（确定性，不再依赖 LLM 的镜头拆分）
    shots = []
    for i, s in enumerate(storyboard_shots, start=1):
        shot = StoryboardShot(
            shot_no=s.get("shot_no", i),
            start=s.get("start", ""),
            scene=s.get("scene", ""),
            narration=s.get("narration", ""),
            material_need=s.get("material_need", ""),
            visual_keywords=s.get("visual_keywords", []),
        )
        shots.append(shot)

    # 素材命中标注（确定性拼接，不依赖 LLM）
    for line in extra_context.split("\n") if extra_context else []:
        if "→" in line:
            need_part, src = line.split("→", 1)
            need_key = need_part.split("需[")[-1].rstrip("]") if "需[" in line else need_part.strip()
            for shot in shots:
                if need_key[:8] and need_key[:8] in shot.material_need:
                    shot.material_need += f" → {src.strip()[:60]}"
                    break

    return ScriptSpec(
        topic=meta.topic, title=meta.title, hook=meta.hook,
        storyboard=shots, cta=meta.cta,
    )

def validate_spec(spec: ScriptSpec) -> list[str]:
    issues = []
    if not (3 <= len(spec.storyboard) <= 8):
        issues.append(f"分镜数 {len(spec.storyboard)} 不在 3~8")
    if not spec.cta:
        issues.append("缺少 CTA")
    return issues

if __name__ == "__main__":
    import os
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass
    from langchain_deepseek import ChatDeepSeek
    llm = ChatDeepSeek(model="deepseek-chat")
    sample = "【0-3s】你问AI最新考研政策——它张口就编，还特自信？【3-35s】RAG是检索增强生成，开卷考试。【55-60s CTA】评论区扣RAG！"
    print(generate_storyboard(llm, sample).model_dump_json(indent=2))
