"""端到端验证 600519 走势 agent 路径。

注意:这测试不直接 invoke SKILL.md(那需要 LLM),只验证数据脚本链路 + 校验最终 JSON。
LLM 推理部分由 SKILL.md 的开发者手动跑通(用 claude code "/industry-analysis ...")。
"""
from scripts.classification.fetch_concept_mapping import fetch_concept_mapping
from scripts.classification.fetch_industry_classification import fetch_industry_classification
from scripts.common.derive_signal import derive_signal
from scripts.leaders.compute_target_position import compute_target_position
from scripts.leaders.fetch_industry_leaders import fetch_industry_leaders
from scripts.output_validator import validate_output
from scripts.trend.compute_breadth import compute_breadth_for_industry
from scripts.trend.fetch_industry_index import compute_window_returns, fetch_industry_index
from scripts.trend.fetch_market_index import compute_relative_strength, fetch_market_index


def test_data_pipeline_600519(mock_tushare_for_600519):
    """完整数据脚本链路 + 模拟 LLM 输出 + JSON 校验。"""
    analysis_date = "2026-05-01"

    # Step 1: classification (Tushare for both industry and concepts)
    cls = fetch_industry_classification(mock_tushare_for_600519, ticker="600519")
    assert cls is not None
    assert cls["primary_industry"]["code"] == "801125.SI"

    concepts = fetch_concept_mapping(mock_tushare_for_600519, ticker="600519", top_n=3)
    assert len(concepts) == 3
    assert concepts[0]["name"] == "白酒概念"

    # Step 2: trend data
    industry_df = fetch_industry_index(
        mock_tushare_for_600519,
        index_code=cls["primary_industry"]["code"],
        analysis_date=analysis_date,
    )
    industry_returns = compute_window_returns(industry_df)
    assert industry_returns["1m"] is not None

    market_df = fetch_market_index(
        mock_tushare_for_600519,
        market_code="000300.SH",
        analysis_date=analysis_date,
    )
    market_returns = compute_window_returns(market_df)
    rs = compute_relative_strength(industry_returns, market_returns)

    breadth = compute_breadth_for_industry(
        mock_tushare_for_600519,
        industry_l2_code=cls["primary_industry"]["code"],
        analysis_date=analysis_date,
    )

    # Step 2.5: leaders
    leaders = fetch_industry_leaders(
        mock_tushare_for_600519,
        industry_l2_code=cls["primary_industry"]["code"],
        analysis_date=analysis_date,
    )
    assert len(leaders) == 5
    assert leaders[0]["ticker"] == "600519.SH"  # 茅台市值最大,排第 1
    assert leaders[0]["name"] == "贵州茅台"

    target_position = compute_target_position(
        target_ticker="600519.SH",
        target_return_1m=leaders[0]["return_1m"],
        target_return_3m=leaders[0]["return_3m"],
        leaders=leaders,
    )
    assert target_position["rank_in_industry"] == 1
    assert target_position["target_position"] == "绝对龙头"

    # Step 3-5: 模拟 LLM 输出(trend + leaders 双激活)
    final_score = 35
    final_confidence = 0.4
    output = {
        "module_id": "industry_analysis",
        "module_name": "行业分析模块",
        "module_version": "1.0.0",
        "schema_version": "module_output_v1",
        "request_id": "req_test_600519",
        "analysis_date": analysis_date,
        "status": "partial",
        "signal": derive_signal(final_score),
        "score": final_score,
        "confidence": final_confidence,
        "reasons": [
            f"白酒行业 1M 涨跌 {industry_returns['1m']:.2%}",
            f"涨跌家数比 {breadth['advance']}:{breadth['decline']}",
            "MVP 阶段仅基于走势维度",
        ],
        "risks": ["MVP 仅看走势,缺其他维度信号"],
        "summary": "走势偏多,茅台短期受益。",
        "metrics": {"latency_ms": 8000, "data_sources_used": ["tushare"]},
        "module_specific": {
            "classification": {
                "primary_industry": cls["primary_industry"],
                "related_concepts": concepts,
            },
            "agent_breakdown": {
                "trend": {
                    "score": final_score,
                    "confidence": final_confidence,
                    "key_signals": [
                        {"name": "1m_return", "value": industry_returns["1m"]},
                        {"name": "rs_vs_csi300_1m", "value": rs.get("1m")},
                        {"name": "breadth_ratio", "value": breadth["advance_decline_ratio"]},
                    ],
                },
                "leaders": {
                    "score": 25,
                    "confidence": 0.7,
                    "target_position": target_position["target_position"],
                    "rank_in_industry": target_position["rank_in_industry"],
                    "rs_vs_leaders_avg_1m": target_position["rs_vs_leaders_avg_1m"],
                    "key_signals": [],
                },
                "fundamentals": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
                "capital_flow": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
                "macro_policy": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
            },
            "stock_in_industry": {
                "relative_position": target_position["target_position"],
                "industry_boost": 0,
                "rationale": target_position["rationale"],
            },
            "weights_used": {"trend": 0.5, "leaders": 0.5, "_note": "trend + leaders 双维度"},
        },
    }

    # Step 6: schema 校验
    validate_output(output)


def test_signal_derivation_consistency():
    assert derive_signal(35) == "看多"
    assert derive_signal(0) == "中性"
    assert derive_signal(-50) == "看空"
