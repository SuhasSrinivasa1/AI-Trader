#!/usr/bin/env python3
from pathlib import Path

# Execute the reviewed v2.4.8 patch after removing the stale-buffer write that CI detected.
script = Path('hotfix/run_v248.py').read_text(encoding='utf-8')
old = "p=J/'ProductionNotificationService.java'; t=read(p)"
new = "p=J/'ProductionNotificationService.java'"
if script.count(old) != 1:
    raise RuntimeError('unexpected ProductionNotificationService patch header')
script = script.replace(old, new, 1)
old_tail = "\nwrite(p,t)\n\n# Ensure accepted/pending entries"
new_tail = "\n\n# Ensure accepted/pending entries"
if script.count(old_tail) != 1:
    raise RuntimeError('unexpected stale-buffer write location')
script = script.replace(old_tail, new_tail, 1)
exec(compile(script, 'hotfix/run_v248.py', 'exec'), {'__name__': '__main__'})

# Standalone launcher identity should not retain an old device-role label.
strings = Path('android-stable/app/src/main/res/values/strings.xml')
text = strings.read_text(encoding='utf-8')
text = text.replace('<string name="app_name">Multyfi AutoBuy MASTER</string>', '<string name="app_name">Multyfi AutoBuy</string>')
text = text.replace('<string name="app_name">Multyfi AutoBuy S24</string>', '<string name="app_name">Multyfi AutoBuy</string>')
strings.write_text(text, encoding='utf-8')
if '<string name="app_name">Multyfi AutoBuy</string>' not in text:
    raise RuntimeError('standalone launcher label was not normalized')
print('Applied final v2.4.8 ultra-fast standalone patch')
