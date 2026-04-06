#!/usr/bin/env python3.13
"""
OCR 변환 스크립트 — 스캔본 PDF를 텍스트 추출 불가 시 이미지→OCR 경로로 변환

지원 시나리오:
  1. markitdown이 텍스트 추출 성공 → 그대로 사용 (이 스크립트 불필요)
  2. markitdown이 텍스트 0줄 또는 극히 적은 텍스트 → OCR 경로 실행
     a. tesseract + pdf2image 설치됨 → 로컬 OCR
     b. 미설치 → markitdown LLM 경로 (OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 필요)

사용법:
  # 단일 파일 OCR 변환
  python scripts/ocr_convert.py --input /path/to/scanned.pdf --output /path/to/output.md

  # 텍스트 밀도 체크만 (OCR 필요 여부 판단)
  python scripts/ocr_convert.py --input /path/to/file.pdf --check-only

설치 요구사항 (로컬 OCR):
  brew install tesseract tesseract-lang
  uv pip install pytesseract pdf2image Pillow
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click


def check_dependencies() -> dict[str, bool]:
    """OCR 관련 의존성 체크"""
    deps: dict[str, bool] = {}

    # tesseract CLI
    try:
        result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
        deps["tesseract"] = result.returncode == 0
    except FileNotFoundError:
        deps["tesseract"] = False

    # pytesseract Python 패키지
    try:
        import pytesseract  # noqa: F401
        deps["pytesseract"] = True
    except ImportError:
        deps["pytesseract"] = False

    # pdf2image
    try:
        import pdf2image  # noqa: F401
        deps["pdf2image"] = True
    except ImportError:
        deps["pdf2image"] = False

    # Pillow
    try:
        from PIL import Image  # noqa: F401
        deps["pillow"] = True
    except ImportError:
        deps["pillow"] = False

    # poppler (pdf2image 의존)
    try:
        result = subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True)
        deps["poppler"] = result.returncode == 0 or "version" in result.stderr.lower()
    except FileNotFoundError:
        deps["poppler"] = False

    # LLM fallback 가능 여부
    deps["llm_anthropic"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    deps["llm_openai"] = bool(os.environ.get("OPENAI_API_KEY"))

    return deps


def measure_text_density(pdf_path: Path) -> dict[str, float | int]:
    """
    markitdown으로 변환 후 텍스트 밀도 측정.
    결과:
      char_count: 총 텍스트 문자 수
      line_count: 줄 수
      density: 문자 수 / 파일 크기(KB) — 낮으면 스캔본 가능성 높음
      is_scanned: 스캔본으로 판단하는지 여부
    """
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(pdf_path))
        text = result.text_content or ""

        char_count = len(text.strip())
        line_count = len([l for l in text.split("\n") if l.strip()])
        file_size_kb = pdf_path.stat().st_size / 1024
        density = char_count / max(file_size_kb, 1)

        # 휴리스틱: 1KB당 10자 미만이면 스캔본 가능성 높음
        is_scanned = density < 10 or char_count < 100

        return {
            "char_count": char_count,
            "line_count": line_count,
            "density": round(density, 2),
            "is_scanned": is_scanned,
            "text_preview": text[:200] if text else "",
        }
    except Exception as e:
        return {"char_count": 0, "line_count": 0, "density": 0.0, "is_scanned": True, "error": str(e)}


def ocr_with_tesseract(pdf_path: Path, output_path: Path, lang: str = "kor+eng") -> dict:
    """
    pdf2image + tesseract를 사용한 로컬 OCR.
    페이지별로 이미지 변환 후 OCR, 결과를 markdown으로 합산.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image
    except ImportError as e:
        return {"status": "error", "error": f"의존성 없음: {e}. 설치: uv pip install pytesseract pdf2image Pillow"}

    # tesseract가 /opt/homebrew/bin에 있는 경우 명시적 경로 설정
    _TESSERACT_CANDIDATES = [
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
    ]
    for candidate in _TESSERACT_CANDIDATES:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            break

    try:
        click.echo(f"  📄 PDF→이미지 변환 중... ({pdf_path.name})")
        images = convert_from_path(str(pdf_path), dpi=300, fmt="jpeg")
        click.echo(f"  🖼  {len(images)}페이지 감지됨")

        all_text_parts = []
        for i, image in enumerate(images, 1):
            click.echo(f"  🔍 OCR 처리 중: {i}/{len(images)}페이지...")
            text = pytesseract.image_to_string(image, lang=lang, config="--psm 3")
            if text.strip():
                all_text_parts.append(f"\n\n---\n\n## 페이지 {i}\n\n{text.strip()}")

        combined_text = "\n".join(all_text_parts)
        char_count = len(combined_text.strip())

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined_text)

        return {
            "status": "success",
            "method": "tesseract_ocr",
            "pages": len(images),
            "char_count": char_count,
            "lang": lang,
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


def ocr_with_llm(pdf_path: Path, output_path: Path) -> dict:
    """
    markitdown의 LLM 플러그인을 사용한 이미지 기반 OCR.
    ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 필요.
    """
    try:
        from markitdown import MarkItDown

        # Anthropic 우선
        if os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic()
            md = MarkItDown(llm_client=client, llm_model="claude-3-5-haiku-20241022")
            method = "markitdown_anthropic_llm"
        elif os.environ.get("OPENAI_API_KEY"):
            import openai
            client = openai.OpenAI()
            md = MarkItDown(llm_client=client, llm_model="gpt-4o-mini")
            method = "markitdown_openai_llm"
        else:
            return {"status": "error", "error": "API 키 없음: ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 필요"}

        click.echo(f"  🤖 LLM OCR 처리 중... ({pdf_path.name})")
        result = md.convert(str(pdf_path))
        text = result.text_content or ""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

        return {
            "status": "success",
            "method": method,
            "char_count": len(text.strip()),
        }

    except ImportError as e:
        return {"status": "error", "error": f"패키지 미설치: {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def convert_scanned_pdf(
    pdf_path: Path,
    output_path: Path,
    lang: str = "kor+eng",
    force_ocr: bool = False,
) -> dict:
    """
    스캔 PDF 변환 메인 함수.
    1. markitdown 시도 → 텍스트 밀도 체크
    2. 밀도 낮으면 (스캔본) → tesseract 또는 LLM OCR 경로
    3. 결과 반환
    """
    deps = check_dependencies()

    # 1단계: markitdown으로 먼저 시도
    if not force_ocr:
        click.echo(f"  🔎 텍스트 밀도 측정: {pdf_path.name}")
        density_info = measure_text_density(pdf_path)

        if not density_info.get("is_scanned", True):
            # 충분한 텍스트가 있음 → 일반 markitdown 경로 사용
            click.echo(f"  ✅ 일반 텍스트 PDF (밀도: {density_info['density']:.1f}자/KB) — OCR 불필요")
            return {
                "status": "skipped",
                "reason": "sufficient_text",
                "density": density_info["density"],
                "char_count": density_info["char_count"],
            }
        else:
            click.echo(
                f"  ⚠️  스캔본 또는 이미지 PDF 감지 (밀도: {density_info['density']:.1f}자/KB, "
                f"텍스트: {density_info['char_count']}자) — OCR 경로 시도"
            )

    # 2단계: OCR 경로 선택
    if deps["tesseract"] and deps["pytesseract"] and deps["pdf2image"] and deps["poppler"]:
        click.echo(f"  🔧 방법: Tesseract 로컬 OCR (언어: {lang})")
        return ocr_with_tesseract(pdf_path, output_path, lang=lang)

    elif deps["llm_anthropic"] or deps["llm_openai"]:
        click.echo("  🔧 방법: LLM 이미지 설명 (API 호출)")
        return ocr_with_llm(pdf_path, output_path)

    else:
        # 설치 안내
        click.echo("  ❌ OCR 도구가 없습니다. 다음 중 하나를 선택하세요:", err=True)
        click.echo("     옵션 1 (로컬 OCR — 권장):", err=True)
        click.echo("       brew install tesseract tesseract-lang poppler", err=True)
        click.echo("       uv pip install pytesseract pdf2image Pillow", err=True)
        click.echo("     옵션 2 (LLM OCR — API 키 필요):", err=True)
        click.echo("       export ANTHROPIC_API_KEY=your_key", err=True)
        click.echo("       uv pip install anthropic", err=True)
        return {
            "status": "error",
            "error": "OCR 도구 없음 — tesseract 또는 API 키 필요",
            "deps": deps,
        }


@click.command()
@click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="입력 PDF 경로")
@click.option("--output", "-o", "output_path", type=click.Path(), help="출력 MD 경로 (생략 시 자동 생성)")
@click.option("--lang", default="kor+eng", show_default=True, help="Tesseract 언어 코드 (예: kor+eng, kor)")
@click.option("--force-ocr", is_flag=True, help="텍스트 밀도 체크 없이 강제 OCR")
@click.option("--check-only", is_flag=True, help="OCR 필요 여부만 판단 (변환 안 함)")
@click.option("--check-deps", is_flag=True, help="의존성 설치 상태 확인")
def main(
    input_path: str,
    output_path: str | None,
    lang: str,
    force_ocr: bool,
    check_only: bool,
    check_deps: bool,
) -> None:
    """OCR 변환 — 스캔본 PDF를 텍스트 Markdown으로 변환"""

    if check_deps:
        deps = check_dependencies()
        click.echo("=== OCR 의존성 상태 ===")
        for name, ok in deps.items():
            status = "✅" if ok else "❌"
            click.echo(f"  {status} {name}")
        local_ocr_ok = all(deps.get(k) for k in ["tesseract", "pytesseract", "pdf2image", "poppler"])
        llm_ok = deps.get("llm_anthropic") or deps.get("llm_openai")
        click.echo()
        if local_ocr_ok:
            click.echo("✅ 로컬 OCR (tesseract) 사용 가능")
        elif llm_ok:
            click.echo("⚠️  로컬 OCR 불가, LLM OCR 사용 가능")
        else:
            click.echo("❌ OCR 사용 불가 — 설치 필요")
        return

    inp = Path(input_path)

    if check_only:
        info = measure_text_density(inp)
        click.echo(f"파일: {inp.name}")
        click.echo(f"  텍스트 문자 수: {info['char_count']:,}")
        click.echo(f"  줄 수: {info['line_count']}")
        click.echo(f"  밀도: {info['density']:.1f}자/KB")
        click.echo(f"  스캔본 여부: {'⚠️ 예 (OCR 권장)' if info['is_scanned'] else '✅ 아니오 (일반 변환 가능)'}")
        if info.get("text_preview"):
            click.echo(f"  텍스트 미리보기: {info['text_preview'][:100]}...")
        return

    if not output_path:
        output_path = str(inp.with_suffix(".ocr.md"))

    out = Path(output_path)
    result = convert_scanned_pdf(inp, out, lang=lang, force_ocr=force_ocr)

    if result["status"] == "success":
        click.echo(f"✅ OCR 완료: {out}")
        click.echo(f"   방법: {result.get('method', 'N/A')}")
        click.echo(f"   텍스트 추출: {result.get('char_count', 0):,}자")
        if result.get("pages"):
            click.echo(f"   처리 페이지: {result['pages']}페이지")
    elif result["status"] == "skipped":
        click.echo(f"⏭  변환 불필요: 충분한 텍스트 있음 (일반 markitdown 사용)")
    else:
        click.echo(f"❌ OCR 실패: {result.get('error', '알 수 없는 오류')}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
