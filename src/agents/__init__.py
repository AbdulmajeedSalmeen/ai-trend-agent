"""Agents: the steps that decide what to look at before they answer.

Everything else in this project is a stage, a rule, or a single question to a model.
An agent belongs here only when the work genuinely needs a loop: when what to read
next depends on what the last read said. Each one gathers and proposes; a rule in the
same module then checks the evidence it cited actually exists, and only that rule
decides what the run records.
"""
