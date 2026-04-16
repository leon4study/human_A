# H2 Pre-Registered Analysis Spec

## Scope

This document freezes the H2 analysis design before writing the final hypothesis-testing code.

H2 is **not** treated as a causal proof of clogging.  
With the current dataset, H2 can only support:

- `drain_ec`-based response lag changes over time/events
- consistency checks against zone-level substrate signals

It cannot isolate clogging from crop growth, seasonal effects, or operating policy changes.

## Phase 0 Diagnostics

Source data:

- `human_A/src/selected_smartfarm.csv`

### Check 1. `drain_ec_ds_m` update cadence

Result:

- Consecutive identical-value run length quantiles:
  - median: `1 min`
  - p95: `2 min`
  - p99: `4 min`
  - p99.9: `11 min`
- Rounded-to-3-decimals run lengths were the same.

Decision:

- Effective update unit `K = 1 minute`

Implication:

- Noise and lag detection are defined on 1-minute raw data.

### Check 2. Event definition and isolated-event count

Candidate `pump_on` definition:

- `pump_rpm > 100`

Observed structure:

- `pump_rpm > 100` yields `90` starts
- exactly `1` start per day
- start time is fixed at `05:51`
- active block duration is about `729 min`
- inactive block duration is about `711 min`

Isolation test:

- For pre-off windows `30/60/120 min`
- and post-on windows `30/60/120 min`
- isolated-event count stayed `90/90` in every case

Decision:

- Event = daily supply-block onset defined by `pump_rpm > 100`
- Isolated-event rule:
  - previous `60 min` all off
  - next `60 min` all on

Gate:

- minimum event count `>= 30`
- minimum isolated-event ratio `>= 10%`

Result:

- PASS (`90` events, `100%` isolated ratio)

### Check 3. `drain_ec` noise distribution

Noise sample:

- `|diff(drain_ec_ds_m)|` during inactive periods (`pump_rpm <= 100`)

Observed distribution:

- median: `0.002`
- p90: `0.006`
- p95: `0.007`
- p99: `0.009`
- skew: `0.919`
- kurtosis: `0.802`

Threshold comparison:

- `3 * sigma = 0.006327`
- `3 * 1.4826 * MAD = 0.004448`

Decision:

- Use robust threshold family
- Significant `drain_ec` change:
  - `|diff(drain_ec_ds_m)| > 3 * 1.4826 * MAD(inactive baseline)`

Reason:

- The distribution is skewed enough that fixed `3σ` is unstable for event detection.

### Check 4. Event-lag detection failure rate

Detection rule:

- For each event start `t_i`
- search `0 to 60 min` after `t_i`
- first time `|diff(drain_ec_ds_m)|` exceeds the frozen threshold

Failure-rate comparison:

- `3σ` threshold:
  - detected: `28`
  - failed: `62`
  - failure rate: `68.9%`
  - FAIL
- `MAD` threshold:
  - detected: `70`
  - failed: `20`
  - failure rate: `22.2%`
  - PASS

Gate:

- failure rate `<= 30%`

Decision:

- Keep censored events
- Do not drop failed detections from the main analysis table

### Check 5. Zone-level auxiliary signal availability

Using the same event starts and a robust MAD threshold on each zone signal:

- `zone1_substrate_moisture_pct`: failure `8.9%`
- `zone2_substrate_moisture_pct`: failure `18.9%`
- `zone3_substrate_moisture_pct`: failure `18.9%`
- `zone1_substrate_ec_ds_m`: failure `13.3%`
- `zone2_substrate_ec_ds_m`: failure `22.2%`
- `zone3_substrate_ec_ds_m`: failure `35.6%`

Gate:

- at least one auxiliary zone signal must be analyzable

Result:

- PASS

## Frozen H2 Analysis Design

### Main signal

- Event onset:
  - `pump_rpm > 100`
  - onset = transition from off to on
- Main response signal:
  - `|diff(drain_ec_ds_m)|`
- Detection window:
  - `0 to 60 minutes`

### Event-lag definition

For each event start `t_i`:

- find first `t >= t_i` within `60 min` such that
  - `|diff(drain_ec_ds_m)| > 3 * 1.4826 * MAD(inactive baseline)`
- define:
  - `lag_i = t - t_i`
- if no such `t` exists:
  - event is right-censored

### Time axis

Main analysis axis:

- cumulative event index (`1..90`)

Important limitation:

- In this dataset, event index and operating day are effectively the same axis
- therefore `event count vs day` is **not** an independent robustness check
- calendar-time effects and repeated-irrigation effects are not identifiable separately
- any time-trend result must be interpreted as a mixed temporal/operational pattern, not a uniquely identified clogging effect

### Censoring-aware main model

Primary inferential model:

- Cox proportional hazards model
- outcome:
  - time-to-first-significant-response
- censoring:
  - right-censored at `60 min`
- main covariate:
  - cumulative event index

Reason:

- censoring must be retained
- the hypothesis is about how response timing changes across repeated events
- Cox allows adding control variables later if defensible covariates are available

Secondary displays:

- Kaplan-Meier curves for early vs late events
- descriptive split only, not an independent confirmatory test

Additional note:

- if uncensored-only auxiliary regressions are reported, their standard errors must use HAC / Newey-West style correction because adjacent events are temporally correlated

### Onset detection logic

Base response signal:

- `abs(diff(drain_ec_ds_m))`

Frozen onset rule:

- onset is the first timestamp within `0 to 60 min`
- where the response signal exceeds the frozen threshold
- for at least `2` consecutive 1-minute samples

Reason:

- this reduces sensitivity to one-off sensor spikes

Boundary check:

- implementation must report the share of detections occurring exactly at `60 min`
- if a material pile-up is observed at the right boundary, interpretation must flag possible boundary artifact

### Main conclusion strength

Allowed claim:

- `drain_ec` response lag changes across repeated supply events
- and the direction/consistency can be compared with zone-level substrate signals

Not allowed:

- direct proof that clogging caused the lag pattern
- direct proof of drain flow onset
- interchangeable use of `channeling` and `clogging` as one directional hypothesis

## Frozen Gates

These values are locked before implementation:

- effective cadence `K = 1 min`
- event definition: `pump_rpm > 100`
- isolation rule:
  - pre-off `60 min`
  - post-on `60 min`
- response window `tau_max = 60 min`
- significant-change threshold:
  - `3 * 1.4826 * MAD`
- minimum event count `>= 30`
- minimum isolated-event ratio `>= 10%`
- maximum failure rate `<= 30%`
- at least one auxiliary zone signal must pass
- onset confirmation:
  - `2` consecutive samples above threshold
- main inferential model:
  - Cox proportional hazards

## Frozen Interpretation Rules

- H2 is an **event-response lag** analysis, not a continuous-time CCF proof
- CCF, if included later, is auxiliary only
- censored events remain part of the analysis
- calendar time and cumulative event exposure are inseparable in this dataset
- if implementation requires changing any value above, this document must be revised first
