"""Build results_slide.html (self-contained, no server needed) from data/results.json.

    python backend/make_slide.py --name "Rao Ghulam Mohiuddin" --roll 23K-0001
"""
import argparse
import html
import json

import config

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="Rao Ghulam Mohiuddin")
ap.add_argument("--roll", default="23K-0001")
a = ap.parse_args()

R = json.loads((config.DATA / "results.json").read_text(encoding="utf-8"))
rows, meta = R["summary"], R["meta"]
e = html.escape


def f(x, d=3):
    return "—" if x is None else f"{x:.{d}f}"


def note(key):
    return meta.get("not_run", {}).get(key)


fastest = min((r for r in rows if r["invalid_outputs"] < r["total_calls"]), key=lambda r: r["avg_move_latency_s"])
table = "".join(
    f"<tr><td><b>{e(r['name'])}</b><br><code>{e(r['id'])}</code>"
    f"{'<br><span class=warn>' + e(note(r['key'])) + '</span>' if note(r['key']) else ''}</td>"
    f"<td class='{'best' if r is fastest else ''}'>{f(r['avg_move_latency_s'])} s</td>"
    f"<td>{f(r['total_time_s'], 2)} s</td><td>{r['total_moves']}</td><td>{r['invalid_outputs']}</td>"
    f"<td>{r['solved']}/{r['trials']}</td><td>{f(r['success_rate'], 1)}%</td>"
    f"<td>{f(r['avg_gap'], 2) if r['avg_gap'] is not None else 'n/a'}</td></tr>"
    for r in rows)
max_lat = max(r["avg_move_latency_s"] for r in rows)
bars = "".join(
    f"<div class=bar><span>{e(r['name'])}</span><div class=track><div class=fill style='width:{100 * r['avg_move_latency_s'] / max_lat:.1f}%'></div></div>"
    f"<span>{f(r['avg_move_latency_s'])} s{' *' if r['invalid_outputs'] == r['total_calls'] else ''}</span></div>"
    for r in rows)
attempts = "".join(f"<li>{e(x)}</li>" for x in meta.get("frontier_attempts", []))
puzzles = " · ".join(f"{p['id']}: <code>{' '.join(p['scramble'])}</code> → optimal {p['optimal_len']}" for p in R["puzzles"])

best_rate = max(r["success_rate"] for r in rows)
top = [r for r in rows if r["success_rate"] == best_rate]
gapped = sorted((r for r in rows if r["avg_gap"] is not None), key=lambda r: r["avg_gap"])
n_p = len(R["puzzles"])
qa = [
    f"<b>Fastest decisions:</b> {e(fastest['name'])}, {f(fastest['avg_move_latency_s'])} s per move on average.",
    (f"<b>Highest solve rate:</b> {', '.join(e(r['name']) for r in top)} ({best_rate:.1f}%)." if best_rate > 0
     else f"<b>Highest solve rate:</b> none. Every model solved 0 of {n_p} puzzles within {meta['max_moves']} moves."),
    (f"<b>Shortest solutions:</b> {e(gapped[0]['name'])}, average optimality gap {gapped[0]['avg_gap']:.2f} moves." if gapped
     else "<b>Shortest solutions:</b> no model solved a puzzle, so no optimality gap could be measured."),
    f"<b>Did the fastest model give the best quality?</b> "
    f"{'Yes' if best_rate > 0 and fastest in top and (not gapped or gapped[0] is fastest) else 'No'}. "
    f"{e(fastest['name'])} solved {fastest['solved']}/{fastest['trials']}.",
    f"<b>Recommendation:</b> {e(meta.get('analysis', ''))}",
]

page = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>Benchmark Results Slide</title>
<style>
:root{{--bg:#0b0e14;--panel:#171b24;--line:#2a3142;--text:#e8ebf2;--muted:#8b93a7;--accent:#7aa2ff;--ok:#3ecf8e;--warn:#f5b84b}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,"Segoe UI",sans-serif;padding:28px 40px 80px}}
h1{{margin:0;font-size:30px}} .sub{{color:var(--muted);margin:4px 0 18px}}
.grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:18px}} @media(max-width:1000px){{.grid{{grid-template-columns:1fr}} body{{padding:18px 16px 80px}}}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;overflow-x:auto}}
.card h3{{margin:0 0 10px;font-size:14px;color:var(--muted)}}
table{{border-collapse:collapse;width:100%;min-width:640px}} th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}}
th:first-child,td:first-child{{text-align:left}} th{{color:var(--muted);font-size:12px}} td.best{{color:var(--ok);font-weight:700}}
code{{color:var(--muted);font-size:12px}} .warn{{color:var(--warn);font-size:12px;white-space:normal}}
.bar{{display:grid;grid-template-columns:170px 1fr 70px;gap:8px;align-items:center;margin:6px 0;font-size:13px}}
.track{{background:#1e2330;height:14px;border-radius:4px;overflow:hidden}} .fill{{height:100%;background:var(--accent)}}
ol li,ul li{{margin:6px 0}} .student{{position:fixed;left:0;right:0;bottom:0;background:var(--accent);color:#0b1020;font-weight:800;font-size:20px;text-align:center;padding:10px}}
</style></head><body>
<h1>Rubik's Cube Race: Benchmark Results</h1>
<div class=sub>{len(R['puzzles'])} identical puzzles · {meta['scramble_len']}-move scrambles (exact distance by BFS) · move limit {meta['max_moves']} · {e(meta['metric'])} · timeout {meta['timeout_s']} s · retries {meta['retries']} · {sum(r['total_calls'] for r in rows)} benchmark API calls</div>
<div class=grid>
 <div class=card><h3>Per-model statistics</h3><table><tr><th>Model</th><th>Avg latency / move</th><th>Total time</th><th>Total moves</th><th>Invalid outputs</th><th>Solved</th><th>Success rate</th><th>Avg optimality gap</th></tr>{table}</table>
 <p style="color:var(--muted);font-size:12px">Puzzles: {puzzles}. Optimality gap = model moves − exact shortest moves (solved trials only).</p></div>
 <div style="display:flex;flex-direction:column;gap:18px">
  <div class=card><h3>Average latency per move (lower is faster)</h3>{bars}<div style="color:var(--muted);font-size:12px">* every call was an error response</div></div>
  <div class=card><h3>Frontier LLM attempts</h3><ul>{attempts}</ul></div>
 </div>
</div>
<div class=card style="margin-top:18px"><h3>Answers to the experiment questions</h3><ol>{''.join(f'<li>{x}</li>' for x in qa)}</ol></div>
<div class=student>{e(a.name)} · {e(a.roll)}</div>
</body></html>"""
out = config.ROOT / "results_slide.html"
out.write_text(page, encoding="utf-8")
print("wrote", out)
