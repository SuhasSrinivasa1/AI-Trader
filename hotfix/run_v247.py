#!/usr/bin/env python3
import runpy

# Compatibility wrapper used only by the v2.4.8 branch.
# Always chain from the exact v2.4.7 standalone patch that passed CI.
runpy.run_path('hotfix/run_v247_standalone.py', run_name='__main__')
