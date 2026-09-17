from pathlib import Path
import re, sys
root=Path(sys.argv[1])
p=root/'app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt'
s=p.read_text()
# The generated v1.0.4 Global Lead block can contain a literal newline inside
# joinToString("") after Python escaping. Replace only that malformed separator.
s,n=re.subn(r'lines\.joinToString\("\s*"\)', 'lines.joinToString(" • ")', s, count=1)
if n!=1:
    raise SystemExit('missing malformed Global Lead BigText separator')
p.write_text(s)
print('v1.0.4 notification separator compile fix applied')
