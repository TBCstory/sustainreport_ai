"""HD-5: Draft query typed fields tests."""


def test_infer_query_type():
    """query_type이 올바르게 추론되어야 한다."""
    from scripts.run_section_writer import _infer_query_type

    assert _infer_query_type("Scope 3 데이터 미확보") == "additional_data_request"
    assert _infer_query_type("두 출처 간 수치 불일치") == "numeric_discrepancy"
    assert _infer_query_type("보고 범위에 해외 사업장 포함 여부") == "scope_question"
    assert _infer_query_type("환경 정책 존재 여부 확인") == "policy_clarification"
    assert _infer_query_type("기준연도 확인 필요") == "data_confirmation"


def test_extract_query_context():
    """placeholder 주변 문맥이 올바르게 추출되어야 한다."""
    from scripts.run_section_writer import _extract_query_context

    body = "전년도 대비 배출량이 감소했습니다.\n[확인필요: Scope 3 데이터 미확보]\n추가 자료가 필요합니다."
    ctx = _extract_query_context(body, "[확인필요: Scope 3 데이터 미확보]")
    assert "전년도" in ctx
    assert "Scope 3" in ctx
    assert "추가 자료" in ctx


def test_get_related_segments():
    """bucket에서 segment ID 목록이 올바르게 추출되어야 한다."""
    from scripts.run_section_writer import _get_related_segments

    bucket = {"segments": [
        {"segment_id": "SEG-00001"},
        {"segment_id": "SEG-00002"},
        {}
    ]}
    result = _get_related_segments(bucket)
    assert result == ["SEG-00001", "SEG-00002"]

    # None bucket
    assert _get_related_segments(None) == []


def test_draft_query_has_all_typed_fields():
    """생성된 DQ에 query_type, context, related_segments가 있어야 한다."""
    from scripts.run_section_writer import _extract_draft_queries_from_content

    content = "## 온실가스\n\n배출량 데이터입니다.\n[확인필요: Scope 1 데이터 확인 필요]\n종료."
    bucket = {"segments": [{"segment_id": "SEG-00001"}, {"segment_id": "SEG-00002"}]}
    queries = _extract_draft_queries_from_content(content, "SEC-3.1", bucket)

    assert len(queries) >= 1
    q = queries[0]
    assert "query_type" in q and q["query_type"] in [
        "data_confirmation", "additional_data_request",
        "numeric_discrepancy", "policy_clarification", "scope_question"
    ]
    assert "context" in q and len(q["context"]) > 0
    assert "related_segments" in q and isinstance(q["related_segments"], list)