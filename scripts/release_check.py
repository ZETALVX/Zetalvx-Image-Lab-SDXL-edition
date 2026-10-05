#!/usr/bin/env python3
"""Source-export test adapter. The original verdict helper is retained unchanged.
The packaged release runner is replaced by the source-scoped runner; no installer.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def verdict(result):
    return {'run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)-len(result.expectedFailures),
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'expected_failures':len(result.expectedFailures),'unexpected_successes':len(result.unexpectedSuccesses),
        'gate_passed':result.wasSuccessful() and not result.skipped and not result.expectedFailures}

if __name__=='__main__':
    from tools.test_source import main
    raise SystemExit(main())
