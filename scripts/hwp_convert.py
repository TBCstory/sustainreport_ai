#!/usr/bin/env python3.13
"""
HWP/HWPX 변환 스크립트 — kordoc(Node.js CLI) 래퍼

kordoc (https://github.com/chrisryugj/kordoc) 은 TypeScript/Node.js 기반의
한국 공문서(HWP/HWPX) 파서. npx로 직접 실행하거나 전역 설치 후 사용.

사용법:
  # 단일 파일 변환
  python scripts/hwp_convert.py --input /path/to/file.hwp --output /path/to/output.md

  # 디렉토리 일괄 변환 (01_raw/ 내 HWP 전체)
  python scripts/hwp_convert.py --dir /path/to/01_raw --output-dir /path/to/03_normalized_md

  # 설치 상태 확인
  python scripts/hwp_convert.py --check-deps

설치 요구사항:
  brew install node
  npm install -g kordoc   (또는 npx kordoc 으로 바로 실행)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click


# kordoc/node가 /opt/homebrew/bin에 있어서 일반 PATH에서 찾지 못하는 경우를 위한 후보 경로
_KORDOC_CANDIDATES = [
    "kordoc",
    "/opt/homebrew/bin/kordoc",
    "/usr/local/bin/kordoc",
]
_NODE_CANDIDATES = [
    "node",
    "/opt/homebrew/bin/node",
    "/usr/local/bin/node",
]
_NPM_CANDIDATES = [
    "npm",
    "/opt/homebrew/bin/npm",
    "/usr/local/bin/npm",
]
_NPX_CANDIDATES = [
    "npx",
    "/opt/homebrew/bin/npx",
    "/usr/local/bin/npx",
]


def _find_executable(candidates: list[str]) -> str | None:
    """후보 경로 목록에서 실행 가능한 첫 번째 명령어 반환"""
    import shutil
    for candidate in candidates:
        if shutil.which(candidate) or (Path(candidate).exists() and os.access(candidate, os.X_OK)):
            return candidate
    return None


def check_kordoc() -> dict[str, bool | str]:
    """kordoc 및 Node.js 설치 상태 확인"""
    result: dict[str, bool | str] = {}

    # Node.js
    node_cmd = _find_executable(_NODE_CANDIDATES)
    if node_cmd:
        try:
            r = subprocess.run([node_cmd, "--version"], capture_output=True, text=True)
            result["node"] = r.returncode == 0
            result["node_version"] = r.stdout.strip()
            result["node_cmd"] = node_cmd
        except Exception:
            result["node"] = False
            result["node_version"] = "실행 오류"
    else:
        result["node"] = False
        result["node_version"] = "미설치"

    # npm
    npm_cmd = _find_executable(_NPM_CANDIDATES)
    if npm_cmd:
        try:
            r = subprocess.run([npm_cmd, "--version"], capture_output=True, text=True)
            result["npm"] = r.returncode == 0
            result["npm_version"] = r.stdout.strip()
            result["npm_cmd"] = npm_cmd
        except Exception:
            result["npm"] = False
            result["npm_version"] = "실행 오류"
    else:
        result["npm"] = False
        result["npm_version"] = "미설치"

    # kordoc 전역 설치 여부
    kordoc_cmd = _find_executable(_KORDOC_CANDIDATES)
    if kordoc_cmd:
        try:
            env = {**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")}
            r = subprocess.run([kordoc_cmd, "--version"], capture_output=True, text=True, env=env)
            result["kordoc_global"] = r.returncode == 0
            result["kordoc_version"] = r.stdout.strip() or r.stderr.strip()
            result["kordoc_cmd"] = kordoc_cmd
        except Exception:
            result["kordoc_global"] = False
    else:
        result["kordoc_global"] = False

    # npx 사용 가능 여부
    npx_cmd = _find_executable(_NPX_CANDIDATES)
    result["npx"] = bool(npx_cmd)
    if npx_cmd:
        result["npx_cmd"] = npx_cmd

    return result


def get_kordoc_command() -> list[str] | None:
    """
    사용 가능한 kordoc 실행 커맨드 반환.
    전역 설치 우선, 없으면 npx 사용.
    kordoc CLI 형식: kordoc <file> [-o output] [--format markdown]
    """
    deps = check_kordoc()

    if deps.get("kordoc_global") and deps.get("kordoc_cmd"):
        return [str(deps["kordoc_cmd"])]
    elif deps.get("npx") and deps.get("node"):
        return [str(deps.get("npx_cmd", "npx")), "--yes", "kordoc"]
    else:
        return None


def install_kordoc_global() -> bool:
    """kordoc을 npm 전역 설치"""
    click.echo("  📦 kordoc 전역 설치 중... (npm install -g kordoc)")
    try:
        result = subprocess.run(
            ["npm", "install", "-g", "kordoc"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            click.echo("  ✅ kordoc 설치 완료")
            return True
        else:
            click.echo(f"  ❌ 설치 실패: {result.stderr[:200]}", err=True)
            return False
    except subprocess.TimeoutExpired:
        click.echo("  ❌ 설치 타임아웃", err=True)
        return False
    except FileNotFoundError:
        click.echo("  ❌ npm이 설치되어 있지 않습니다. brew install node 후 재시도", err=True)
        return False


def convert_hwp_to_md(
    hwp_path: Path,
    output_path: Path,
    timeout: int = 60,
) -> dict:
    """
    단일 HWP/HWPX 파일을 Markdown으로 변환.
    kordoc CLI를 subprocess로 호출.
    """
    cmd = get_kordoc_command()
    if cmd is None:
        return {
            "status": "error",
            "error": "kordoc 또는 Node.js가 설치되어 있지 않습니다.\n"
                     "설치: brew install node && npm install -g kordoc",
        }

    ext = hwp_path.suffix.lower()
    if ext not in {".hwp", ".hwpx"}:
        return {"status": "error", "error": f"지원하지 않는 형식: {ext} (HWP/HWPX만 지원)"}

    if not hwp_path.exists():
        return {"status": "error", "error": f"파일을 찾을 수 없습니다: {hwp_path}"}

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # kordoc CLI 형식: kordoc <file> -o <output> [--format markdown] [--silent]
        # node가 /opt/homebrew/bin에 있으므로 PATH 명시
        env = {**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")}

        run_cmd = cmd + [str(hwp_path), "--output", str(output_path), "--format", "markdown", "--silent"]

        click.echo(f"  🔄 변환 중: {hwp_path.name}")
        result = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            env=env,
        )

        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            with open(output_path, encoding="utf-8") as f:
                char_count = len(f.read().strip())
            return {
                "status": "success",
                "method": "kordoc",
                "char_count": char_count,
                "output": str(output_path),
            }
        else:
            # --output 없이 stdout으로 받는 방식도 시도
            err_msg = result.stderr.strip() or result.stdout.strip() or "kordoc 변환 실패"

            alt_cmd = cmd + [str(hwp_path), "--format", "markdown", "--silent"]
            result2 = subprocess.run(
                alt_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                env=env,
            )

            if result2.returncode == 0 and result2.stdout.strip():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result2.stdout)
                char_count = len(result2.stdout.strip())
                return {
                    "status": "success",
                    "method": "kordoc_stdout",
                    "char_count": char_count,
                    "output": str(output_path),
                }

            return {
                "status": "error",
                "error": f"kordoc 실패: {err_msg[:300]}",
                "returncode": result.returncode,
            }

    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"변환 타임아웃 ({timeout}초)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def convert_hwp_batch(
    source_dir: Path,
    output_dir: Path,
    timeout: int = 60,
) -> list[dict]:
    """
    디렉토리 내 모든 HWP/HWPX 파일 일괄 변환.
    """
    hwp_files = list(source_dir.glob("*.hwp")) + list(source_dir.glob("*.hwpx"))
    hwp_files = [f for f in hwp_files if not f.name.startswith(".")]

    if not hwp_files:
        click.echo(f"  ℹ️  HWP/HWPX 파일 없음: {source_dir}")
        return []

    click.echo(f"  🗂  발견된 HWP/HWPX: {len(hwp_files)}개")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for hwp_path in sorted(hwp_files):
        out_path = output_dir / hwp_path.with_suffix(".md").name
        result = convert_hwp_to_md(hwp_path, out_path, timeout=timeout)
        result["source"] = str(hwp_path)
        results.append(result)

        status_icon = "✅" if result["status"] == "success" else "❌"
        click.echo(
            f"  {status_icon} {hwp_path.name}"
            + (f" → {result.get('char_count', 0):,}자" if result["status"] == "success" else f" — {result.get('error', '')[:60]}")
        )

    return results


@click.command()
@click.option("--input", "-i", "input_path", type=click.Path(exists=True), help="입력 HWP/HWPX 파일 경로")
@click.option("--output", "-o", "output_path", type=click.Path(), help="출력 MD 경로")
@click.option("--dir", "-d", "source_dir", type=click.Path(exists=True), help="일괄 변환할 디렉토리")
@click.option("--output-dir", type=click.Path(), help="일괄 변환 출력 디렉토리")
@click.option("--timeout", default=60, show_default=True, help="파일당 변환 타임아웃(초)")
@click.option("--check-deps", is_flag=True, help="의존성 설치 상태 확인")
@click.option("--install", is_flag=True, help="kordoc을 npm 전역 설치")
def main(
    input_path: str | None,
    output_path: str | None,
    source_dir: str | None,
    output_dir: str | None,
    timeout: int,
    check_deps: bool,
    install: bool,
) -> None:
    """HWP/HWPX → Markdown 변환 (kordoc 래퍼)"""

    if check_deps:
        deps = check_kordoc()
        click.echo("=== kordoc 의존성 상태 ===")
        click.echo(f"  {'✅' if deps.get('node') else '❌'} Node.js: {deps.get('node_version', '미설치')}")
        click.echo(f"  {'✅' if deps.get('npm') else '❌'} npm: {deps.get('npm_version', '미설치')}")
        click.echo(f"  {'✅' if deps.get('kordoc_global') else '❌'} kordoc (전역): {deps.get('kordoc_version', '미설치')}")
        click.echo(f"  {'✅' if deps.get('npx') else '❌'} npx")
        click.echo()
        cmd = get_kordoc_command()
        if cmd:
            click.echo(f"✅ 사용 가능한 실행 커맨드: {' '.join(cmd)}")
        else:
            click.echo("❌ kordoc 실행 불가")
            click.echo("   설치: brew install node && npm install -g kordoc")
        return

    if install:
        deps = check_kordoc()
        if not deps.get("npm"):
            click.echo("❌ npm이 없습니다. 먼저 node를 설치하세요: brew install node", err=True)
            sys.exit(1)
        success = install_kordoc_global()
        sys.exit(0 if success else 1)

    if source_dir:
        # 일괄 변환
        src = Path(source_dir)
        out_d = Path(output_dir) if output_dir else src.parent / "normalized_md"
        results = convert_hwp_batch(src, out_d, timeout=timeout)

        success_count = sum(1 for r in results if r["status"] == "success")
        fail_count = len(results) - success_count
        click.echo(f"\n변환 완료: 성공 {success_count}개 / 실패 {fail_count}개")

        if fail_count > 0:
            sys.exit(1)

    elif input_path:
        if not output_path:
            out = Path(input_path).with_suffix(".md")
        else:
            out = Path(output_path)

        result = convert_hwp_to_md(Path(input_path), out, timeout=timeout)

        if result["status"] == "success":
            click.echo(f"✅ 변환 완료: {out}")
            click.echo(f"   텍스트: {result.get('char_count', 0):,}자")
        else:
            click.echo(f"❌ 변환 실패: {result.get('error', '알 수 없는 오류')}", err=True)
            sys.exit(1)

    else:
        click.echo("사용법 오류: --input, --dir, --check-deps, --install 중 하나를 지정하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
