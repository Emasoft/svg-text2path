# Per-object diff vs Inkscape (advanced sample)

Generated on 2025-11-21 with:

```bash
python -m text2path.main samples/test_text_to_path_advanced.svg /tmp/out_latest.svg --precision 6
# per-object split already in samples/test_text_to_path_advanced/
python - <<'PY'
import subprocess, re
from pathlib import Path
samples_dir = Path('samples/test_text_to_path_advanced')
parts = sorted(samples_dir.glob('text*.svg'))
out_dir = Path('/tmp/parts_out'); out_dir.mkdir(exist_ok=True)
results = []
for part in parts:
    base = part.stem
    ours = out_dir / f"{base}_ours.svg"
    ink = out_dir / f"{base}_ink.svg"
    subprocess.run(['python','-m','text2path.main', part, ours,'--precision','6'], check=True)
    subprocess.run([
        'inkscape','--export-type=svg','--export-plain-svg','--export-text-to-path',
        '--export-overwrite','--no-convert-text-baseline-spacing',
        f'--export-filename={ink}','--convert-dpi-method=none', part
    ], check=True)
    res = subprocess.run(['python','-m','text2path.frame_comparer', ink, ours, '--no-html', '--output-dir', out_dir / base], capture_output=True, text=True, check=True)
    m = re.search(r'Comparison:\s*([0-9.]+)%', res.stdout)
    diff = float(m.group(1)) if m else None
    results.append((base, diff))
print("id,diff%")
for b,d in results:
    print(f"{b},{d:.4f}")
PY
```

Results (ours vs Inkscape text-to-path) — lower is better:

| id    | diff % |
|-------|--------|
| text2 | 0.2038 |
| text3 | 12.8151 |
| text37 | 0.2641 |
| text39 | 18.8984 |
| text4 | 0.0000 |
| text40 | 0.0548 |
| text41 | 5.0144 |
| text42 | 28.9454 |
| text43 | 0.7345 |
| text44 | 22.3719 |
| text45 | 12.9716 |
| text47 | 5.0702 |
| text48 | 1.0038 |
| text49 | 3.7017 |
| text50 | 3.1919 |
| text51 | 3.2033 |
| text52 | 35.1738 |
| text53 | 4.7804 |
| text54 | 24.1211 |
| text7 | 0.0313 |
| text8 | 0.0000 |
| text9 | 0.1978 |

Worst offenders: text52, text42, text54, text44, text39, text45, text3, text41, text47. These align with the observed layout/anchor issues (Arabic/inline-size, condensed/italic lines, etc.).
