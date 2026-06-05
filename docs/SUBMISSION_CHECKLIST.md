# Submission Checklist

## Instructor Requirements

| Requirement | Status | Evidence |
| --- | --- | --- |
| Pinned Python libraries | Ready | `requirements.txt` |
| Frozen CSV inputs | Ready | `data/raw/*.csv` |
| Clear Python implementation | Ready | `src/run_project.py` |
| Backtrader backtests | Ready | `results/backtrader_*.csv` |
| `1,000,000 TL` initial capital | Ready | `config/project_config.yaml` |
| `100,000 TL` fixed cash sizing | Ready | `src/run_project.py` |
| Zero commission | Ready | `config/project_config.yaml` |
| Saved result files | Ready | `results/*.csv` |
| Tables and figures | Ready | `figures/*.png` |
| PDF presentation | Ready with one input | `presentation/bist_factor_project_presentation.pdf` |
| Participant names in PDF | Needs input | Set `project.group_participants` and rerun. |
| Fresh-session reproducibility | Validate before push | Follow `docs/REPRODUCIBILITY.md`. |

## Presentation Coverage

The PDF includes:

- Paper summary.
- Data and factor definitions.
- Strategy construction.
- Code examples.
- FMP and IC outputs.
- Backtrader results.
- Improvement attempts.
- Monte Carlo interpretation.
- Final investment judgment.

## Before GitHub Push

1. Fill `project.group_participants` in `config/project_config.yaml`.
2. Run `py src/run_project.py`.
3. Confirm `results/project_audit_checklist.csv` contains only `OK`.
4. Open `presentation/bist_factor_project_presentation.pdf` and visually verify participant names.
5. Keep `data/raw/*.csv` in the repository so the instructor can reproduce the completed baseline.
6. Review `docs/GITHUB_READINESS.md` before pushing.

## Experimental BIST Appendix

`data_bist/` is an experimental appendix, not the completed submission run. The final submitted results come from `data/`, `results/`, `figures/`, and `presentation/`.
