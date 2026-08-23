from pathlib import Path
for i in range(8):
    p=Path(f'.github/scripts/scanner_v300_part{i}.py')
    exec(compile(p.read_text(), str(p), 'exec'), {})
print('NSE Unified Scanner v3.0.0 production patch complete')
