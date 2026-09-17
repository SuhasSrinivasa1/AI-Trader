from pathlib import Path
import re, sys
root=Path(sys.argv[1])
p=root/'app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt'
s=p.read_text()
# Replace the Global Lead BigText join expression as a whole. This is robust to
# whether the generator produced an escaped separator or a literal newline.
pat=r'\.setStyle\(NotificationCompat\.BigTextStyle\(\)\.bigText\(lines\.joinToString\(.*?\)\)\)'
replacement='.setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString(" • ")))'
s,n=re.subn(pat,replacement,s,count=1,flags=re.S)
if n!=1:
    raise SystemExit('missing Global Lead BigText join expression')
p.write_text(s)
print('v1.0.4 notification separator compile fix applied')
