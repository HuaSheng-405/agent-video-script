# structured_spec.py —— v1.0 的成片规格结构化输出组件
# 把「口播脚本文本」转成结构化【成片规格】（Pydantic schema + 校验 + 失败重试）
from pydantic import BaseModel, Field

class StoryboardShot(BaseModel):
    start: str = Field(description="时间段，如 0-3s")
    scene: str = Field(description="画面描述")
    narration: str = Field(description="该时段口播词")

class ScriptSpec(BaseModel):
    topic: str = Field(description="视频主题")
    title: str = Field(description="标题（含钩子）")
    hook: str = Field(description="开头 3 秒钩子原文")
    storyboard: list[StoryboardShot] = Field(description="分镜表：覆盖 60 秒，3~8 个镜头")
    cta: str = Field(description="结尾行动号召")

def generate_spec(llm, script_text: str, max_attempts: int = 3) -> ScriptSpec:
    """把脚本文本解析为 ScriptSpec；校验失败重试"""
    structured_llm = llm.with_structured_output(ScriptSpec)
    last_err = None
    for attempt in range(max_attempts):
        try:
            spec = structured_llm.invoke(
                f"将以下口播脚本整理为成片规格（字段见 schema，必须覆盖全部镜头）：\n{script_text}"
            )
            if not isinstance(spec, ScriptSpec):
                # with_structured_output 某些版本返回 dict，兜底转一次
                spec = ScriptSpec.model_validate(spec)
            return spec
        except Exception as e:
            last_err = e
            print(f"⚠ 解析失败（第 {attempt + 1} 次）：{e}")
    raise RuntimeError(f"结构化输出 3 次尝试均失败：{last_err}")

def validate_spec(spec: ScriptSpec) -> list[str]:
    """业务规则校验（规则层的延伸）：成片规格的约束也可以规则化"""
    issues = []
    if not (3 <= len(spec.storyboard) <= 8):
        issues.append(f"分镜数 {len(spec.storyboard)} 不在 3~8")
    if not spec.storyboard:
            issues.append("缺少 分镜表")
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

    sample_script = """【0-3秒 钩子】你问AI最新考研政策——它张口就编，还特自信？
【3-35秒 核心】别怪它。模型的知识有保质期，不知道的只能编。它像困在旧图书馆的学霸，新知识够不着。咋办？给它装外挂——RAG，检索增强生成。说白了就是开卷考试：第一步R，从外部资料库搜答案；第二步G，对着资料整理语言回答。
【35-55秒 价值】写论文、期末复习、查最新政策……有来源的答案才可信。让AI学会翻书，而不是硬编。
【55-60秒 CTA】评论区扣 RAG，下期教你搭一个！"""

    try:
        spec = generate_spec(llm, sample_script)
        print("\n===== 结构化输出（ScriptSpec）=====")
        print(spec.model_dump_json(indent=2))
        issues = validate_spec(spec)
        print("\n业务规则校验:", issues if issues else "✅ 通过")
    except Exception as e:
        print("生成失败:", e)

