"""The council engine: a stepped host driving a file-exchange seat protocol.

The host is never a long-running process. `init` creates the run; each `step`
invocation reads what is on disk, advances the run as far as it can, and
exits. All durable state lives in the run directory; there is no in-memory
state to lose. A seat invocation that dies without writing its answer file
simply never happened (owner ruling M5); a run that fails validation twice is
FAILED and publishes nothing.
"""
