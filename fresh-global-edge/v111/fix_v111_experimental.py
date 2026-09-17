from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'app/src/main/java/com/suhas/ucsentinel/ui/AppNavigation.kt'
s=p.read_text()
ann='@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)\n\n'
if not s.startswith('@file:OptIn('):
    s=ann+s
    p.write_text(s)
print('v1.1.1 Material3 opt-in applied')
