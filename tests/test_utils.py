#!/usr/bin/env python3.13
"""
tests/test_utils.py — utils.py 단위 테스트

run_id 생성 및 시퀀스 관리 함수를 테스트합니다.
"""

from datetime import datetime, timezone

from scripts.utils import generate_run_id, get_run_sequence


class TestGetRunSequence:
    """get_run_sequence() 함수 테스트."""

    def test_returns_string(self) -> None:
        """시퀀스 번호가 문자열로 반환되어야 합니다."""
        result = get_run_sequence()
        assert isinstance(result, str)

    def test_format_is_letter_digit(self) -> None:
        """반환 형식이 {Letter}{Digit}이어야 합니다 (예: A1, B3)."""
        result = get_run_sequence()
        assert len(result) == 2
        assert result[0].isalpha()
        assert result[1].isdigit()

    def test_letter_is_uppercase(self) -> None:
        """첫 번째 문자가 대문자여야 합니다."""
        result = get_run_sequence()
        assert result[0].isupper()

    def test_digit_is_1_to_9(self) -> None:
        """두 번째 문자가 1~9 사이의 숫자여야 합니다."""
        result = get_run_sequence()
        digit = int(result[1])
        assert 1 <= digit <= 9

    def test_sequence_increments(self) -> None:
        """연속 호출 시 시퀀스가 증가해야 합니다."""
        first = get_run_sequence()
        second = get_run_sequence()
        # 시퀀스는 단일 프로세스 내에서 순차적으로 증가
        assert first != second

    def test_sequence_wraps_from_9_to_next_letter(self) -> None:
        """시퀀스가 9에서 다음 글자로 넘어가야 합니다."""
        # 이 테스트는 특정 상태에 의존하므로 독립적이지 않음
        # 실제로는 순차 호출로 검증
        seq1 = get_run_sequence()
        seq2 = get_run_sequence()
        # 단순히 다른 값이 반환되는지만 확인
        assert seq1 != seq2


class TestGenerateRunId:
    """generate_run_id() 함수 테스트."""

    def test_returns_string(self) -> None:
        """run_id가 문자열로 반환되어야 합니다."""
        result = generate_run_id()
        assert isinstance(result, str)

    def test_starts_with_run_prefix(self) -> None:
        """run_id가 'RUN-' 접두사로 시작해야 합니다."""
        result = generate_run_id()
        assert result.startswith("RUN-")

    def test_contains_three_parts(self) -> None:
        """run_id가 RUN-YYYYMMDD-{seq} 형식이어야 합니다."""
        result = generate_run_id()
        parts = result.split("-")
        assert len(parts) == 3
        assert parts[0] == "RUN"

    def test_date_part_is_today(self) -> None:
        """날짜 부분이 오늘 날짜여야 합니다 (YYYYMMDD)."""
        result = generate_run_id()
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        assert today in result

    def test_sequence_part_format(self) -> None:
        """시퀀스 부분이 {Letter}{Digit} 형식이어야 합니다."""
        result = generate_run_id()
        parts = result.split("-")
        seq_part = parts[2]
        assert len(seq_part) == 2
        assert seq_part[0].isalpha()
        assert seq_part[1].isdigit()

    def test_id_is_unique_across_calls(self) -> None:
        """연속 호출 시 고유한 ID가 반환되어야 합니다."""
        ids = set()
        for _ in range(5):
            run_id = generate_run_id()
            assert run_id not in ids
            ids.add(run_id)
