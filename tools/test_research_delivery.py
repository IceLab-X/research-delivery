"""Unit tests for the mechanical research-delivery gate."""

import tempfile
import shutil
import unittest
from pathlib import Path

from check_research_delivery import check_delivery


CONFIRMATIONS = """
- [x] 我已逐字阅读并理解本 PR，可以解释其中每个判断。
- [x] 我已检查对应的 Report / Design / 工程材料，认可其表达，并可以完整讲给别人听。
- [x] 本 PR 的主张、数字和边界与对应材料一致。
"""


def progress_body(report_path: str = "codes/experiment/exp1/report/report.md") -> str:
    """Return a minimal valid Progress PR body."""
    return f"""
- [x] 研究进展（Progress PR）
- [ ] 代码重构 / 工程维护（含功能实现、bug 修复）
- [ ] Paper Design（L1 / L2 实质设计变更）
{CONFIRMATIONS}
- [x] Progress 已说明怎样服务当前 L1；风险与探索偏差已显露，正式修改 L1 时另提独立设计 PR。
Progress Report：https://github.com/org/repo/blob/{'a' * 40}/{report_path}
"""


def paper_body() -> str:
    """Return a minimal valid Paper Design PR body."""
    return f"""
- [ ] 研究进展（Progress PR）
- [ ] 代码重构 / 工程维护（含功能实现、bug 修复）
- [x] Paper Design（L1 / L2 实质设计变更）
{CONFIRMATIONS}
"""


class ResearchDeliveryTests(unittest.TestCase):
    """Exercise the few intentionally enforced delivery rules."""

    def setUp(self) -> None:
        """Create one complete experiment fixture."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        experiment = self.root / "codes" / "experiment" / "exp1"
        (experiment / "report").mkdir(parents=True)
        (experiment / "code").mkdir()
        (experiment / "results").mkdir()
        (experiment / "figures").mkdir()
        (experiment / "README.md").write_text("# exp1\n[Report](report/report.md)\n", encoding="utf-8")
        (experiment / "detail.md").write_text("# detail\n", encoding="utf-8")
        (experiment / "report" / "report.md").write_text(
            "# report\n![result](../figures/result.png)\n", encoding="utf-8"
        )
        (experiment / "code" / "run.py").write_text("# Run experiment.\n", encoding="utf-8")
        (experiment / "results" / "metrics.csv").write_text("metric,value\n", encoding="utf-8")
        (experiment / "figures" / "result.png").write_bytes(b"figure")
        self.changed = [
            "codes/experiment/exp1/report/report.md",
            "codes/experiment/exp1/detail.md",
            "codes/experiment/exp1/results/metrics.csv",
        ]

    def tearDown(self) -> None:
        """Remove the temporary fixture."""
        self.temp_dir.cleanup()

    def test_complete_progress_passes(self) -> None:
        """A complete single-experiment Progress PR passes."""
        errors = check_delivery(
            title="[EXP-1] Result",
            body=progress_body(),
            changed_files=self.changed,
            repo_root=self.root,
        )
        self.assertEqual(errors, [])

    def test_missing_result_fails_directly(self) -> None:
        """Missing actual results produce a repairable message."""
        experiment = self.root / "codes" / "experiment" / "exp1"
        (experiment / "results" / "metrics.csv").unlink()
        (experiment / "figures" / "result.png").unlink()
        errors = check_delivery(
            title="[EXP-1] Result",
            body=progress_body(),
            changed_files=self.changed,
            repo_root=self.root,
        )
        self.assertTrue(any("实际结果或指标" in error for error in errors))
        self.assertFalse(any("至少一张结果图" in error for error in errors))

    def test_progress_cannot_change_l1(self) -> None:
        """L1 changes cannot hide inside a Progress PR."""
        errors = check_delivery(
            title="[EXP-1] Result",
            body=progress_body(),
            changed_files=self.changed + ["paper-top-design/L1-story.md"],
            repo_root=self.root,
        )
        self.assertTrue(any("Progress PR 不能修改 L1" in error for error in errors))

    def test_independent_l1_pr_passes(self) -> None:
        """An isolated and clearly titled L1 proposal passes the mechanical gate."""
        errors = check_delivery(
            title="[L1] Narrow the paper claim",
            body=paper_body(),
            changed_files=["paper-top-design/L1-story.md"],
            repo_root=self.root,
        )
        self.assertEqual(errors, [])

    def test_existing_equivalent_layout_passes(self) -> None:
        """Legacy names pass without a repository-specific configuration file."""
        experiment = self.root / "codes" / "experiment" / "legacy"
        (experiment / "reports").mkdir(parents=True)
        (experiment / "metrics").mkdir()
        (experiment / "figures").mkdir()
        (experiment / "README.md").write_text("# legacy\n[Report](reports/RESULTS.md)\n", encoding="utf-8")
        (experiment / "detail.md").write_text("# detail\n", encoding="utf-8")
        (experiment / "run.py").write_text("# Run.\n", encoding="utf-8")
        (experiment / "metrics" / "summary.json").write_text("{}\n", encoding="utf-8")
        (experiment / "figures" / "result.png").write_bytes(b"figure")
        (experiment / "reports" / "RESULTS.md").write_text(
            "# Results\n![result](../figures/result.png)\n", encoding="utf-8"
        )
        errors = check_delivery(
            title="[EXP-2] Result",
            body=progress_body("codes/experiment/legacy/reports/RESULTS.md"),
            changed_files=[
                "codes/experiment/_shared-analysis/plot.py",
                "codes/experiment/legacy/reports/RESULTS.md",
            ],
            repo_root=self.root,
        )
        self.assertEqual(errors, [])

    def test_report_link_must_match_changed_experiment(self) -> None:
        """A fixed link to another experiment cannot satisfy this delivery."""
        errors = check_delivery(
            title="[EXP-1] Result",
            body=progress_body("codes/experiment/other/report/report.md"),
            changed_files=self.changed,
            repo_root=self.root,
        )
        self.assertTrue(any("同一实验目录" in error for error in errors))

    def test_weekly_multiple_experiments_each_need_report_link(self) -> None:
        """Weekly aggregation permits multiple experiments but no missing reports."""
        shutil.copytree(self.root / "codes/experiment/exp1", self.root / "codes/experiment/exp2")
        changed = self.changed + ["codes/experiment/exp2/report/report.md"]
        body = progress_body() + "\n- [x] 每周汇总（允许多个实验）\n"
        errors = check_delivery(title="[Weekly] Evidence", body=body,
                                changed_files=changed, repo_root=self.root)
        self.assertTrue(any("exp2" in error for error in errors))
        body += f"\nhttps://github.com/org/repo/blob/{'b' * 40}/codes/experiment/exp2/report/report.md"
        self.assertEqual(check_delivery(title="[Weekly] Evidence", body=body,
                                       changed_files=changed, repo_root=self.root), [])
        self.assertTrue(check_delivery(title="Result", body=body.replace("[x] 每周汇总", "[ ] 每周汇总"),
                                       changed_files=changed, repo_root=self.root))

    def test_html_report_with_inline_results_passes_without_image_file(self) -> None:
        """HTML and table-only reports do not require external image files."""
        experiment = self.root / "codes/experiment/exp1"
        (experiment / "report/report.md").unlink()
        (experiment / "figures/result.png").unlink()
        (experiment / "report/results.html").write_text("<h1>Results</h1><table><tr><td>3</td></tr></table>")
        (experiment / "README.md").write_text("[Report](report/results.html)")
        self.assertEqual(check_delivery(title="Result", body=progress_body("codes/experiment/exp1/report/results.html"),
                         changed_files=["codes/experiment/exp1/report/results.html"], repo_root=self.root), [])

    def test_readme_declares_custom_report_format(self) -> None:
        """An explicit Report entry supports formats beyond the suggested ones."""
        experiment = self.root / "codes/experiment/exp1"
        (experiment / "report/report.md").unlink()
        (experiment / "analysis.custom").write_text("Readable report")
        (experiment / "README.md").write_text("[Report](analysis.custom)")
        self.assertEqual(check_delivery(title="Result", body=progress_body("codes/experiment/exp1/analysis.custom"),
                         changed_files=self.changed, repo_root=self.root), [])

    def test_link_to_missing_or_wrong_report_fails(self) -> None:
        """Being in the same directory is insufficient if the report does not exist."""
        errors = check_delivery(title="Result", body=progress_body("codes/experiment/exp1/report/missing.html"),
                                changed_files=self.changed, repo_root=self.root)
        self.assertTrue(any("实际报告" in error for error in errors))

    def test_l2_design_passes_but_mixed_design_fails(self) -> None:
        """L2 design is separate from code, manuscript, and L1 changes."""
        l2 = ["paper-top-design/L2-argument-design.md", "paper-top-design/decision-log.md"]
        self.assertEqual(check_delivery(title="[L2] Revise comparison", body=paper_body(),
                                       changed_files=l2, repo_root=self.root), [])
        for extra in ["codes/core/method.py", "paper/manuscript/draft.tex", "paper-top-design/L1-story.md"]:
            self.assertTrue(check_delivery(title="[L2] Revise comparison", body=paper_body(),
                                           changed_files=l2 + [extra], repo_root=self.root))

    def test_l2_status_can_change_in_progress(self) -> None:
        """Non-design L2 maintenance need not create another design PR."""
        self.assertEqual(check_delivery(title="Result", body=progress_body(),
                         changed_files=self.changed + ["paper-top-design/L2-argument-design.md"], repo_root=self.root), [])

    def test_aggregate_only_progress_passes(self) -> None:
        """A diagnosis or summary uses durable report evidence without a new experiment."""
        (self.root / "codes/experiment/report.md").write_text("# Current evidence")
        self.assertEqual(check_delivery(title="[Weekly] Diagnosis", body=progress_body("codes/experiment/report.md"),
                         changed_files=["codes/experiment/report.md"], repo_root=self.root), [])

    def test_engineering_cannot_bypass_experiment_report(self) -> None:
        """The Engineering label cannot waive the per-experiment report requirement."""
        (self.root / "codes/experiment/exp1/report/report.md").unlink()
        body = CONFIRMATIONS + "\n- [x] 代码重构 / 工程维护"
        errors = check_delivery(title="Fix experiment", body=body, changed_files=self.changed, repo_root=self.root)
        self.assertTrue(any("Report" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
