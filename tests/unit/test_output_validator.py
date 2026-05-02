"""Output JSON Schema 校验器。"""
import json

import pytest

from scripts.output_validator import ValidationError, validate_output


VALID_OUTPUT = {
    "module_id": "industry_analysis",
    "module_name": "行业分析模块",
    "module_version": "1.0.0",
    "schema_version": "module_output_v1",
    "request_id": "req_test_001",
    "analysis_date": "2026-04-30",
    "status": "success",
    "signal": "看多",
    "score": 65,
    "confidence": 0.78,
    "reasons": ["A", "B", "C"],
    "risks": ["X", "Y"],
    "summary": "白酒景气回升,茅台核心受益。",
}


def test_valid_output_passes():
    validate_output(VALID_OUTPUT)


def test_score_out_of_range_fails():
    bad = {**VALID_OUTPUT, "score": 200}
    with pytest.raises(ValidationError):
        validate_output(bad)


def test_summary_too_long_fails():
    bad = {**VALID_OUTPUT, "summary": "x" * 51}
    with pytest.raises(ValidationError):
        validate_output(bad)


def test_reasons_too_many_fails():
    bad = {**VALID_OUTPUT, "reasons": ["a"] * 6}
    with pytest.raises(ValidationError):
        validate_output(bad)


def test_failed_status_with_null_signal_passes():
    output = {
        **VALID_OUTPUT,
        "status": "failed",
        "signal": None,
        "score": None,
        "confidence": None,
        "error": {"code": "DATA_NOT_FOUND", "message": "..."},
    }
    validate_output(output)


def test_unknown_error_code_fails():
    bad = {
        **VALID_OUTPUT,
        "status": "failed",
        "signal": None,
        "score": None,
        "confidence": None,
        "error": {"code": "WHO_KNOWS", "message": "..."},
    }
    with pytest.raises(ValidationError):
        validate_output(bad)
