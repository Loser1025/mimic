from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    ok: bool
    output: str      # 最大 3000 文字
    duration: float  # 秒
    framework: str


def detect_framework(cwd: str, modified_path: str) -> str | None:
    """プロジェクトのテストフレームワークを検出する。"""
    root = Path(cwd)
    path = Path(modified_path)
    if path.suffix == ".py":
        if any((root / f).exists() for f in ("pytest.ini", "pyproject.toml", "setup.cfg")):
            return "pytest"
        if list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
            return "pytest"
    elif path.suffix in (".ts", ".tsx", ".js", ".jsx"):
        if (root / "package.json").exists():
            return "npm"
    return None


def find_related_tests(modified_path: str, cwd: str) -> list[str]:
    """変更ファイルに関連するテストファイルを返す。"""
    path = Path(modified_path)
    root = Path(cwd)
    stem = path.stem
    patterns = [
        f"test_{stem}.py",
        f"{stem}_test.py",
        f"tests/test_{stem}.py",
        f"tests/{stem}_test.py",
        f"test/test_{stem}.py",
    ]
    found = []
    for pattern in patterns:
        found.extend(str(p) for p in root.glob(f"**/{pattern}"))
    return list(dict.fromkeys(found))  # 重複除去・順序保持


def run_tests(test_files: list[str], cwd: str, timeout: int = 30) -> TestResult:
    """
    テストを実行して TestResult を返す。
    追加インストール不要: pytest があれば使い、なければ python -m unittest にフォールバック。
    """
    if not test_files:
        return TestResult(
            ok=True, output="関連テストが見つかりませんでした。",
            duration=0.0, framework="none"
        )

    t0 = time.time()

    def _run(cmd: list[str], framework: str) -> TestResult:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=cwd, encoding="utf-8", errors="replace"
            )
            duration = time.time() - t0
            output = (result.stdout + result.stderr).strip()[:3000]
            return TestResult(
                ok=(result.returncode == 0), output=output,
                duration=duration, framework=framework
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                ok=False, output=f"タイムアウト（{timeout}秒）",
                duration=float(timeout), framework=framework
            )

    # ── Strategy 1: pytest（インストール済みなら使う）─────────────
    try:
        subprocess.run(
            ["python", "-m", "pytest", "--version"],
            capture_output=True, timeout=5
        )
        return _run(
            ["python", "-m", "pytest"] + test_files + ["--tb=short", "-q", "--no-header"],
            "pytest"
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # pytest なし → フォールバック

    # ── Strategy 2: python -m unittest（標準ライブラリ・追加インストール不要）──
    # ファイルパスをモジュールパス形式に変換（tests/test_foo.py → tests.test_foo）
    module_args = []
    for f in test_files:
        p = Path(f)
        rel = p.relative_to(Path(cwd)) if p.is_absolute() else p
        module_args.append(
            str(rel).replace("\\", "/").replace("/", ".").removesuffix(".py")
        )

    return _run(
        ["python", "-m", "unittest"] + module_args + ["-v"],
        "unittest"
    )
