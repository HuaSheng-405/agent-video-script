# pipeline/agents_qc.py —— 质检（模块五）：规则层 + LLM 打分层（防漂移设计）
import re

def rule_check(text: str):
    """规则层：可规则化的全部用代码判（确定性、零成本、不漂移）"""
    spoken = re.sub(r"【[^】]*】|（[^）]*）|[#*>\-|=]|\d+-\d+秒|[\U0001F300-\U0001FAFF]", "", text)
    n = len(spoken)
    issues = []
    if not (150 <= n <= 450):
        issues.append(f"口播词 {n} 字，目标 250 字左右——请删减铺垫和重复例子，保留钩子与核心类比")
    if not re.search(r"(关注|点赞|评论|扣|私信|转发)", text):
        issues.append("缺少 CTA——请在结尾补一句互动号召")
    return (len(issues) == 0), issues

def create_qc_node(llm):
    def llm_score(text: str) -> int:
        """质量层：主观项（钩子吸引力）只打分不硬判（实测 LLM 硬判会标准漂移）"""
        r = llm.invoke(f"给以下短视频脚本的【开头钩子】吸引力打分（1-5 的整数）：\n{text[:150]}\n只输出一个 1-5 的数字。")
        m = re.search(r"[1-5]", r.content)
        return int(m.group()) if m else 3

    def qc_node(state):
        text = state["script"]
        ok, issues = rule_check(text)
        score = llm_score(text)
        sb_issues = state.get("storyboard_issues", []) or []
        report = f"规则层：{'✅ 通过' if ok else '❌ ' + '；'.join(issues)}\n"
        report += f"分镜层：{'✅ 通过' if not sb_issues else '❌ ' + '；'.join(sb_issues)}\n"
        report += f"LLM 钩子评分：{score}/5"
        print("\n===== 质检报告 =====\n" + report)
        retry = state.get("retry_count", 0)
        if not (ok and not sb_issues and score >= 3):
            retry += 1
            if not state.get("first_fail_reason"):
                reason = "；".join(issues + sb_issues) if (issues or sb_issues) else f"钩子评分 {score}/5"
                return {"qc_report": report, "retry_count": retry,
                        "first_fail_reason": f"❌ {reason}"}
        return {"qc_report": report, "retry_count": retry}

    return qc_node
