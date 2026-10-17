#!/usr/bin/env python3
"""Check mechanical research-delivery rules for a pull request.

This script intentionally avoids judging scientific meaning. It only checks
facts that CI can decide consistently and reports direct repair instructions.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

TYPE_LABELS = {
    "progress": "研究进展（Progress PR）",
    "engineering": "代码重构 / 工程维护",
    "paper": "Paper Design",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".webp"}
CODE_SUFFIXES = {".py", ".r", ".ipynb", ".sh", ".jl", ".m"}
RESULT_SUFFIXES = {".csv", ".json", ".parquet", ".feather", ".npy", ".npz"}
AUTHOR_CONFIRMATIONS = (
    "我已逐字阅读并理解本 PR",
    "我已检查对应的 Report / Design / 工程材料",
    "本 PR 的主张、数字和边界与对应材料一致",
)
L1_PATH_RE = re.compile(r"^paper-top-design/L1[^/]*\.md$")
EXPERIMENT_PATH_RE = re.compile(r"^codes/experiment/([^/]+)/")
L2_PATH_RE = re.compile(r"^paper-top-design/L2[^/]*\.md$")
FIXED_REPORT_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/blob/[0-9a-fA-F]{40}/([^\s)<>#]+)",
    re.IGNORECASE,
)


def _checked(body: str, text: str) -> bool:
    """Return whether a checklist line containing text is checked."""
    return re.search(rf"^- \[[xX]\].*{re.escape(text)}", body, re.MULTILINE) is not None


def _selected_types(body: str) -> list[str]:
    """Return the PR types selected in the standard template."""
    return [key for key, label in TYPE_LABELS.items() if _checked(body, label)]


def _experiment_ids(changed_files: Iterable[str]) -> set[str]:
    """Extract changed experiment directory names, excluding aggregate files."""
    experiment_ids: set[str] = set()
    for path in changed_files:
        match = EXPERIMENT_PATH_RE.match(path)
        if match and not match.group(1).startswith("_"):
            experiment_ids.add(match.group(1))
    return experiment_ids


def _has_real_file(directory: Path) -> bool:
    """Return whether a directory contains a non-metadata file."""
    return directory.is_dir() and any(
        path.is_file() and path.name != ".DS_Store" for path in directory.rglob("*")
    )


def _report_files(experiment_dir: Path) -> list[Path]:
    """Accept readable report formats and explicit README Report links."""
    reports: set[Path] = set()
    # A report can use any document format, but images and sidecar assets are not reports.
    document_suffixes = {".md", ".markdown", ".html", ".htm", ".pdf", ".docx", ".txt", ".rst", ".tex"}
    for directory_name in ("report", "reports"):
        directory = experiment_dir / directory_name
        if directory.is_dir():
            reports.update(path for path in directory.iterdir() if path.suffix.lower() in document_suffixes)
    reports.update(path for path in experiment_dir.glob("*")
                   if "report" in path.stem.lower() and path.suffix.lower() in document_suffixes)
    readme = experiment_dir / "README.md"
    if readme.is_file():
        for target in re.findall(r"\[Report\]\(([^)]+)\)", readme.read_text(encoding="utf-8"), re.IGNORECASE):
            # Explicit report entry points allow other readable formats and legacy names.
            target = unquote(target.split("#", 1)[0].strip("<>"))
            candidate = (experiment_dir / target).resolve()
            if candidate.is_relative_to(experiment_dir.resolve()) and candidate.suffix.lower() not in IMAGE_SUFFIXES - {".pdf"}:
                reports.add(candidate)
    return sorted(path.resolve() for path in reports if path.is_file() and path.stat().st_size)


def _has_code(experiment_dir: Path) -> bool:
    """Accept local code or an established shared-analysis implementation."""
    return _has_real_file(experiment_dir / "code") or any(
        path.is_file() and path.suffix.lower() in CODE_SUFFIXES
        for root in (experiment_dir, experiment_dir.parent / "_shared-analysis")
        for path in root.rglob("*")
        if root.is_dir()
    )


def _has_results(experiment_dir: Path) -> bool:
    """Accept established results/metrics layouts and explicit result artifacts."""
    if any(
        _has_real_file(experiment_dir / directory_name)
        for directory_name in ("results", "metrics")
    ):
        return True
    return any(
        path.is_file()
        and path.suffix.lower() in RESULT_SUFFIXES
        and any(word in path.stem.lower() for word in ("result", "metric", "summary"))
        for path in experiment_dir.glob("*")
    )


def check_delivery(
    *, title: str, body: str, changed_files: list[str], repo_root: Path
) -> list[str]:
    """Return actionable CI errors for one pull request."""
    errors: list[str] = []
    selected = _selected_types(body)
    if len(selected) != 1:
        errors.append("PR 类型必须且只能勾选一项。")
        return errors

    pr_type = selected[0]
    for confirmation in AUTHOR_CONFIRMATIONS:
        if not _checked(body, confirmation):
            errors.append(f"请勾选作者确认：{confirmation}。")

    l1_files = [path for path in changed_files if L1_PATH_RE.match(path)]
    l2_files = [path for path in changed_files if L2_PATH_RE.match(path)]
    # Deleted experiment directories do not need new reports; their evidence stays in Git.
    experiment_ids = {experiment_id for experiment_id in _experiment_ids(changed_files)
                      if (repo_root / "codes" / "experiment" / experiment_id).is_dir()}
    linked_paths = {unquote(path) for path in FIXED_REPORT_RE.findall(body)}
    weekly = _checked(body, "每周汇总")

    if pr_type == "progress":
        if len(experiment_ids) > 1 and not weekly:
            errors.append("单项 Progress PR 只能交付一个实验；每周汇总请勾选‘每周汇总’。")
        if l1_files:
            errors.append("Progress PR 不能修改 L1；请把 L1 变更拆到独立的 [L1] PR。")
        if not _checked(body, "Progress 已说明怎样服务当前 L1"):
            errors.append("请勾选确认：Progress 已说明怎样服务当前 L1。")
        if not experiment_ids:
            # Diagnostic or aggregate-only progress still needs durable research evidence.
            valid_links = [path for path in linked_paths
                           if path.startswith("codes/experiment/")
                           and ".." not in Path(path).parts
                           and (repo_root / path).is_file()
                           and ((repo_root / path).resolve() == (repo_root / "codes/experiment/report.md").resolve()
                                or any((repo_root / path).resolve() in _report_files(directory)
                                       for directory in (repo_root / "codes/experiment").glob("*") if directory.is_dir()))]
            if not valid_links:
                errors.append("Progress PR 必须提供含 40 位提交 SHA 的实验 Report 或总体报告链接。")

    for experiment_id in sorted(experiment_ids):
        experiment_dir = repo_root / "codes" / "experiment" / experiment_id
        for required_file in (experiment_dir / "README.md", experiment_dir / "detail.md"):
            if not required_file.is_file():
                errors.append(f"实验缺少必需入口：{required_file.relative_to(repo_root)}。")
        reports = _report_files(experiment_dir)
        if not reports:
            errors.append(f"实验 {experiment_id} 必须保存非空 Report（推荐 MD，也可 HTML 等），并在 README 链接入口。")
        readme = experiment_dir / "README.md"
        if readme.is_file():
            entries = re.findall(r"\[Report\]\(([^)]+)\)", readme.read_text(encoding="utf-8"), re.IGNORECASE)
            if not any((experiment_dir / unquote(entry.split("#", 1)[0].strip("<>"))).resolve() in reports for entry in entries):
                errors.append(f"实验 {experiment_id} 的 README 必须用 [Report](相对路径) 链接当前报告。")
        if pr_type == "progress" and not any(
            path.startswith(f"codes/experiment/{experiment_id}/")
            and ".." not in Path(path).parts
            and (repo_root / path).resolve() in reports for path in linked_paths
        ):
            errors.append(f"固定 Report 链接必须指向本次修改的同一实验目录 {experiment_id} 中的实际报告，使用 40 位提交 SHA。")
        if not _has_code(experiment_dir):
            errors.append(f"实验 {experiment_id} 必须保存实际代码。")
        if not _has_results(experiment_dir):
            errors.append(f"实验 {experiment_id} 必须保存实际结果或指标。")

    if l1_files and pr_type != "paper":
        errors.append("修改 L1 的 PR 必须选择 Paper Design。")
    if pr_type == "paper":
        if bool(l1_files) == bool(l2_files):
            errors.append("Paper Design 必须且只能修改 L1 或 L2 中的一层；不能混改两层。")
        layer = "L1" if l1_files else "L2"
        if f"[{layer}]" not in title:
            errors.append(f"修改 {layer} 的 PR 标题必须包含 [{layer}]。")
        allowed = set(l1_files if l1_files else l2_files) | {"paper-top-design/decision-log.md"}
        if any(path not in allowed for path in changed_files):
            errors.append("设计 PR 必须独立提交，只含对应层设计文件和必要 decision log；不能混代码、实验产物或稿件。")

    return errors


def _git_changed_files(base_sha: str, head_sha: str, repo_root: Path) -> list[str]:
    """Read changed paths from Git using the immutable PR endpoints."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}...{head_sha}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    """Load the GitHub event, run checks, and print concise CI output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    event = json.loads(args.event.read_text(encoding="utf-8"))
    pull_request = event["pull_request"]
    changed_files = _git_changed_files(
        pull_request["base"]["sha"],
        pull_request["head"]["sha"],
        args.repo_root,
    )

    errors = check_delivery(
        title=pull_request.get("title", ""),
        body=pull_request.get("body") or "",
        changed_files=changed_files,
        repo_root=args.repo_root,
    )
    if errors:
        print("Research delivery gate failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Research delivery gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
