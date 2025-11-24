from pathlib import Path
p=Path('src/vrp/solver.py')
t=p.read_text(encoding='utf-8')
marker='    # Fallback:'
idx=t.rfind(marker)
print(idx)
