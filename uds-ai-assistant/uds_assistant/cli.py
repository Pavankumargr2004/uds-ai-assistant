"""Command-line interface for uds-ai-assistant.

Examples
--------
    uds-ai generate data/samples/bcm_ecu_profile.yaml -o tests.json
    uds-ai run data/samples/bcm_ecu_profile.yaml tests.json --faults accept_any_key
    uds-ai coverage data/samples/bcm_ecu_profile.yaml tests.json
    uds-ai export data/samples/bcm_ecu_profile.yaml tests.json --format python -o out/
    uds-ai serve --port 8000
    uds-ai ui
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .coverage import compute_coverage
from .generator.exporters import export_all
from .generator.models import TestCase
from .generator.suites import build_suite
from .protocol.profile import load_profile
from .runner.report import to_junit, to_markdown
from .runner.runner import Runner
from .runner.transport import SimTransport


def _load_tests(path: Path) -> list[TestCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [TestCase.model_validate(d) for d in data]


def _dump_tests(tests: list[TestCase], path: Path) -> None:
    path.write_text(json.dumps([t.model_dump(mode="json") for t in tests], indent=2), encoding="utf-8")


def cmd_generate(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    tests = build_suite(profile)
    _dump_tests(tests, Path(args.output))
    cov = compute_coverage(profile, tests)
    print(f"Generated {len(tests)} test case(s) for {profile.name} -> {args.output}")
    print(f"Coverage: {cov['percent']}% ({cov['covered_items']}/{cov['total_items']} items)")
    if cov["gaps"]:
        print(f"Gaps ({len(cov['gaps'])}): " + ", ".join(cov["gaps"][:20]) + (" ..." if len(cov["gaps"]) > 20 else ""))
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    tests = _load_tests(Path(args.tests))
    cov = compute_coverage(profile, tests)
    print(json.dumps(cov, indent=2))
    return 0 if not cov["gaps"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    tests = _load_tests(Path(args.tests))
    if args.test_id:
        tests = [t for t in tests if t.id in set(args.test_id)]
    transport = SimTransport(profile, faults=args.faults or [])
    summary = Runner(profile, transport).run(tests, faults=args.faults or [])
    print(to_markdown(summary))
    if args.junit:
        Path(args.junit).write_text(to_junit(summary), encoding="utf-8")
        print(f"JUnit report written to {args.junit}")
    return 0 if summary.failed == 0 and summary.errors == 0 else 1


def cmd_export(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    tests = _load_tests(Path(args.tests))
    files = export_all(args.format, profile, tests)
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (outdir / name).write_text(content, encoding="utf-8")
        print(f"wrote {outdir / name}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    uvicorn.run("uds_assistant.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    import subprocess
    ui_path = Path(__file__).parent / "ui" / "app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(ui_path),
                            "--server.port", str(args.port)])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="uds-ai", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate the full systematic test suite for an ECU profile")
    g.add_argument("profile", help="path to the ECU profile YAML")
    g.add_argument("-o", "--output", default="tests.json", help="output JSON file")
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("coverage", help="report coverage of a test-case JSON file against a profile")
    c.add_argument("profile")
    c.add_argument("tests")
    c.set_defaults(func=cmd_coverage)

    r = sub.add_parser("run", help="run tests against the in-process simulator")
    r.add_argument("profile")
    r.add_argument("tests")
    r.add_argument("--test-id", action="append", help="run only this test id (repeatable)")
    r.add_argument("--faults", nargs="*", help="inject named simulator faults (see uds_assistant.simulator.mock_ecu.FAULTS)")
    r.add_argument("--junit", help="also write a JUnit XML report to this path")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("export", help="export tests to python/capl/json/csv/markdown")
    e.add_argument("profile")
    e.add_argument("tests")
    e.add_argument("--format", choices=["python", "capl", "json", "csv", "markdown"], default="python")
    e.add_argument("-o", "--output", default="export", help="output directory")
    e.set_defaults(func=cmd_export)

    s = sub.add_parser("serve", help="run the FastAPI server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    u = sub.add_parser("ui", help="run the Streamlit UI")
    u.add_argument("--port", type=int, default=8501)
    u.set_defaults(func=cmd_ui)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
