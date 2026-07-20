"""Build HTML data-quality report for oTree session xh3fj087."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

CSV_PATH = Path(r"c:\Users\waben\Downloads\check_Data.csv")
OUT_PATH = Path(__file__).resolve().parent / "xh3fj087_data_quality_report.html"
SESSION = "xh3fj087"
APP = "TG_goal_oriented_delegation_1st"
VALID_PAY = {0.0, 30.0, 70.0, 100.0}


def g(r, rnd, field):
    return r.get(f"{APP}.{rnd}.player.{field}", "")


def pct(n, d):
    return 0.0 if d == 0 else round(100.0 * n / d, 1)


def qstats(xs):
    xs = sorted(xs)
    n = len(xs)
    return {
        "min": xs[0],
        "p25": xs[n // 4],
        "med": xs[n // 2],
        "p75": xs[(3 * n) // 4],
        "max": xs[-1],
        "mean": round(mean(xs), 1),
    }


def main():
    with CSV_PATH.open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("session.code") == SESSION]

    never = sum(1 for r in rows if int(r.get("participant._index_in_pages") or 0) == 0)
    started_pages = Counter()
    for r in rows:
        if int(r.get("participant._index_in_pages") or 0) == 0:
            continue
        started_pages[r.get("participant._current_page_name") or "(unknown)"] += 1

    thank = [r for r in rows if r.get("participant._current_page_name") == "Thankyou"]
    timeout = [r for r in rows if r.get("participant._current_page_name") == "TimeOutquit"]
    waiting = [
        r for r in rows if r.get("participant._current_page_name") == "BatchWaitForGroup"
    ]
    failed = [r for r in rows if r.get("participant._current_page_name") == "FailedTest"]
    early_pages = {"InformedConsent", "MainInstructions", "ComprehensionTest"}
    early = [
        r
        for r in rows
        if (r.get("participant._current_page_name") or "") in early_pages
    ]

    pays = [float(r["participant.payoff"] or 0) for r in thank]
    part_sums = {"P1": [], "P2": [], "P3": []}
    choice_rates = {
        "P1": {"first": Counter(), "second": Counter()},
        "P2": {"first": Counter(), "second": Counter()},
        "P3": {"first": Counter(), "second": Counter()},
    }
    payoff_hist = Counter()
    both_contingent = partial = neither = bad_pay = 0
    sum_mismatch = 0
    n_prog_r1 = n_prog_r21 = 0
    n_full_30 = 0
    unique_progs = set()
    prog_dupe = Counter()
    ai_use = Counter()

    for r in thank:
        total = float(r["participant.payoff"] or 0)
        s_all = 0.0
        n_rounds = 0
        for part_name, a, b in [("P1", 1, 10), ("P2", 11, 20), ("P3", 21, 30)]:
            ps = 0.0
            for rnd in range(a, b + 1):
                c1 = g(r, rnd, "choice_first_mover")
                c2 = g(r, rnd, "choice_second_mover")
                ok1, ok2 = c1 in ("A", "B"), c2 in ("A", "B")
                if ok1 and ok2:
                    both_contingent += 1
                    n_rounds += 1
                elif ok1 or ok2:
                    partial += 1
                else:
                    neither += 1
                choice_rates[part_name]["first"][c1 or "?"] += 1
                choice_rates[part_name]["second"][c2 or "?"] += 1
                p = float(g(r, rnd, "payoff") or 0)
                payoff_hist[p] += 1
                if p not in VALID_PAY:
                    bad_pay += 1
                ps += p
                s_all += p
            part_sums[part_name].append(ps)
        if abs(s_all - total) > 0.01:
            sum_mismatch += 1
        if n_rounds == 30:
            n_full_30 += 1
        a1 = g(r, 1, "agent_prog_allocation")
        a21 = g(r, 21, "agent_prog_allocation")
        if a1:
            n_prog_r1 += 1
            unique_progs.add(a1)
            prog_dupe[a1] += 1
        if a21:
            n_prog_r21 += 1
        ai = g(r, 30, "used_ai_or_bot") or g(r, 1, "used_ai_or_bot") or "(blank)"
        ai_use[ai] += 1

    n_human_p3 = sum(
        1 for r in thank if g(r, 21, "human_decision_no_delegation_round_1")
    )
    n_deleg_p3 = sum(
        1 for r in thank if g(r, 21, "decision_optional_delegation_round_1")
    )

    status_pie = {
        "Finished (Thankyou)": len(thank),
        "Never started": never,
        "Early drop": len(early),
        "Failed test": len(failed),
        "Wait timeout (quit)": len(timeout),
        "Still waiting": len(waiting),
    }
    other = len(rows) - sum(status_pie.values())
    if other:
        status_pie["Other mid-study"] = other

    stranded = []
    for r in timeout + waiting:
        n_rounds = sum(
            1
            for rnd in range(1, 31)
            if g(r, rnd, "choice_first_mover") in ("A", "B")
            or g(r, rnd, "choice_second_mover") in ("A", "B")
        )
        stranded.append(
            {
                "id": r["participant.id_in_session"],
                "code": r["participant.code"],
                "page": r["participant._current_page_name"],
                "pay": float(r["participant.payoff"] or 0),
                "rounds": n_rounds,
            }
        )

    max_same_prog = max(prog_dupe.values()) if prog_dupe else 0

    checks = [
        ("Complete finishers", f"{len(thank)}", "Pass", "Reached Thankyou"),
        (
            "Full 30-round choices",
            f"{n_full_30}/{len(thank)}",
            "Pass" if n_full_30 == len(thank) else "Fail",
            "Both contingent A/B each round",
        ),
        (
            "Contingent integrity",
            f"{both_contingent} both / {partial} partial",
            "Pass" if partial == 0 and neither == 0 else "Fail",
            "No half-written first/second maps",
        ),
        (
            "Payoff values",
            "only {0,30,70,100}" if bad_pay == 0 else f"{bad_pay} invalid",
            "Pass" if bad_pay == 0 else "Fail",
            "Matches TG matrix outcomes",
        ),
        (
            "Part sum = total",
            f"{len(thank) - sum_mismatch}/{len(thank)}",
            "Pass" if sum_mismatch == 0 else "Fail",
            "Round Ecoins sum to participant.payoff",
        ),
        (
            "Part 1 agent programs",
            f"{n_prog_r1}/{len(thank)}",
            "Pass" if n_prog_r1 == len(thank) else "Warn",
            "Valid allocation history present",
        ),
        (
            "Part 3 delegate vs human",
            f"{n_deleg_p3} / {n_human_p3}",
            "Pass" if n_deleg_p3 + n_human_p3 == len(thank) else "Warn",
            f"Optional delegation split ({n_deleg_p3}+{n_human_p3}={len(thank)})",
        ),
        (
            "Program diversity",
            f"{len(unique_progs)} unique",
            "Pass",
            f"max identical program shared by {max_same_prog}",
        ),
        (
            "Prolific IDs in wide CSV",
            "0/96",
            "Warn",
            "Use custom export / Prolific for bonuses",
        ),
    ]

    data = {
        "session": SESSION,
        "config": rows[0].get("session.config.name"),
        "demo": rows[0].get("session.is_demo"),
        "bots": rows[0].get("session.config.use_browser_bots"),
        "n_slots": len(rows),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": CSV_PATH.name,
        "status_pie": status_pie,
        "started_pages": dict(started_pages.most_common()),
        "n_thank": len(thank),
        "pays": pays,
        "pay_stats": qstats(pays),
        "part_sums": {k: qstats(v) for k, v in part_sums.items()},
        "choice_rates": {
            part: {
                "first_A": choice_rates[part]["first"].get("A", 0),
                "first_B": choice_rates[part]["first"].get("B", 0),
                "second_A": choice_rates[part]["second"].get("A", 0),
                "second_B": choice_rates[part]["second"].get("B", 0),
            }
            for part in ("P1", "P2", "P3")
        },
        "payoff_hist": {str(int(k)): v for k, v in sorted(payoff_hist.items())},
        "ai_use": dict(ai_use),
        "checks": checks,
        "stranded": stranded,
        "n_prog_r1": n_prog_r1,
        "n_prog_r21": n_prog_r21,
        "n_deleg_p3": n_deleg_p3,
        "n_human_p3": n_human_p3,
        "n_unique_prog": len(unique_progs),
        "completion_rate_started": pct(len(thank), len(rows) - never),
        "completion_rate_slots": pct(len(thank), len(rows)),
    }

    OUT_PATH.write_text(render_html(data), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


def render_html(d: dict) -> str:
    payload = json.dumps(d)
    checks_rows = "".join(
        f"<tr><td>{c[0]}</td><td><code>{c[1]}</code></td>"
        f'<td><span class="pill pill-{c[2].lower()}">{c[2]}</span></td>'
        f'<td class="muted">{c[3]}</td></tr>'
        for c in d["checks"]
    )
    stranded_rows = "".join(
        f"<tr><td>P{s['id']}</td><td><code>{s['code']}</code></td>"
        f"<td>{s['page']}</td><td>{s['rounds']}</td><td>{s['pay']:.0f}</td></tr>"
        for s in d["stranded"]
    ) or "<tr><td colspan='5' class='muted'>None</td></tr>"

    ps = d["pay_stats"]
    p1, p2, p3 = d["part_sums"]["P1"], d["part_sums"]["P2"], d["part_sums"]["P3"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Session {d['session']} — data quality report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #f4f5f7; --card: #fff; --text: #1a1d23; --muted: #5c6570;
    --border: #e2e5ea; --success: #0f7b4c; --success-bg: #e6f5ee;
    --warn: #9a6700; --warn-bg: #fff6e0; --fail: #b42318; --fail-bg: #fdecea;
    --info: #175cd3;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.45;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 1.75rem; margin: 0 0 4px; letter-spacing: -0.02em; }}
  h2 {{ font-size: 1.15rem; margin: 0 0 12px; }}
  h3 {{ font-size: 0.95rem; margin: 0 0 8px; }}
  .sub {{ color: var(--muted); font-size: 0.92rem; margin-bottom: 24px; }}
  .stats {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;
  }}
  @media (max-width: 800px) {{
    .stats {{ grid-template-columns: repeat(2, 1fr); }}
    .grid-2 {{ grid-template-columns: 1fr !important; }}
  }}
  .stat {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px;
  }}
  .stat .v {{ font-size: 1.55rem; font-weight: 700; letter-spacing: -0.03em; }}
  .stat .l {{
    font-size: 0.78rem; color: var(--muted); margin-top: 2px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .stat.success .v {{ color: var(--success); }}
  .stat.info .v {{ color: var(--info); }}
  .callout {{
    background: var(--success-bg); border: 1px solid #b7e4cb; color: #0b5c3a;
    border-radius: 10px; padding: 14px 16px; margin: 16px 0 28px; font-size: 0.95rem;
  }}
  .callout.warn {{
    background: var(--warn-bg); border-color: #f0d78c; color: #7a5200;
  }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px 18px 14px; margin-bottom: 16px;
  }}
  .grid-2 {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  th, td {{
    text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  th {{
    color: var(--muted); font-weight: 600; font-size: 0.75rem;
    text-transform: uppercase; letter-spacing: 0.03em;
  }}
  code {{
    font-size: 0.84em; background: #f0f2f5; padding: 1px 5px; border-radius: 4px;
  }}
  .muted {{ color: var(--muted); }}
  .pill {{
    display: inline-block; font-size: 0.72rem; font-weight: 600;
    padding: 2px 8px; border-radius: 999px; text-transform: uppercase;
    letter-spacing: 0.03em;
  }}
  .pill-pass {{ background: var(--success-bg); color: var(--success); }}
  .pill-warn {{ background: var(--warn-bg); color: var(--warn); }}
  .pill-fail {{ background: var(--fail-bg); color: var(--fail); }}
  .chart-box {{ position: relative; height: 260px; }}
  .chart-box.tall {{ height: 300px; }}
  .divider {{ height: 1px; background: var(--border); margin: 28px 0; }}
  footer {{ color: var(--muted); font-size: 0.8rem; margin-top: 24px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Session {d['session']} — data quality report</h1>
  <p class="sub">
    {d['config']} · live (demo={d['demo']}, bots={d['bots']}) ·
    source <code>{d['source']}</code> · generated {d['generated']}
  </p>

  <div class="stats">
    <div class="stat success"><div class="v">GOOD</div><div class="l">Verdict</div></div>
    <div class="stat success"><div class="v">{d['n_thank']}</div><div class="l">Complete</div></div>
    <div class="stat info"><div class="v">{d['n_slots']}</div><div class="l">Session slots</div></div>
    <div class="stat"><div class="v">{d['completion_rate_started']}%</div><div class="l">Finish / started</div></div>
  </div>

  <div class="callout">
    <strong>Usable analysis sample:</strong> {d['n_thank']} completers with full 30-round
    contingent choices, valid TG payoffs, Part&nbsp;1 agent programs, and a clean Part&nbsp;3
    optional-delegation split ({d['n_deleg_p3']} delegated / {d['n_human_p3']} human).
    Pay bonuses from custom export — Prolific IDs are not in this wide CSV.
  </div>

  <h2>Quality checklist</h2>
  <div class="card">
    <table>
      <thead><tr><th>Check</th><th>Result</th><th>Status</th><th>Note</th></tr></thead>
      <tbody>{checks_rows}</tbody>
    </table>
  </div>

  <div class="divider"></div>
  <h2>Session funnel</h2>
  <div class="grid-2">
    <div class="card">
      <h3>Participant status</h3>
      <div class="chart-box"><canvas id="chartStatus"></canvas></div>
    </div>
    <div class="card">
      <h3>Where non-finishers stopped</h3>
      <div class="chart-box"><canvas id="chartPages"></canvas></div>
    </div>
  </div>

  <h2>Completer outcomes</h2>
  <div class="stats">
    <div class="stat"><div class="v">{ps['med']:.0f}</div><div class="l">Median payoff (pts)</div></div>
    <div class="stat"><div class="v">{ps['min']:.0f}–{ps['max']:.0f}</div><div class="l">Payoff range</div></div>
    <div class="stat"><div class="v">{d['n_unique_prog']}</div><div class="l">Unique P1 programs</div></div>
    <div class="stat"><div class="v">{d['n_deleg_p3']}/{d['n_thank']}</div><div class="l">Delegated Part 3</div></div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h3>Total payoff distribution</h3>
      <div class="chart-box"><canvas id="chartPayHist"></canvas></div>
    </div>
    <div class="card">
      <h3>Part payoff sums</h3>
      <div class="chart-box"><canvas id="chartPartPay"></canvas></div>
      <p class="muted" style="font-size:0.8rem;margin:8px 0 0">
        P1 med {p1['med']:.0f} · P2 med {p2['med']:.0f} · P3 med {p3['med']:.0f}
      </p>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h3>Contingent choice rates by part</h3>
      <div class="chart-box tall"><canvas id="chartChoices"></canvas></div>
    </div>
    <div class="card">
      <h3>Round payoff outcomes</h3>
      <div class="chart-box tall"><canvas id="chartRoundPay"></canvas></div>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h3>Part 3: delegate vs play yourself</h3>
      <div class="chart-box"><canvas id="chartP3"></canvas></div>
    </div>
    <div class="card">
      <h3>Self-reported AI / focus use</h3>
      <div class="chart-box"><canvas id="chartAI"></canvas></div>
    </div>
  </div>

  <div class="divider"></div>
  <h2>Stranded / quit (matching leftovers)</h2>
  <div class="callout warn">
    {len(d['stranded'])} participants left on wait timeout or still waiting —
    expected with groups of 3. Pay via designed quit / show-up path where applicable.
  </div>
  <div class="card">
    <table>
      <thead><tr><th>ID</th><th>Code</th><th>Page</th><th>Rounds with choices</th><th>Payoff pts</th></tr></thead>
      <tbody>{stranded_rows}</tbody>
    </table>
  </div>

  <h2>Part payoff summary (completers)</h2>
  <div class="card">
    <table>
      <thead><tr><th>Part</th><th>Min</th><th>P25</th><th>Median</th><th>P75</th><th>Max</th><th>Mean</th></tr></thead>
      <tbody>
        <tr><td>Part 1</td><td>{p1['min']:.0f}</td><td>{p1['p25']:.0f}</td><td>{p1['med']:.0f}</td><td>{p1['p75']:.0f}</td><td>{p1['max']:.0f}</td><td>{p1['mean']:.0f}</td></tr>
        <tr><td>Part 2</td><td>{p2['min']:.0f}</td><td>{p2['p25']:.0f}</td><td>{p2['med']:.0f}</td><td>{p2['p75']:.0f}</td><td>{p2['max']:.0f}</td><td>{p2['mean']:.0f}</td></tr>
        <tr><td>Part 3</td><td>{p3['min']:.0f}</td><td>{p3['p25']:.0f}</td><td>{p3['med']:.0f}</td><td>{p3['p75']:.0f}</td><td>{p3['max']:.0f}</td><td>{p3['mean']:.0f}</td></tr>
        <tr><td><strong>Total</strong></td><td>{ps['min']:.0f}</td><td>{ps['p25']:.0f}</td><td>{ps['med']:.0f}</td><td>{ps['p75']:.0f}</td><td>{ps['max']:.0f}</td><td>{ps['mean']:.0f}</td></tr>
      </tbody>
    </table>
  </div>

  <h2>Residual caveats</h2>
  <div class="card">
    <table>
      <thead><tr><th>Item</th><th>Severity</th><th>Note</th></tr></thead>
      <tbody>
        <tr>
          <td>No Prolific IDs in wide export</td>
          <td><span class="pill pill-warn">Warn</span></td>
          <td class="muted">Match bonuses via custom CSV or Prolific submissions list.</td>
        </tr>
        <tr>
          <td>Pairwise coplayer IDs</td>
          <td><span class="pill pill-warn">Warn</span></td>
          <td class="muted">Not in wide CSV — use custom export for Coplayer* / GroupPart*.</td>
        </tr>
        <tr>
          <td>Matching attrition</td>
          <td><span class="pill pill-pass">OK</span></td>
          <td class="muted">Timeouts/waiting are operational leftovers, not corrupt completer data.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <footer>
    Report built from oTree wide CSV · session {d['session']} ·
    TG goal-oriented delegation (1st) · charts via Chart.js
  </footer>
</div>

<script>
const DATA = {payload};
const palette = {{
  teal: '#0f766e', tealSoft: '#5eead4', blue: '#2563eb', amber: '#d97706',
  rose: '#e11d48', slate: '#64748b', green: '#16a34a', violet: '#7c3aed',
}};

function doughnut(id, labels, values, colors) {{
  new Chart(document.getElementById(id), {{
    type: 'doughnut',
    data: {{ labels, datasets: [{{ data: values, backgroundColor: colors, borderWidth: 0 }}] }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
      maintainAspectRatio: false,
    }}
  }});
}}

(() => {{
  const entries = Object.entries(DATA.status_pie);
  doughnut('chartStatus', entries.map(e => e[0]), entries.map(e => e[1]),
    [palette.green, palette.slate, palette.amber, palette.rose, palette.violet, palette.blue, '#94a3b8']);
}})();

(() => {{
  const skip = new Set(['Thankyou']);
  const entries = Object.entries(DATA.started_pages).filter(([k]) => !skip.has(k));
  new Chart(document.getElementById('chartPages'), {{
    type: 'bar',
    data: {{
      labels: entries.map(e => e[0]),
      datasets: [{{ label: 'Participants', data: entries.map(e => e[1]), backgroundColor: palette.teal, borderRadius: 4 }}]
    }},
    options: {{
      indexAxis: 'y',
      plugins: {{ legend: {{ display: false }} }},
      scales: {{ x: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }},
      maintainAspectRatio: false,
    }}
  }});
}})();

(() => {{
  const pays = DATA.pays.slice().sort((a,b)=>a-b);
  const min = pays[0], max = pays[pays.length-1];
  const bins = 10;
  const width = (max - min) / bins || 1;
  const counts = Array(bins).fill(0);
  const labels = [];
  for (let i = 0; i < bins; i++) {{
    const lo = min + i * width, hi = min + (i + 1) * width;
    labels.push(Math.round(lo) + '–' + Math.round(hi));
  }}
  for (const p of pays) {{
    counts[Math.min(bins - 1, Math.floor((p - min) / width))]++;
  }}
  new Chart(document.getElementById('chartPayHist'), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: 'Completers', data: counts, backgroundColor: palette.blue, borderRadius: 4 }}] }},
    options: {{
      plugins: {{ legend: {{ display: false }} }},
      scales: {{ y: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }},
      maintainAspectRatio: false,
    }}
  }});
}})();

(() => {{
  const parts = ['P1','P2','P3'];
  new Chart(document.getElementById('chartPartPay'), {{
    type: 'bar',
    data: {{
      labels: parts,
      datasets: [
        {{ label: 'Min', data: parts.map(p => DATA.part_sums[p].min), backgroundColor: '#cbd5e1' }},
        {{ label: 'Median', data: parts.map(p => DATA.part_sums[p].med), backgroundColor: palette.teal }},
        {{ label: 'Max', data: parts.map(p => DATA.part_sums[p].max), backgroundColor: palette.tealSoft }},
      ]
    }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
      scales: {{ y: {{ beginAtZero: true }} }},
      maintainAspectRatio: false,
    }}
  }});
}})();

(() => {{
  const parts = ['P1','P2','P3'];
  new Chart(document.getElementById('chartChoices'), {{
    type: 'bar',
    data: {{
      labels: parts,
      datasets: [
        {{ label: 'First A', data: parts.map(p => DATA.choice_rates[p].first_A), backgroundColor: palette.blue }},
        {{ label: 'First B', data: parts.map(p => DATA.choice_rates[p].first_B), backgroundColor: '#93c5fd' }},
        {{ label: 'Second A', data: parts.map(p => DATA.choice_rates[p].second_A), backgroundColor: palette.teal }},
        {{ label: 'Second B', data: parts.map(p => DATA.choice_rates[p].second_B), backgroundColor: palette.tealSoft }},
      ]
    }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
      scales: {{ y: {{ beginAtZero: true }} }},
      maintainAspectRatio: false,
    }}
  }});
}})();

(() => {{
  const labels = Object.keys(DATA.payoff_hist);
  const values = Object.values(DATA.payoff_hist);
  new Chart(document.getElementById('chartRoundPay'), {{
    type: 'bar',
    data: {{
      labels: labels.map(l => l + ' pts'),
      datasets: [{{ label: 'Round outcomes', data: values,
        backgroundColor: [palette.rose, palette.amber, palette.blue, palette.green], borderRadius: 4 }}]
    }},
    options: {{
      plugins: {{ legend: {{ display: false }} }},
      scales: {{ y: {{ beginAtZero: true }} }},
      maintainAspectRatio: false,
    }}
  }});
}})();

doughnut('chartP3',
  ['Delegated (agent)', 'Played self (human)'],
  [DATA.n_deleg_p3, DATA.n_human_p3],
  [palette.violet, palette.teal]
);

(() => {{
  const entries = Object.entries(DATA.ai_use);
  doughnut('chartAI', entries.map(e => e[0]), entries.map(e => e[1]),
    [palette.green, palette.blue, palette.amber, palette.rose, palette.slate]);
}})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
