#!/usr/bin/env python3
"""Deprecated shim: use `claim-graph` or `python -m research_agent.cli.claim_graph`."""

from research_agent.cli.claim_graph import main

if __name__ == "__main__":
    raise SystemExit(main())
