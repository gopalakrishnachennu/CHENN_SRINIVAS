#!/usr/bin/env python3
"""Phase 3 CLI — export ResumeJSON to DOCX/PDF or launch the operator UI."""

from __future__ import annotations

import argparse
import json
import sys

from resume_engine.export.service import SUPPORTED_FORMATS, export_resume


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 resume document export / UI")
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="Export a resume JSON to DOCX and/or PDF")
    export_p.add_argument("--resume", required=True, help="Path to ResumeJSON (validated final preferred)")
    export_p.add_argument(
        "--format",
        default="docx,pdf",
        help="Comma-separated formats: docx,pdf",
    )
    export_p.add_argument("--out-dir", default=None, help="Output directory")
    export_p.add_argument("--basename", default=None, help="Output filename stem")
    export_p.add_argument(
        "--candidate-profile",
        default=None,
        help="Optional candidate profile JSON for name/contact header",
    )

    ui_p = sub.add_parser("ui", help="Launch Phase 3 operator UI")
    ui_p.add_argument("--host", default="127.0.0.1")
    ui_p.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.command == "ui":
        from resume_engine.ui.app import main as ui_main

        ui_main(host=args.host, port=args.port)
        return 0

    formats = [part.strip().lower() for part in args.format.split(",") if part.strip()]
    for fmt in formats:
        if fmt not in SUPPORTED_FORMATS:
            print(f"Unsupported format: {fmt}", file=sys.stderr)
            return 2

    result = export_resume(
        args.resume,
        formats=formats,
        output_dir=args.out_dir,
        basename=args.basename,
        contact=args.candidate_profile,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
