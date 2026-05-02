"""把 module_output_v1 JSON 渲染成 PDF 研报。

JSON 是给上游(总控)的契约;PDF 是给人看的研报。

输入:
  - JSON 文件路径(符合 module_output_v1 schema)
  - PDF 输出路径
  - 可选:ticker / stock_name(显示在标题上)

PDF 结构:
  Page 1: 标题 + 总分 + summary + reasons + risks + 5 维度 score 表
  Page 2: 行业定位 + industry_outlook + 目标股位置
  Page 3: 5 个 agent 详细 key_signals
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# reportlab 自带的简体中文字体
_CN_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(_CN_FONT))

# Agent 显示名映射
_AGENT_CN_NAME = {
    "trend": "行业走势",
    "fundamentals": "行业基本面",
    "capital_flow": "行业资金流",
    "leaders": "龙头分析",
    "macro_policy": "行业宏观&政策",
}


def _make_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "CnTitle", parent=base["Title"], fontName=_CN_FONT,
            fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "CnSubtitle", parent=base["Title"], fontName=_CN_FONT,
            fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.grey,
        ),
        "h1": ParagraphStyle(
            "CnH1", parent=base["Heading1"], fontName=_CN_FONT,
            fontSize=14, leading=18, spaceBefore=10, spaceAfter=6,
            textColor=colors.HexColor("#1a4d80"),
        ),
        "h2": ParagraphStyle(
            "CnH2", parent=base["Heading2"], fontName=_CN_FONT,
            fontSize=11, leading=15, spaceBefore=6, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "CnBody", parent=base["BodyText"], fontName=_CN_FONT,
            fontSize=10, leading=14, spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "CnBullet", parent=base["BodyText"], fontName=_CN_FONT,
            fontSize=10, leading=14, leftIndent=14, spaceAfter=2,
        ),
        "small": ParagraphStyle(
            "CnSmall", parent=base["BodyText"], fontName=_CN_FONT,
            fontSize=8, leading=11, textColor=colors.grey,
        ),
        "score_big": ParagraphStyle(
            "CnScoreBig", parent=base["BodyText"], fontName=_CN_FONT,
            fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=4,
        ),
    }


def _signal_color(signal: str | None) -> colors.Color:
    """中国市场传统配色:看多红 / 看空绿 / 中性灰。"""
    if signal == "看多":
        return colors.HexColor("#c0392b")
    if signal == "看空":
        return colors.HexColor("#27ae60")
    if signal == "中性":
        return colors.HexColor("#7f8c8d")
    return colors.black


def _score_to_text(s: int | None) -> str:
    return "N/A" if s is None else str(s)


def _conf_to_text(c: float | None) -> str:
    return "N/A" if c is None else f"{c:.2f}"


def _stage_text(agent: dict) -> str:
    """从 agent 的不同字段里提取一个"状态标签"用于表格显示。"""
    return (
        agent.get("stage")
        or agent.get("target_position")
        or agent.get("macro_alignment")
        or agent.get("consensus")
        or "—"
    )


def _build_summary_table(data: dict, styles: dict) -> Table:
    """5 个 agent 评分总览表。"""
    breakdown = data.get("module_specific", {}).get("agent_breakdown", {})
    rows = [["Agent", "Score", "Confidence", "状态"]]
    for key, agent_data in breakdown.items():
        cn_name = _AGENT_CN_NAME.get(key, key)
        rows.append([
            cn_name,
            _score_to_text(agent_data.get("score")),
            _conf_to_text(agent_data.get("confidence")),
            _stage_text(agent_data)[:30],
        ])

    table = Table(rows, colWidths=[3.5 * cm, 2 * cm, 2.5 * cm, 7 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _CN_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4fa")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a4d80")),
        ("FONTNAME", (0, 0), (-1, 0), _CN_FONT),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _build_signals_table(signals: list[dict]) -> Table | None:
    if not signals:
        return None
    rows = [["信号", "值", "解读"]]
    for s in signals:
        rows.append([
            str(s.get("name", ""))[:30],
            str(s.get("value", ""))[:25],
            str(s.get("interpretation", ""))[:60],
        ])
    table = Table(rows, colWidths=[5 * cm, 3.5 * cm, 8 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _CN_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4fa")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def build_pdf(
    json_path: str | Path,
    pdf_path: str | Path,
    ticker: str | None = None,
    stock_name: str | None = None,
) -> None:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    styles = _make_styles()
    flowables: list = []

    # ── Page 1: 概要 ──────────────────────────────────────────────
    flowables.append(Paragraph("行业分析研报", styles["title"]))
    sub = (
        f"{stock_name + ' ' if stock_name else ''}({ticker or '—'})  |  "
        f"分析日期 {data.get('analysis_date', '—')}"
    )
    flowables.append(Paragraph(sub, styles["subtitle"]))
    flowables.append(Spacer(1, 0.6 * cm))

    # 大字总分
    signal = data.get("signal")
    score = data.get("score")
    conf = data.get("confidence")
    score_html = (
        f'<b>信号:</b> <font color="{_signal_color(signal).hexval()}">{signal or "—"}</font>'
        f'  &nbsp;|&nbsp;  <b>评分:</b> {score if score is not None else "—"} / 100'
        f'  &nbsp;|&nbsp;  <b>置信度:</b> {conf if conf is not None else "—"}'
        f'  &nbsp;|&nbsp;  <b>状态:</b> {data.get("status", "—")}'
    )
    flowables.append(Paragraph(score_html, styles["score_big"]))
    flowables.append(Spacer(1, 0.4 * cm))

    # Summary
    flowables.append(Paragraph("<b>核心结论</b>", styles["h2"]))
    flowables.append(Paragraph(data.get("summary", "—"), styles["body"]))
    flowables.append(Spacer(1, 0.3 * cm))

    # Reasons
    flowables.append(Paragraph("<b>主要理由</b>", styles["h2"]))
    for r in data.get("reasons", []):
        flowables.append(Paragraph(f"•  {r}", styles["bullet"]))
    flowables.append(Spacer(1, 0.2 * cm))

    # Risks
    flowables.append(Paragraph("<b>主要风险</b>", styles["h2"]))
    for r in data.get("risks", []):
        flowables.append(Paragraph(f"•  {r}", styles["bullet"]))
    flowables.append(Spacer(1, 0.4 * cm))

    # 5 维度 score 总览
    flowables.append(Paragraph("<b>5 维度 Agent 评分总览</b>", styles["h1"]))
    flowables.append(_build_summary_table(data, styles))

    # ── Page 2: 行业定位 + 概览 ──────────────────────────────────
    flowables.append(PageBreak())
    flowables.append(Paragraph("<b>行业定位</b>", styles["h1"]))

    cls = data.get("module_specific", {}).get("classification", {})
    primary = cls.get("primary_industry", {}) or {}
    l1 = cls.get("l1_industry", {}) or {}
    cls_html = (
        f"<b>申万二级:</b>{primary.get('name', '—')} ({primary.get('code', '—')})<br/>"
        f"<b>申万一级:</b>{l1.get('name', '—')} ({l1.get('code', '—')})"
    )
    flowables.append(Paragraph(cls_html, styles["body"]))

    concepts = cls.get("related_concepts", []) or []
    if concepts:
        flowables.append(Spacer(1, 0.2 * cm))
        concept_names = ", ".join(c.get("name", "") for c in concepts if c.get("name"))
        flowables.append(Paragraph(f"<b>关联概念:</b>{concept_names}", styles["body"]))

    # 行业景气度
    flowables.append(Spacer(1, 0.5 * cm))
    flowables.append(Paragraph("<b>行业景气度判断</b>", styles["h1"]))
    outlook = data.get("module_specific", {}).get("industry_outlook", {}) or {}
    outlook_html = (
        f"<b>判断:</b>{outlook.get('verdict', '—')}  &nbsp;|&nbsp;  "
        f"<b>阶段:</b>{outlook.get('stage', '—')}  &nbsp;|&nbsp;  "
        f"<b>时间窗口:</b>{outlook.get('horizon', '—')}"
    )
    flowables.append(Paragraph(outlook_html, styles["body"]))
    if outlook.get("rationale"):
        flowables.append(Spacer(1, 0.1 * cm))
        flowables.append(Paragraph(outlook["rationale"], styles["body"]))

    # 目标股位置
    flowables.append(Spacer(1, 0.5 * cm))
    flowables.append(Paragraph("<b>目标股在行业中的位置</b>", styles["h1"]))
    sii = data.get("module_specific", {}).get("stock_in_industry", {}) or {}
    sii_html = (
        f"<b>位置:</b>{sii.get('relative_position', '—')}  &nbsp;|&nbsp;  "
        f"<b>行业对该股加成:</b>{sii.get('industry_boost', 0)}"
    )
    flowables.append(Paragraph(sii_html, styles["body"]))
    if sii.get("rationale"):
        flowables.append(Spacer(1, 0.1 * cm))
        flowables.append(Paragraph(sii["rationale"], styles["body"]))

    # ── Page 3: 各 Agent 详细信号 ─────────────────────────────────
    flowables.append(PageBreak())
    flowables.append(Paragraph("<b>各 Agent 详细信号</b>", styles["h1"]))

    breakdown = data.get("module_specific", {}).get("agent_breakdown", {}) or {}
    for key, agent_data in breakdown.items():
        cn_name = _AGENT_CN_NAME.get(key, key)
        score_str = _score_to_text(agent_data.get("score"))
        conf_str = _conf_to_text(agent_data.get("confidence"))
        flowables.append(Paragraph(
            f"<b>{cn_name}</b>  &nbsp;&nbsp;  score = {score_str}  ·  confidence = {conf_str}",
            styles["h2"],
        ))
        if agent_data.get("note"):
            flowables.append(Paragraph(f"<i>{agent_data['note']}</i>", styles["small"]))

        sig_table = _build_signals_table(agent_data.get("key_signals", []))
        if sig_table is not None:
            flowables.append(sig_table)
        flowables.append(Spacer(1, 0.25 * cm))

    # 元数据
    flowables.append(Spacer(1, 0.4 * cm))
    flowables.append(Paragraph("<b>元数据</b>", styles["h2"]))
    metrics = data.get("metrics", {}) or {}
    sources = ", ".join(metrics.get("data_sources_used", []) or [])
    meta_html = (
        f"分析耗时:{metrics.get('latency_ms', '—')} ms  &nbsp;|&nbsp;  "
        f"数据源:{sources or '—'}<br/>"
        f"request_id:{data.get('request_id', '')}<br/>"
        f"模块版本:{data.get('module_version', '')}  ·  "
        f"schema:{data.get('schema_version', '')}"
    )
    flowables.append(Paragraph(meta_html, styles["small"]))

    flowables.append(Spacer(1, 0.3 * cm))
    flowables.append(Paragraph(
        "<i>免责声明:本报告基于公开数据自动生成,仅供研究参考,不构成投资建议。"
        "投资有风险,入市需谨慎。</i>",
        styles["small"],
    ))

    # ── 渲染 ──────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"行业分析研报 - {ticker or ''} {stock_name or ''}".strip(),
        author="industry-analysis skill",
    )
    doc.build(flowables)


def main() -> int:
    parser = argparse.ArgumentParser(description="把 module_output_v1 JSON 渲染成 PDF 研报")
    parser.add_argument("--input", required=True, help="JSON 文件路径")
    parser.add_argument("--output", required=True, help="PDF 输出路径")
    parser.add_argument("--ticker", default=None, help="股票代码(可选,显示用)")
    parser.add_argument("--stock-name", default=None, help="股票名称(可选,显示用)")
    args = parser.parse_args()

    build_pdf(args.input, args.output, ticker=args.ticker, stock_name=args.stock_name)
    print(f"✓ PDF 已生成: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
