"""Turn a case list and a contact list into an epiinfer dataset folder.

    python examples/convert_case_list.py cases.csv contacts.csv data/my_data

``cases.csv`` has one row per symptomatic episode: ``person,onset`` (onset = date symptoms
began). ``contacts.csv`` has one row per contact: ``date,a,b``. Person labels can be any text.
The same is available as ``epiinfer from-cases``.

Each case is written as symptomatic for DURATION days from onset and recovered for the
REC_DURATION days after that. Change both to fit your disease, and pass the same values to
epiinfer (--duration, --rec-duration).
"""

import sys

from epiinfer.convert import cases_to_dataset

DURATION, REC_DURATION = 7, 7

info = cases_to_dataset(*sys.argv[1:4], duration=DURATION, rec_duration=REC_DURATION)
print(f"wrote {info['folder']}: {info['people']} people, days 0-{info['days'] - 1} "
      f"(day 0 = {info['day0']})")
