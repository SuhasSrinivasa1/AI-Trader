#!/usr/bin/env python3
from pathlib import Path

# Execute the reviewed v2.4.9 patch with the exact v2.4.8 executor shutdown ordering.
script = Path('hotfix/run_v249.py').read_text(encoding='utf-8')
old = "'''    public void onDestroy() {\\n        entryExecutor.shutdownNow();\\n''',"
new = "'''    public void onDestroy() {\\n        earlyExitExecutor.shutdownNow();\\n        entryExecutor.shutdownNow();\\n''',"
if script.count(old) != 1:
    raise RuntimeError('unexpected v2.4.9 onDestroy old-pattern')
script = script.replace(old, new, 1)
old = "'''    public void onDestroy() {\\n        NotificationListenerHealth.markDisconnected();\\n        entryExecutor.shutdownNow();\\n''')"
new = "'''    public void onDestroy() {\\n        NotificationListenerHealth.markDisconnected();\\n        earlyExitExecutor.shutdownNow();\\n        entryExecutor.shutdownNow();\\n''')"
if script.count(old) != 1:
    raise RuntimeError('unexpected v2.4.9 onDestroy new-pattern')
script = script.replace(old, new, 1)
exec(compile(script, 'hotfix/run_v249.py', 'exec'), {'__name__': '__main__'})
print('Applied final v2.4.9 reliability + protection wrapper')
