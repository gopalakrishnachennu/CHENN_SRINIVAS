# PHASE 2.8 GATE 1 REPORT — Online Self-Learning (Shadow Mode)

**Status:** `PHASE 2.8 ONLINE LEARNING GATE 1 STATUS: PASS`  
**Starting commit:** `72d757064892b65c7a24e848a9609b3b6f9799df`  
**Ending commit:** `a3679af2651e2dbb9dbbd2088d651af2a77eaa60`  
**Branch:** `main`  
**GitHub Actions run:** `35818638569` (success)  
**River:** `0.26.1`  
**Mode:** `shadow` (active production reordering **not** enabled)

Architecture: [`docs/PHASE_2_8_ONLINE_LEARNING_ARCHITECTURE.md`](PHASE_2_8_ONLINE_LEARNING_ARCHITECTURE.md)

---

## Acceptance checklist

| Criterion | Result |
|-----------|--------|
| River 0.26.1 pinned | **PASS** |
| Python 3.11 CI | **PASS** |
| Python 3.12 CI | **PASS** |
| Deterministic strategy unchanged in shadow | **PASS** |
| Features deterministic / no PII | **PASS** |
| River ranks only eligible actions | **PASS** |
| No technology invention | **PASS** |
| Rewards bounded [0,1] | **PASS** |
| Invalid/failing cannot positively train | **PASS** |
| Only final accepted variants teach | **PASS** |
| Policy persisted safely (atomic + previous) | **PASS** |
| Policy failure falls back | **PASS** |
| SQLite decisions + observations | **PASS** |
| Replay dry-run available | **PASS** |
| Offline pytest PASS | **PASS** (**598**/3) |
| Ruff PASS | **PASS** (0) |
| Coverage ≥ 70 | **PASS** (**75.09%**) |
| Behavioral audit PASS | **PASS** (`ONLINE_LEARNING_SHADOW_VALIDATED`) |
| Implementation audit | **50/50** importable |

---

## Files created

- `resume_engine/learning/online/` (`config`, `schemas`, `feature_builder`, `reward_engine`, `river_policy`, `policy_store`, `shadow_runner`, `replay`)
- `tests/test_phase28_online_learning.py` (29 tests)
- `docs/PHASE_2_8_ONLINE_LEARNING_ARCHITECTURE.md`
- `docs/PHASE_2_8_GATE_1_REPORT.md`

## Files modified

- `requirements.txt` / `pyproject.toml` — pin `river==0.26.1`
- `.env.example` — online learning env vars
- `resume_engine/config/settings.py` — `ONLINE_LEARNING_STORAGE_DIR`
- `resume_engine/learning/repository.py` — decision/observation tables
- `resume_engine/strategy/variant_planner.py` — `list_eligible_positionings`
- `resume_engine/pipeline/phase2_pipeline.py` — shadow + observe hooks
- `resume_engine/reports/behavioral_audit.py` — shadow invariants
- `resume_engine/reports/implementation_audit.py` — online modules

---

## Local + CI metrics

| Metric | Value |
|--------|-------|
| Offline tests | **598** passed / **3** skipped |
| Phase 2.8 tests | **29** passed |
| Shadow decisions tested | ≥3 persisted decision cases |
| Coverage | **75.09%** |
| Ruff | **0** errors |
| River version | **0.26.1** |
| Policy persistence | atomic save + previous backup |
| Replay | `--dry-run` OK (no mutation) |
| GitHub 3.11 | SUCCESS (tests + cov + Ruff) |
| GitHub 3.12 | SUCCESS (tests + cov + Ruff) |

---

## Known limitations

1. Active mode is **not** enabled for production variant reordering.
2. Historical replay often skips records lacking reconstructible blueprint context.
3. LinUCB scores are ranking scores, not calibrated probabilities (`probability=null`).
4. Paid live OpenAI/Laya unchanged / not required for this gate.

---

# PHASE 2.8 ONLINE LEARNING GATE 1 STATUS: PASS
