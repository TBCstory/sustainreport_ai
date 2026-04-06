#!/usr/bin/env python3
"""
verify_disclosure_ids.py — 프레임워크 DB의 disclosure ID 포맷 검증 스크립트

프레임워크별 ID 필드 및 형식을 검증하고 불일치를 보고합니다.

Usage:
    python scripts/verify_disclosure_ids.py
    python scripts/verify_disclosure_ids.py --verbose
    python scripts/verify_disclosure_ids.py --fix  # 향후 포맷 자동 교정용
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Framework DB 경로
FRAMEWORK_DB_DIR = Path(__file__).parent.parent / "templates" / "framework_db"

# 프레임워크별 ID 필드 및 기대 형식 정의
FRAMEWORK_CONFIG = {
    "tcfd_db.json": {
        "id_field": "disclosure_id",
        "id_type": "TCFD Disclosure ID",
        "expected_patterns": [
            r"^[A-Z]\d+$",  # G1, G2, G3, G4
        ],
        "examples": ["G1", "G2", "G3", "G4"],
    },
    "gri_db.json": {
        "id_field": "standard_id",
        "id_type": "GRI Standard ID",
        "expected_patterns": [
            r"^GRI \d+$",  # GRI 1, GRI 305
            r"^GRI \d+-\d+$",  # GRI 305-1, GRI 305-2
        ],
        "examples": ["GRI 1", "GRI 305", "GRI 305-1"],
    },
    "kssb_db.json": {
        "id_field": "section_id",
        "id_type": "KSSB Section ID",
        "expected_patterns": [
            r"^KSSB-[A-Z]\d+$",  # KSSB-E1, KSSB-S1, KSSB-G1
        ],
        "examples": ["KSSB-E1", "KSSB-S1", "KSSB-G1"],
    },
    "esrs_db.json": {
        "id_field": "standard_id",
        "id_type": "ESRS Standard ID",
        "expected_patterns": [
            r"^ESRS-[A-Z]?\d+$",  # ESRS-1, ESRS-2, ESRS-E1, ESRS-S1
        ],
        "examples": ["ESRS-1", "ESRS-2", "ESRS-E1", "ESRS-S1"],
    },
    "sasb_db.json": {
        "id_field": "topic_code",
        "id_type": "SASB Topic Code",
        "expected_patterns": [
            r"^[A-Z]{2}-[A-Z]{2}-\d+[a-z]?(?:\.\d+)?$",  # RT-CH-110, RT-CH-110.1, LV-CO-410a
        ],
        "examples": ["RT-CH-110", "RT-CH-110.1", "LV-CO-410a"],
    },
}


@dataclass
class VerificationResult:
    """검증 결과를 저장하는 데이터 클래스."""

    framework: str
    id_field: str
    total_entries: int = 0
    valid_ids: list[str] = field(default_factory=list)
    invalid_ids: list[tuple[str, str]] = field(default_factory=list)  # (id, reason)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and len(self.invalid_ids) == 0

    def print_summary(self, verbose: bool = False) -> None:
        """검증 결과를 콘솔에 출력."""
        status = "✅ PASS" if self.is_valid else "❌ FAIL"
        print(f"\n{status} — {self.framework}")
        print(f"  ID Field: {self.id_field}")
        print(f"  Total Entries: {self.total_entries}")

        if self.invalid_ids:
            print(f"  Invalid IDs ({len(self.invalid_ids)}):")
            for invalid_id, reason in self.invalid_ids[:5]:
                print(f"    - {invalid_id}: {reason}")
            if len(self.invalid_ids) > 5:
                print(f"    ... and {len(self.invalid_ids) - 5} more")

        if self.errors:
            print(f"  Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"    - {error}")

        if verbose and self.warnings:
            print(f"  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"    - {warning}")


def load_framework_db(filepath: Path) -> dict | None:
    """프레임워크 DB JSON 파일을 로드."""
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"  Error: Invalid JSON in {filepath.name}: {e}")
        return None
    except OSError as e:
        print(f"  Error: Cannot read {filepath.name}: {e}")
        return None


def extract_entries(db_data: dict, framework: str) -> list[dict]:
    """프레임워크별 구조에서 entries 목록을 추출."""
    # 구조가 다른 프레임워크들을 처리
    if framework == "tcfd_db.json":
        return db_data.get("disclosures", [])
    elif framework == "gri_db.json":
        return db_data.get("standards", [])
    elif framework == "kssb_db.json":
        return db_data.get("framework", [])
    elif framework == "esrs_db.json":
        return db_data.get("standards", [])
    elif framework == "sasb_db.json":
        # SASB는 industries > topics 구조
        entries = []
        for industry in db_data.get("industries", []):
            entries.extend(industry.get("topics", []))
        return entries
    return []


def validate_id_format(id_value: str, framework: str, expected_patterns: list[str]) -> tuple[bool, str]:
    """ID 값이 기대 포맷에 맞는지 검증."""
    import re

    if not id_value or not isinstance(id_value, str):
        return False, "ID is empty or not a string"

    for pattern in expected_patterns:
        if re.match(pattern, id_value):
            return True, ""

    return False, f"Does not match expected patterns: {expected_patterns}"


def verify_framework_db(framework: str, config: dict, verbose: bool = False) -> VerificationResult:
    """단일 프레임워크 DB를 검증."""
    result = VerificationResult(
        framework=framework,
        id_field=config["id_field"],
    )

    filepath = FRAMEWORK_DB_DIR / framework
    if not filepath.exists():
        result.errors.append(f"File not found: {filepath}")
        return result

    db_data = load_framework_db(filepath)
    if db_data is None:
        result.errors.append("Failed to load JSON")
        return result

    entries = extract_entries(db_data, framework)
    result.total_entries = len(entries)

    if result.total_entries == 0:
        result.warnings.append("No entries found in framework DB")
        return result

    id_field = config["id_field"]
    expected_patterns = config["expected_patterns"]

    for idx, entry in enumerate(entries):
        entry_id = entry.get(id_field)
        if entry_id is None:
            result.errors.append(f"Entry {idx} missing ID field '{id_field}'")
            continue

        is_valid, reason = validate_id_format(entry_id, framework, expected_patterns)
        if is_valid:
            result.valid_ids.append(entry_id)
        else:
            result.invalid_ids.append((entry_id, reason))

    return result


def main() -> int:
    """메인 검증 로직."""
    parser = argparse.ArgumentParser(
        description="프레임워크 DB의 disclosure ID 포맷을 검증합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/verify_disclosure_ids.py           # 기본 검증
  python scripts/verify_disclosure_ids.py --verbose # 상세 출력
  python scripts/verify_disclosure_ids.py --fix     # 자동 교정 (예정)
        """,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 출력 모드")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="자동 교정 모드 (아직 미구현)",
    )
    parser.add_argument(
        "--framework",
        "-f",
        choices=[f for f in FRAMEWORK_CONFIG.keys()],
        help="특정 프레임워크만 검증",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Disclosure ID Format Verification")
    print("=" * 60)

    frameworks_to_check = [args.framework] if args.framework else list(FRAMEWORK_CONFIG.keys())

    all_results: list[VerificationResult] = []

    for framework in frameworks_to_check:
        if framework not in FRAMEWORK_CONFIG:
            print(f"\n❌ Unknown framework: {framework}")
            continue

        config = FRAMEWORK_CONFIG[framework]
        result = verify_framework_db(framework, config, args.verbose)
        result.print_summary(args.verbose)
        all_results.append(result)

    # 종합 결과
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for r in all_results if r.is_valid)
    failed = sum(1 for r in all_results if not r.is_valid)

    print(f"Total Frameworks: {len(all_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed Frameworks:")
        for r in all_results:
            if not r.is_valid:
                print(f"  - {r.framework}")

    # 상세 불일치 목록
    if args.verbose:
        for r in all_results:
            if r.invalid_ids:
                print(f"\n{r.framework} Invalid IDs:")
                for invalid_id, reason in r.invalid_ids:
                    print(f"  - {invalid_id}: {reason}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
