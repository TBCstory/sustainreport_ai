"""HD-3: Writer contract enforcement tests."""
import re


def test_empty_response_detected():
    """빈/대기 응답이 감지되어야 한다."""
    from scripts.dispatch_agent import AgentDispatcher

    # AgentDispatcher 인스턴스 생성 (workspace는 임시 사용)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "PRJ-TEST"
        ws.mkdir(parents=True)
        dispatcher = AgentDispatcher(ws)

        # 대기 상태 패턴 테스트
        assert dispatcher._is_empty_or_waiting_response("대기 상태입니다.") is True
        assert dispatcher._is_empty_or_waiting_response("아직 작성되지 않았습니다.") is True
        assert dispatcher._is_empty_or_waiting_response("WAITING FOR INPUT") is True
        assert dispatcher._is_empty_or_waiting_response("no content available") is True

        # 짧지만 유효한 응답은 False (길이만으로는 빈 응답 판단 안 함)
        assert dispatcher._is_empty_or_waiting_response("짧음") is False
        assert dispatcher._is_empty_or_waiting_response("# SEC-3.1") is False

        # 정상적인 긴 응답
        good = "## 온실가스 배출량\n\n당사의 Scope 1 배출량은 <!-- src:SEG-00001 --> tCO2e이며"
        assert dispatcher._is_empty_or_waiting_response(good) is False


def test_count_source_tags():
    """source tag 카운트가 정확해야 한다."""
    from scripts.run_section_writer import _count_source_tags

    # 태그 없음
    assert _count_source_tags("## 섹션\n\n내용") == 0

    # SEG 태그
    assert _count_source_tags("<!-- src:SEG-00001 --> 내용") == 1
    assert _count_source_tags("<!-- src:SEG-00001 --> 내용 <!-- src:SEG-00002 -->") == 2

    # CALC 태그
    assert _count_source_tags("<!-- src:CALC-0001 --> 계산") == 1

    # 혼합
    text = "<!-- src:SEG-00001 --> 첫 번째\n<!-- src:CALC-0001 --> 두 번째\n<!-- src:SEG-00003 --> 세 번째"
    assert _count_source_tags(text) == 3


def test_grounding_mode_in_fallback_meta():
    """fallback draft meta에 grounding_mode 필드가 있어야 한다."""
    from scripts.run_section_writer import _generate_fallback_draft

    body, meta = _generate_fallback_draft(
        section_id="SEC-3.1",
        section_blueprint={"depth_level": 3, "title": "테스트"},
        section_entry={"section_id": "SEC-3.1"}
    )
    assert meta.get("grounding_mode") == "fallback", f"expected fallback, got {meta.get("grounding_mode")}"
    assert meta.get("fallback_mode") is True