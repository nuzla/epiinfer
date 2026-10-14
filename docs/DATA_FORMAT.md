# Dataset format

A dataset is a folder of CSV files. Person ids are integers `0 … N-1`; days are integers
starting at 0 (the contact graph usually starts at day 1).

| File | Columns | Required |
|---|---|---|
| `individual_day_state.csv` | `id,day,state` — one row per person per day; state `0=S, 1=A, 2=I, 3=R` | yes |
| `timed_edges.csv` | `day,i,j` — an undirected contact between `i` and `j` on `day` | yes |
| `age_group_population.csv` | `age_group,population` (ids are then assumed to be contiguous ranges in this order) | one of these two |
| `individual_age_group.csv` | `id,age_group` (0-based group index) — **preferred**, unambiguous | one of these two |
| `states_total.csv` | `day,S,A,I,R` (any column order) — only used to auto-check the state encoding | no (derived) |
| `daily_group_infected.csv` | `day,age,infected` — symptomatic (I) count per group | no (derived) |
| `daily_group_avg_contacts.csv` | `day,age,c` (or `avg_contacts`) — used only to sanity-check the id→age mapping | no |

Every day from 0 to the last day should be present in `individual_day_state.csv`. Missing
days are treated as "nobody in that state". `daily_group_infected.csv` may omit zero
counts.

Compartments: **S** susceptible, **A** infected and infectious but not yet symptomatic
(the paper's *E*), **I** symptomatic and isolated, **R** recovered. The forecast target is
the number of people in **I**.

> **Important — the A state must be known.** As in the code behind the paper, the model is
> seeded with *who is in A* on recent days, read from `individual_day_state.csv`.
> Simulators provide this. Real contact-tracing data usually do not: they record
> symptomatic or tested people only. With such data you must first impute the A state
> (for example by back-dating confirmed cases by the incubation period). The paper's own
> reconstruction is not implemented yet; see `PAPER_VS_CODE.md`, item 2.

## Mapping your own data

If you have a different state model, collapse it to these four. For OpenABM-Covid19 the
paper uses:

| OpenABM state | Compartment |
|---|---|
| SUSCEPTIBLE | S |
| PRESYMPTOMATIC, PRESYMPTOMATIC_MILD | A |
| SYMPTOMATIC, SYMPTOMATIC_MILD | I |
| HOSPITALISED, CRITICAL, HOSPITALISED_RECOVERING, RECOVERED, DEATH | R |

(`make_p1_figure.py` in the original code also folds never-symptomatic ASYMPTOMATIC people
into A by subtraction; the model script itself does not. See `docs/PAPER_VS_CODE.md`.)

## What the loader checks

* required files/columns exist; ids in both the state file and the edge list lie in `0 … N-1`
* every id gets an age group in range
* the susceptible code is confirmed against `states_total.csv` (when present)
* mean day-1 contacts per group is compared with `daily_group_avg_contacts.csv` (warns at >15%)

## Timing parameters

`inc` (days in A) and `duration` (days in I) are not inferred. Set them from your data
(`--inc`, `--duration`, or `Config(inc=…, duration=…)`). Paper values: 7/7 for AgeMixABM,
5/11 for OpenABM (the measured median dwell times).
