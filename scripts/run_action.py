"""GitHub Action runner for inventory-policy-lab."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

FORMATS = {"markdown", "json"}


def _reject_input_controls(value: str, label: str, *, allow_tab: bool = False) -> None:
    """Keep external Action inputs from changing logs, paths or CLI boundaries."""
    if "\n" in value or "\r" in value:
        raise ValueError(f"Action {label} must not contain line breaks.")
    # Tab remains a normal shlex argument separator, not part of CSV/report paths.
    if any(
        (ord(char) < 32 and (char != "\t" or not allow_tab))
        or 127 <= ord(char) <= 159
        for char in value
    ):
        raise ValueError(f"Action {label} must not contain terminal control characters.")


def _append_output(name: str, value: str) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _fail(message: str, code: int = 2) -> int:
    print(message, file=sys.stderr)
    _append_output("exit-code", str(code))
    _append_output("succeeded", "false")
    _append_output("report-path", "")
    return code


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _reserved_argument(args: list[str]) -> str | None:
    """Prevent extra Action args from bypassing execution or owned outputs.

    argparse accepts unambiguous long-option prefixes, so protecting only the
    complete spellings of --output and --format is insufficient.
    """
    protected_long = ("--help", "--version", "--format", "--output")
    for token in args:
        if token == "-h" or (token.startswith("-o") and not token.startswith("--")):
            return token
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            if len(name) > 2 and any(option.startswith(name) for option in protected_long):
                return token
    return None


def _default_report_path(report_format: str) -> Path:
    runner_temp = os.getenv("RUNNER_TEMP")
    if runner_temp:
        root = Path(runner_temp)
    else:
        workspace = Path(os.getenv("GITHUB_WORKSPACE", "."))
        root = workspace / ".inventory-policy-lab"
    suffix = "json" if report_format == "json" else "md"
    return root / f"inventory-policy-report.{suffix}"


def _resolve_report_path(raw: str, report_format: str) -> Path:
    if not raw:
        return _default_report_path(report_format).resolve()
    path = Path(raw)
    if path.is_absolute():
        raise ValueError("Action report-path must be relative to GITHUB_WORKSPACE.")
    workspace = Path(os.getenv("GITHUB_WORKSPACE", ".")).resolve()
    resolved = (workspace / path).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("Action report-path must stay within GITHUB_WORKSPACE.") from exc
    return resolved


def _resolve_input_path(raw: str) -> Path:
    """Keep the Action's input CSV inside the caller workspace."""
    workspace = os.getenv("GITHUB_WORKSPACE")
    if not workspace:
        raise ValueError("GITHUB_WORKSPACE is required for the Action.")
    if raw == "-":
        raise ValueError("Action input path must name a CSV inside GITHUB_WORKSPACE.")
    _reject_input_controls(raw, "input path")
    path = Path(raw)
    if path.is_absolute():
        raise ValueError("Action input path must be relative to GITHUB_WORKSPACE.")
    root = Path(workspace).resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("Action input path must stay within GITHUB_WORKSPACE.") from exc
    return resolved


def _write_summary(path: Path, report_format: str) -> None:
    target = os.getenv("GITHUB_STEP_SUMMARY")
    if not target:
        return
    text = path.read_text(encoding="utf-8")
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write("## inventory-policy-lab\n\n")
        if report_format == "json":
            # The payload can contain untrusted backticks in SKU labels.
            maximum = max((len(run) for run in re.findall(r"`+", text)), default=0)
            fence = "`" * max(3, maximum + 1)
            handle.write(f"{fence}json\n")
            handle.write(text.rstrip())
            handle.write(f"\n{fence}\n")
        else:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")


def main() -> int:
    csv_path = os.getenv("INVENTORY_INPUT_PATH", "")
    if not csv_path:
        return _fail("Action input path is required.")

    report_format = os.getenv("INVENTORY_INPUT_FORMAT", "markdown").strip().lower()
    if report_format not in FORMATS:
        return _fail("Action input format must be markdown or json.")

    summary = _parse_bool(os.getenv("INVENTORY_INPUT_SUMMARY", "false"))
    if summary is None:
        return _fail("Action input summary must be true or false.")

    raw_args = os.getenv("INVENTORY_INPUT_ARGS", "")
    try:
        _reject_input_controls(raw_args, "args", allow_tab=True)
        extra_args = shlex.split(raw_args)
    except ValueError as exc:
        return _fail(f"Invalid action args: {exc}")

    reserved = _reserved_argument(extra_args)
    if reserved is not None:
        return _fail(
            f"Argument {reserved!r} is not allowed in Action args; "
            "use format/report-path inputs or run help/version in the standalone CLI."
        )

    try:
        csv_path = str(_resolve_input_path(csv_path))
    except ValueError as exc:
        return _fail(str(exc))

    try:
        raw_report_path = os.getenv("INVENTORY_INPUT_REPORT_PATH", "")
        _reject_input_controls(raw_report_path, "report-path")
        report_path = _resolve_report_path(raw_report_path, report_format)
    except ValueError as exc:
        return _fail(str(exc))
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(f"Cannot create report directory: {exc}", 3)

    try:
        action_path = Path(os.environ["INVENTORY_ACTION_PATH"]).resolve()
    except KeyError:
        return _fail("INVENTORY_ACTION_PATH is not available.")

    env = dict(os.environ)
    src = str(action_path / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else os.pathsep.join((src, existing))

    command = [
        sys.executable,
        "-m",
        "inventory_policy_lab",
        csv_path,
        *extra_args,
        "--format",
        report_format,
        "--output",
        str(report_path),
    ]
    completed = subprocess.run(
        command,
        cwd=os.getenv("GITHUB_WORKSPACE") or None,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)

    code = completed.returncode
    if code == 0 and not report_path.is_file():
        print("Analysis completed without creating the report file.", file=sys.stderr)
        code = 3

    succeeded = code == 0
    _append_output("exit-code", str(code))
    _append_output("succeeded", "true" if succeeded else "false")
    _append_output("report-path", str(report_path) if succeeded else "")

    if succeeded and summary:
        _write_summary(report_path, report_format)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
