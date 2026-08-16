---
name: data-science-pandas-numpy
description: pandas/numpy conventions for scientific data pipelines (actigraphy, sleep metrics, compliance checks)
keywords: pandas, numpy, csv, dataframe, actigraphy, sleep, epoch, circadian, scipy
---

# pandas / numpy data pipelines

For projects processing epoch-level or time-series scientific data (e.g.
actigraphy CSVs, sleep-metric exports, compliance-check pipelines):

- Vectorize over `DataFrame`/`Series` operations before reaching for
  `.apply()` or a Python loop — a loop over rows is the first thing to
  suspect when a pipeline that should take seconds takes minutes.
- Timestamps: parse once to `datetime64` (`pd.to_datetime`, explicit
  `format=` when known) and keep everything downstream in that dtype —
  repeated string-parsing of the same column is a common silent slowdown.
- Validate units and sampling rate at the point data enters the pipeline
  (e.g. confirm 60-second epochs, not assume it) — a silently mismatched
  epoch length invalidates every downstream metric without erroring.
- Missing/invalid data: prefer an explicit `NaN`-aware calculation
  (`np.nanmean`, `.dropna()` at a named step) over letting `NaN` propagate
  silently through a chain of arithmetic — a metric that's quietly `NaN`
  end-to-end is easy to miss in a report.
- For periodogram/statistical metrics (IS, IV, M10/L5, Enright/Chi-square
  periodograms and similar), don't reimplement the math from scratch if a
  reference implementation already exists in the codebase (e.g. a prior R
  port) — translate it faithfully and note any deviation, since these are
  validated research metrics, not just arbitrary calculations.
- Multi-page PDF reports: build one page's figure at a time and close it
  (`plt.close(fig)`) before the next — accumulating open figures across a
  long report is a classic silent memory leak.
