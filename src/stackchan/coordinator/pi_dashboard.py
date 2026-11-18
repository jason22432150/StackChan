"""個人版 Pi Coordinator 簡易管理頁（唯讀、不含 Prompt／Token）。"""

from __future__ import annotations

import html
from typing import Any


def summarize_event_row(row: dict[str, Any]) -> dict[str, Any]:
    """只保留管理頁需要的欄位；絕不輸出 payload／訊息本文。"""
    return {
        "event_id": str(row.get("event_id", "")),
        "bridge_id": str(row.get("bridge_id", "")),
        "epoch": str(row.get("epoch", "")),
        "bridge_sequence": int(row.get("bridge_sequence") or 0),
        "event_type": str(row.get("event_type", "")),
        "evidence_level": str(row.get("evidence_level", "")),
        "privacy_class": str(row.get("privacy_class", "")),
        "observed_at": str(row.get("observed_at", "")),
        "ingested_at": str(row.get("ingested_at", "")),
    }


def render_dashboard_html(*, service: str = "stackchan-pi-coordinator") -> str:
    """回傳自含 CSS／JS 的簡易管理頁；Token 只留在瀏覽器記憶體，不寫入 HTML。"""
    title = html.escape(service)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="robots" content="noindex,nofollow"/>
  <title>{title} dashboard</title>
  <style>
    :root {{
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e7ecf1;
      --muted: #8b9aab;
      --accent: #3d9cfd;
      --line: #2a3542;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "IBM Plex Sans", "Noto Sans TC", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1c2a3a, var(--bg));
      color: var(--text); min-height: 100vh;
    }}
    main {{ max-width: 960px; margin: 0 auto; padding: 2rem 1.25rem 3rem; }}
    h1 {{ font-size: 1.6rem; letter-spacing: 0.02em; margin: 0 0 0.35rem; }}
    p.lead {{ color: var(--muted); margin: 0 0 1.5rem; }}
    .panel {{
      background: color-mix(in srgb, var(--panel) 92%, black);
      border: 1px solid var(--line); border-radius: 12px; padding: 1rem;
      margin-bottom: 1rem;
    }}
    label {{ display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.35rem; }}
    input, button {{
      font: inherit; border-radius: 8px; border: 1px solid var(--line);
      padding: 0.55rem 0.75rem;
    }}
    input {{
      width: 100%; background: #0c1117; color: var(--text); margin-bottom: 0.75rem;
    }}
    button {{
      background: var(--accent); color: #041018; border: 0; font-weight: 600; cursor: pointer;
    }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .row {{ display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }}
    .status {{ color: var(--muted); font-size: 0.9rem; min-height: 1.2rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
    th, td {{
      text-align: left; padding: 0.55rem 0.4rem; border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .mono {{ font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.82rem; }}
    .badge {{
      display: inline-block; padding: 0.1rem 0.45rem; border-radius: 999px;
      background: #243041; color: #c9d7e6; font-size: 0.75rem;
    }}
    .warn {{ color: #ffb4a2; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p class="lead">個人版唯讀管理頁。僅顯示事件摘要；不包含 Prompt、Token 或密鑰。</p>
    <section class="panel">
      <label for="token">Bridge Bearer Token（只存在此分頁記憶體）</label>
      <input id="token" type="password" autocomplete="off" spellcheck="false"
             placeholder="貼上與 Pi 相同的 STACKCHAN_BRIDGE_TOKEN"/>
      <div class="row">
        <button id="load" type="button">重新整理事件</button>
        <span id="status" class="status"></span>
      </div>
      <p class="status warn">此頁僅供信任的家庭 LAN；請勿對公網開放。</p>
    </section>
    <section class="panel">
      <table>
        <thead>
          <tr>
            <th>observed</th>
            <th>type</th>
            <th>evidence</th>
            <th>seq</th>
            <th>event_id</th>
          </tr>
        </thead>
        <tbody id="rows">
          <tr><td colspan="5" class="status">尚未載入</td></tr>
        </tbody>
      </table>
    </section>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const rowsEl = document.getElementById("rows");
    const tokenEl = document.getElementById("token");
    const loadBtn = document.getElementById("load");

    function setStatus(text, isError) {{
      statusEl.textContent = text || "";
      statusEl.className = isError ? "status warn" : "status";
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    async function refresh() {{
      const token = tokenEl.value.trim();
      if (!token) {{
        setStatus("請先輸入 Token", true);
        return;
      }}
      loadBtn.disabled = true;
      setStatus("載入中…");
      try {{
        const resp = await fetch("/v1/events?limit=50", {{
          headers: {{
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
          }},
        }});
        const body = await resp.json();
        if (!resp.ok) {{
          const msg = (body && body.error && body.error.message) || ("HTTP " + resp.status);
          throw new Error(msg);
        }}
        const events = body.items || [];
        if (!events.length) {{
          rowsEl.innerHTML = '<tr><td colspan="5" class="status">尚無事件</td></tr>';
        }} else {{
          rowsEl.innerHTML = events.map((ev) => {{
            return "<tr>"
              + "<td class=\\"mono\\">" + escapeHtml(ev.observed_at || "") + "</td>"
              + "<td><span class=\\"badge\\">" + escapeHtml(ev.event_type || "") + "</span></td>"
              + "<td>" + escapeHtml(ev.evidence_level || "") + "</td>"
              + "<td class=\\"mono\\">" + escapeHtml(String(ev.bridge_sequence ?? "")) + "</td>"
              + "<td class=\\"mono\\">" + escapeHtml(ev.event_id || "") + "</td>"
              + "</tr>";
          }}).join("");
        }}
        setStatus("已載入 " + events.length + " 筆");
      }} catch (err) {{
        setStatus(String(err.message || err), true);
      }} finally {{
        loadBtn.disabled = false;
      }}
    }}

    loadBtn.addEventListener("click", refresh);
    tokenEl.addEventListener("keydown", (ev) => {{
      if (ev.key === "Enter") refresh();
    }});
  </script>
</body>
</html>
"""
