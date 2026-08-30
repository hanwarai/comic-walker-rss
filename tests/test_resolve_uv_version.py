"""CI が uv のピンを読むスクリプト .github/scripts/resolve-uv-version.sh の仕様テスト。

このスクリプトは ci.yaml と gh-pages.yaml の両方から呼ばれ、標準出力がそのまま
GitHub Actions の $GITHUB_OUTPUT に追記される。出力形式・失敗時の終了コード・
実行ビットのいずれが壊れても CI が止まるため、ここで固定する。
"""

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / ".github" / "scripts" / "resolve-uv-version.sh"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _run(pyproject: Path) -> "subprocess.CompletedProcess[str]":
    # check=False: 失敗時の returncode / stderr を検証するテストなので例外にしない。
    return subprocess.run(
        [str(SCRIPT), str(pyproject)], capture_output=True, text=True, check=False
    )


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(content)
    return path


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} に実行ビットが無い (CI が直接起動する)"


def test_resolves_pin_from_repo_pyproject() -> None:
    pinned = re.search(r'"uv==([0-9]+\.[0-9]+\.[0-9]+)"', PYPROJECT.read_text())
    assert pinned is not None, "pyproject.toml の [dependency-groups] ci に uv のピンが無い"
    result = _run(PYPROJECT)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"version={pinned.group(1)}\n"


def test_emits_github_output_format(tmp_path: Path) -> None:
    path = _write(tmp_path, '[dependency-groups]\nci = ["uv==1.2.3"]\n')
    assert _run(path).stdout == "version=1.2.3\n"


def test_fails_when_pin_has_no_version(tmp_path: Path) -> None:
    path = _write(tmp_path, '[dependency-groups]\nci = ["uv"]\n')
    result = _run(path)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "could not resolve" in result.stderr


def test_fails_when_pyproject_is_missing(tmp_path: Path) -> None:
    assert _run(tmp_path / "absent.toml").returncode != 0
