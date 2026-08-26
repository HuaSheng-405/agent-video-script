# eval_run.py —— v1.0 组件二：端到端评估体系（复用 RAG 项目的评测方法论）
# 指标：一次通过率 / 平均回退次数 / 成片规格生成率 / 平均耗时
# 跑法：python eval_run.py          # 冒烟：5 题（约 30 分钟，含索引构建）
#      python eval_run.py --all     # 全量：20 题（约 2 小时，建议周末跑）
# 限速说明：material_server 每次子进程启动都会全量重建索引（P0 已知问题）——
#           v1.0 收尾的「增量索引」会把它降到秒级
import json
import asyncio, io, sys, time, contextlib
from prototype_v02 import run_topic
from structured_spec import ScriptSpec, validate_spec

TOPICS = [
    "给大学生讲清楚什么是RAG",
    "健身新人第一周怎么练",
    "晚上睡不着怎么办",
    "北京胡同美食盘点",
    "大一新生报到避坑指南",
    "什么是深度学习",
    "期末复习怎么安排",
    "手机拍照入门技巧",
    "学生党怎么选蓝牙耳机",
    "考研英语单词怎么背",
    "宿舍改造低成本方案",
    "编程第一课学什么语言",
    "穷游省钱攻略",
    "和室友发生矛盾怎么办",
    "如何写出高分论文",
    "时间管理四象限",
    "久坐颈椎疼怎么缓解",
    "要不要转专业",
    "为什么总是熬夜",
    "暑期实习简历怎么写",
]

async def main():
    topics = TOPICS if "--all" in sys.argv else TOPICS[:5]

    n, first_pass, retries_sum, spec_ok, spec_valid, dur_sum, crashed = 0, 0, 0, 0, 0, 0.0, 0
    results = []
    # 关键优化：整个评估循环只建一次 MCP 连接/索引（20 题从 2h+ 降到 ~40min）
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from prototype_v02 import LLM_ENV_PY, MATERIAL_SERVER
    mcp_client = MultiServerMCPClient({
        "material": {"command": LLM_ENV_PY, "args": [MATERIAL_SERVER], "transport": "stdio"},
    })
    shared_tools = await mcp_client.get_tools()
    print("检索工具已接入（共享连接）:", [t.name for t in shared_tools])
    for t in topics:
        t0 = time.time()
        try:
            # 屏蔽 run_topic 的详细打印，只需指标（评估要的是数据不是噪音）
            with contextlib.redirect_stdout(io.StringIO()):
                st = await run_topic(t, material_tools=shared_tools)
            retries = st.get("retry_count", 0)
            spec = st.get("spec")
            ok_generated = spec is not None
            ok_validated = False
            if ok_generated:
                ok_validated = len(validate_spec(ScriptSpec.model_validate(spec))) == 0
            qc = st.get("first_fail_reason", "") or ""
            fail_reason = qc if retries > 0 else ""
        except Exception as e:  # 单题崩溃不毒化整轮（健壮性铁律）
            retries, ok_generated, ok_validated, spec = -1, False, False, None
            crashed += 1
            print(f"[{n + 1}/{len(topics)}] {t[:18]}… 💥 崩溃：{type(e).__name__}: {str(e)[:60]}")
        dt = time.time() - t0
        n += 1
        first_pass += 1 if retries == 0 else 0
        retries_sum += max(retries, 0)
        spec_ok += 1 if ok_generated else 0
        spec_valid += 1 if ok_validated else 0
        dur_sum += dt
        results.append({"topic": t, "retries": retries, "spec": ok_generated,
                        "spec_valid": ok_validated, "duration": round(dt, 1),
                        "first_fail_reason": fail_reason if retries > 0 else ""})
        if retries >= 0:
            extra = f" | 首稿问题：{fail_reason[:40]}" if retries > 0 else ""
            print(f"[{n}/{len(topics)}] {t[:18]}… 回退{retries}次 | 规格{'✅' if ok_generated else '❌'} | {dt:.0f}s{extra}")

    print("\n===== 端到端评估（" + str(n) + " 题）=====")
    print(f"一次通过率：{first_pass / n:.1%}")
    print(f"平均回退次数：{retries_sum / n:.2f}")
    print(f"成片规格生成率：{spec_ok / n:.1%}")
    print(f"规格校验通过率：{spec_valid / n:.1%}")
    print(f"平均耗时：{dur_sum / n:.0f}s")
    if crashed:
        print(f"崩溃题数：{crashed}（已容错跳过）")
    with open("eval_result.json", "w", encoding="utf-8") as f:
        json.dump({"topics": results, "summary": {
            "n": n, "first_pass_rate": round(first_pass / n, 4),
            "avg_retries": round(retries_sum / n, 2),
            "spec_rate": round(spec_ok / n, 4),
            "spec_valid_rate": round(spec_valid / n, 4),
            "avg_duration_s": round(dur_sum / n, 1),
            "crashed": crashed,
        }}, f, ensure_ascii=False, indent=2)
    print("明细已存 eval_result.json")

asyncio.run(main())
