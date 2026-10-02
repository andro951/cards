"""Load the actual UI dependency graph into an offline component document."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def ui_source():
    parts=[]
    for name in ('diagnostics','work','ui'):
        source=(ROOT/'site'/(name+'.js')).read_text(encoding='utf-8')
        parts.append('\n'.join(line for line in source.splitlines() if not line.startswith('import ')).replace('export ',''))
    return '\n'.join(parts)