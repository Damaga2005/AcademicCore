"""Certification states — no ambiguous 'equivalent to X' claims without proof."""

IMPLEMENTED = "IMPLEMENTED"      # code exists
VERIFIED = "VERIFIED"            # tests pass against oracle
BENCHMARKED = "BENCHMARKED"      # measured vs reference
SIMULATED = "SIMULATED"          # simulation result, not physical truth
VISUAL_ONLY = "VISUAL_ONLY"      # rendering only, no solver behind
EXPERIMENTAL = "EXPERIMENTAL"    # prototype, do not trust

ALL = (IMPLEMENTED, VERIFIED, BENCHMARKED, SIMULATED, VISUAL_ONLY, EXPERIMENTAL)
