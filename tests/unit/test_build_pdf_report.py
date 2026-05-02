"""PDF 报告生成器 - 单元测试。"""
import json
from pathlib import Path

import pytest

from scripts.report.build_pdf_report import build_pdf

# 最小可用的 module_output_v1 mock
_MIN_OUTPUT = {
    "module_id": "industry_analysis",
    "module_name": "行业分析模块",
    "module_version": "1.0.0",
    "schema_version": "module_output_v1",
    "request_id": "req_test_pdf",
    "analysis_date": "2026-04-30",
    "status": "success",
    "signal": "中性",
    "score": -10,
    "confidence": 0.6,
    "reasons": ["理由 1", "理由 2", "理由 3"],
    "risks": ["风险 1", "风险 2"],
    "summary": "测试用一句话总结。",
    "metrics": {"latency_ms": 1234, "data_sources_used": ["tushare"]},
    "module_specific": {
        "classification": {
            "primary_industry": {"system": "申万二级", "code": "801125.SI", "name": "白酒Ⅱ"},
            "l1_industry": {"code": "801120.SI", "name": "食品饮料"},
            "related_concepts": [{"name": "高端消费"}, {"name": "ROE大白马"}],
        },
        "agent_breakdown": {
            "trend": {"score": -55, "confidence": 0.75, "stage": "下行",
                      "key_signals": [
                          {"name": "1m_return", "value": -0.05, "interpretation": "1M 跌-5%"},
                      ]},
            "fundamentals": {"score": 25, "confidence": 0.7, "stage": "底部"},
            "capital_flow": {"score": -30, "confidence": 0.6, "consensus": "outflow"},
            "leaders": {"score": 10, "confidence": 0.65, "target_position": "绝对龙头"},
            "macro_policy": {"score": 20, "confidence": 0.55, "macro_alignment": "顺风"},
        },
        "industry_outlook": {"verdict": "中性", "stage": "下行", "horizon": "60d",
                             "rationale": "白酒下行但茅台龙头。"},
        "stock_in_industry": {"relative_position": "绝对龙头", "industry_boost": 0,
                              "rationale": "行业弱与龙头强抵消。"},
        "weights_used": {"trend": 0.20, "fundamentals": 0.20},
    },
}


def test_build_pdf_creates_file(tmp_path):
    """基本功能:JSON → PDF 文件存在且非零大小。"""
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps(_MIN_OUTPUT, ensure_ascii=False), encoding="utf-8")
    pdf_path = tmp_path / "output.pdf"

    build_pdf(json_path, pdf_path, ticker="600519", stock_name="贵州茅台")

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000  # 大于 1KB(实际约 10KB)


def test_build_pdf_with_minimal_data(tmp_path):
    """缺失大部分可选字段也能生成(只有顶层必备字段)。"""
    minimal = {
        "module_id": "industry_analysis",
        "module_name": "行业分析模块",
        "module_version": "1.0.0",
        "schema_version": "module_output_v1",
        "request_id": "req_min",
        "analysis_date": "2026-04-30",
        "status": "failed",
        "signal": None,
        "score": None,
        "confidence": None,
        "reasons": [],
        "risks": [],
        "summary": "数据不可用。",
    }
    json_path = tmp_path / "min.json"
    json_path.write_text(json.dumps(minimal, ensure_ascii=False), encoding="utf-8")
    pdf_path = tmp_path / "min.pdf"

    build_pdf(json_path, pdf_path)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 500


def test_pdf_content_includes_chinese(tmp_path):
    """PDF 文本应该包含中文,验证字体没乱码。"""
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps(_MIN_OUTPUT, ensure_ascii=False), encoding="utf-8")
    pdf_path = tmp_path / "output.pdf"

    build_pdf(json_path, pdf_path, ticker="600519", stock_name="贵州茅台")

    # 用 pypdf 提取文本
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(str(pdf_path))
    text = "".join(page.extract_text() for page in reader.pages)

    # 关键中文应该出现
    assert "行业分析研报" in text
    assert "贵州茅台" in text
    assert "白酒Ⅱ" in text
    assert "中性" in text
    assert "理由 1" in text
    assert "风险 1" in text


def test_pdf_score_signal_color_rendering(tmp_path):
    """看多/看空/中性都能正常渲染(不挂)。"""
    for signal, score in [("看多", 50), ("看空", -50), ("中性", 0), (None, None)]:
        d = {**_MIN_OUTPUT, "signal": signal, "score": score}
        if signal is None:
            d["confidence"] = None
        json_path = tmp_path / f"sig_{signal or 'null'}.json"
        json_path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        pdf_path = tmp_path / f"sig_{signal or 'null'}.pdf"
        build_pdf(json_path, pdf_path)
        assert pdf_path.exists()


def test_pdf_handles_stub_agent_with_note(tmp_path):
    """有 note 字段的 stub agent 也能正常渲染(没 key_signals)。"""
    d = {**_MIN_OUTPUT}
    d["module_specific"]["agent_breakdown"]["fundamentals"] = {
        "score": 0, "confidence": 0.3, "note": "v2 will add"
    }
    json_path = tmp_path / "stub.json"
    json_path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    pdf_path = tmp_path / "stub.pdf"

    build_pdf(json_path, pdf_path)
    assert pdf_path.exists()
