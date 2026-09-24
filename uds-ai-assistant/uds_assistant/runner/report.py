"""Result reports: JUnit XML (CI), Markdown (humans)."""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .runner import RunSummary


def to_junit(summary: RunSummary, suite_name: str = "uds-generated") -> str:
    suite = ET.Element("testsuite", name=suite_name, tests=str(summary.total),
                       failures=str(summary.failed), errors=str(summary.errors),
                       time=str(summary.duration_s))
    for r in summary.results:
        case = ET.SubElement(suite, "testcase", classname=f"uds.{r.category}", name=f"{r.test_id} {r.title}")
        if r.verdict == "fail":
            ET.SubElement(case, "failure", message=r.message).text = _transcript(r)
        elif r.verdict == "error":
            ET.SubElement(case, "error", message=r.message).text = _transcript(r)
    return ET.tostring(suite, encoding="unicode", xml_declaration=False)


def _transcript(r) -> str:
    lines = []
    for s in r.steps:
        mark = "OK " if s.passed else "BAD"
        lines.append(f"{mark} #{s.n} [{s.role}] {s.request or s.message} -> {s.response} | {s.message}")
    return "\n".join(lines)


def to_markdown(summary: RunSummary, title: str = "UDS test run report") -> str:
    out = [f"# {title}", "",
           f"- Target: **{summary.target}**" + (f" (faults injected: {', '.join(summary.faults)})" if summary.faults else ""),
           f"- Result: **{summary.passed}/{summary.total} passed** ({summary.pass_rate}%), "
           f"{summary.failed} failed, {summary.errors} errors, {summary.duration_s}s", ""]
    fails = summary.failures()
    if fails:
        out += ["## Failures", "", "| Test | Title | Category | Reason |", "|---|---|---|---|"]
        for r in fails:
            out.append(f"| {r.test_id} | {r.title} | {r.category} | {r.message.replace('|', '/')} |")
    else:
        out.append("All tests passed.")
    return "\n".join(out) + "\n"
