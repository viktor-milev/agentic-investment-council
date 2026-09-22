"""The verdict ledger (UPGRADE-2 U7).

The council keeps a record it can be judged by. Every published verdict
writes one append-only row (`ledger.py`); a later script fills in what
happened at three, six and twelve months from an observation file and
scores it (`score.py`); a scorecard page shows the record (`report.py`).

Book-blind throughout: a row and the scorecard carry the subject's public
identity, never a size and never a holding. Standard library only; no
script here ever fetches.
"""
