"""Delegates to reconcile CLI when invoked as python -m resume_engine.maintenance."""

from resume_engine.maintenance.reconcile import main

if __name__ == "__main__":
    raise SystemExit(main())
