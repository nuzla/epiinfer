# Dataset format

A dataset is a folder of CSV files. Person ids are integers `0 … N-1`; days are integers
starting at 0 (the contact list usually starts at day 1).

Compartments: **S** susceptible, **A** infected and infectious but not yet symptomatic
(the paper's *E*), **I** symptomatic and isolated, **R** recovered. The forecast target is
the number of people in **I**.

## What each engine needs

| File | Columns | final engine (default) | contact engine (`--engine contact`) | compartmental engine (`--engine compartmental`) |
|---|---|---|---|---|
| `individual_day_state.csv` | `id,day,state`, one row per person per day; state `0=S, 1=A, 2=I, 3=R` | yes, but only states **2 (I)** and **3 (R)** are read | yes, including **1 (A)** | no |
| `timed_edges.csv` | `day,i,j`: an undirected contact between `i` and `j` on `day` | yes | yes | no |
| `age_group_population.csv` | `age_group,population` (ids are then assumed to be contiguous ranges in this order) | gives the population size | one of these two | yes |
| `individual_age_group.csv` | `id,age_group` (0-based index or a label from the population file); unambiguous | not used | one of these two | no |
| `states_total.csv` | `day,S,A,I,R` (any column order) | no | no (derived); checks the state encoding | yes (I and R totals) |
| `daily_group_infected.csv` | `day,age,infected`: symptomatic count per group | no | no (derived) | yes |
| `daily_group_avg_contacts.csv` | `day,age,c` (or `avg_contacts`): mean contacts per person in the group | no | no; only sanity-checks the id→age mapping | yes |

The **final engine** is the October 2026 paper's method. It needs only to know who is
symptomatic (I) and who has recovered (R) each day, plus the contacts. It rebuilds the
pre-symptomatic history itself: people first seen symptomatic on day e + inc were exposed
on day e, and the unseen exposures are drawn in proportion to contacts. This is what real
contact-tracing data usually record, so you do not have to know who is in A.

Any other state code, including 0 and 1, is simply "not I and not R". A person missing from
a day's records also counts as neither that day. The population size is the sum of
`age_group_population.csv` if present, otherwise the largest id + 1.

The **contact engine** is the 2025 code behind the earlier tables. It is seeded with who was
in A on recent days, so it needs state 1 recorded (it refuses a dataset that records none:
without it the forecast would silently say that nobody new gets infected). Simulators provide
it; real data usually do not. It forecasts each age group as well as the total.

The **compartmental engine** is EpiInfer, the earlier model the paper compares against. It
needs no individual records and no contact list: only daily counts per age group (people
symptomatic, average contacts) and the totals. That makes it the option for aggregate
surveillance data. In `daily_group_avg_contacts.csv` a missing day repeats the previous one.

`epiinfer describe --data FOLDER` tells you which engines a folder supports.

Every day from 0 to the last day should be present in `individual_day_state.csv`. The last day
that has any row is taken as the last observed day, so if you write only the I and R rows,
make sure the final day has at least one row (any state), or a forecast will start earlier
than you expect. `daily_group_infected.csv` may omit zero counts.

## A minimal dataset for the final engine

```text
my_data/
  individual_day_state.csv     id,day,state      (only rows with state 2 or 3 are needed)
  timed_edges.csv              day,i,j
  age_group_population.csv     age_group,population     (or omit: N = largest id + 1)
```

If your records are a case list (`person,onset`: who, and the date symptoms began) and a
contact list (`date,a,b`), `epiinfer from-cases` writes this folder for you:

```bash
epiinfer from-cases --cases cases.csv --contacts contacts.csv --out my_data \
    --duration 7 --rec-duration 7
```

It does the following:

- **Ids and days.** It numbers the people 0 … N−1 and the days from the earliest date.
  `people.csv` maps the ids back to your labels.
- **State file.** It writes state 2 for each case on the `duration` days from onset, then
  state 3 for the next `rec_duration` days.
- **Contacts.** It writes them as `day,i,j`.

Pass the same `--duration` and `--rec-duration` to `forecast` and `run`.

## Mapping a simulator's states

If you have a different state model, collapse it to these four. For OpenABM-Covid19 the
paper uses:

| OpenABM state | Compartment |
|---|---|
| SUSCEPTIBLE | S |
| PRESYMPTOMATIC, PRESYMPTOMATIC_MILD | A |
| SYMPTOMATIC, SYMPTOMATIC_MILD | I |
| HOSPITALISED, CRITICAL, HOSPITALISED_RECOVERING, RECOVERED, DEATH | R |

`make_p1_figure.py` in the original code also folds never-symptomatic ASYMPTOMATIC people
into A by subtraction; the model script itself does not. See `docs/PAPER_VS_CODE.md`.

## What the loaders check

* the required files and columns exist;
* ids in both the state file and the edge list lie in `0 … N-1`;
* contact engine: every id gets an age group in range, and the ids in `individual_age_group.csv`
  lie in `0 … N-1`;
* compartmental engine: the columns each of its four files needs (a missing one is named);
* contact engine: the susceptible code is confirmed against `states_total.csv` (when
  present);
* contact engine: mean day-1 contacts per group is compared with
  `daily_group_avg_contacts.csv`. A warning appears at >15%; every ABM dataset supplied with
  the paper triggers it, harmlessly.

## Timing parameters

`inc` (days pre-symptomatic), `duration` (days symptomatic) and, for the final engine,
`rec_duration` (days recovered before becoming susceptible again) are not inferred. Set them
from your data with `--inc`, `--duration`, `--rec-duration`, or `Config(...)`.

| Data | inc / duration / rec_duration |
|---|---|
| AgeMixABM | 7 / 7 / 7 |
| OpenABM | 5 / 11 / – (the measured median dwell times) |
