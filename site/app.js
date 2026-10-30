(() => {
  "use strict";

  const $app = document.getElementById("app");
  const AXIS_FIELD = {
    "지역": (d) => d.regions.concat(d.crossborder ? ["크로스보더"] : []),
    "규모 구간": (d) => [d.size],
    "유형": (d) => d.types,
    "업종": (d) => d.sectors,
    "테마": (d) => d.themes,
    "상태": (d) => [d.status],
  };
  const ROLES = ["인수자", "대상", "매도자", "재무 자문", "법률 자문"];
  let DATA = null;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const enc = encodeURIComponent;
  const todayKST = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  const fmtDate = (s) => (s ? s.slice(5).replace("-", ".") : "");

  // ---------------------------------------------------------------- 라우팅
  function parseHash() {
    const h = decodeURIComponent(location.hash.replace(/^#/, "")) || "/";
    const [path, query = ""] = h.split("?");
    return { parts: path.split("/").filter(Boolean), params: new URLSearchParams(query) };
  }

  function setNav(key) {
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === key));
  }

  function route() {
    if (!DATA) return;
    const { parts, params } = parseHash();
    window.scrollTo(0, 0);
    if (parts[0] === "deal" && parts[1]) return viewDeal(parts.slice(1).join("/"));
    if (parts[0] === "entity" && parts[1]) return viewEntity(parts.slice(1).join("/"));
    if (parts[0] === "entities") return viewEntities();
    if (parts[0] === "briefings") return viewBriefings();
    if (parts[0] === "briefing" && parts[1]) return viewBriefing(parts[1]);
    return viewHome(params);
  }

  // ---------------------------------------------------------------- 필터
  function readFilters(params) {
    const f = {};
    for (const axis of Object.keys(AXIS_FIELD)) {
      const v = params.get(axis);
      f[axis] = new Set(v ? v.split("|") : []);
    }
    return { f, q: (params.get("q") || "").trim() };
  }

  function filterHash(f, q) {
    const p = [];
    for (const [axis, set] of Object.entries(f)) if (set.size) p.push(`${enc(axis)}=${enc([...set].join("|"))}`);
    if (q) p.push(`q=${enc(q)}`);
    return "#/" + (p.length ? "?" + p.join("&") : "");
  }

  function textOf(d) {
    const names = ROLES.flatMap((r) => d.names[r] || []);
    const aliases = names.flatMap((n) => (DATA.entities[n]?.aliases || []));
    return [d.title, d.summary, ...names, ...aliases].join(" ").toLowerCase();
  }

  // 같은 축 안에서는 OR, 축끼리는 AND
  function matches(d, f, q, skipAxis) {
    for (const [axis, set] of Object.entries(f)) {
      if (axis === skipAxis || !set.size) continue;
      const vals = AXIS_FIELD[axis](d);
      if (![...set].some((v) => vals.includes(v))) return false;
    }
    if (q && !q.toLowerCase().split(/\s+/).every((w) => textOf(d).includes(w))) return false;
    return true;
  }

  // ---------------------------------------------------------------- 홈
  function viewHome(params) {
    setNav("home");
    const { f, q } = readFilters(params);
    const hasFilter = q || Object.values(f).some((s) => s.size);
    const latest = DATA.briefings[0];
    const isToday = latest && latest.date === todayKST();

    let html = "";
    if (!hasFilter) {
      html += `<section class="brief">
        <div class="kicker"><span>${isToday ? "오늘의 브리핑" : "최근 브리핑"}</span>
        <span class="aside">${latest ? esc(latest.date) : ""}</span></div>
        ${latest ? `<div class="prose">${latest.html}</div>` : `<p class="muted">아직 브리핑이 없습니다.</p>`}
      </section>`;
    }

    const shown = DATA.deals.filter((d) => matches(d, f, q));
    html += `<div class="kicker"><span>딜 아카이브</span><span class="aside">전체 ${DATA.deals.length}건 · 최근 업데이트순</span></div>`;
    html += `<div class="filters">
      <input class="search" id="q" type="search" placeholder="회사, PE, 자문사, 키워드 검색" value="${esc(q)}" aria-label="검색">
      <details class="axes"${hasFilter || window.innerWidth > 720 ? " open" : ""}>
        <summary>태그로 찾기${activeCount(f) ? ` · ${activeCount(f)}개 선택` : ""}</summary>
        ${Object.keys(AXIS_FIELD).map((axis) => axisRow(axis, f, q)).join("")}
        <div class="hint">같은 줄에서 여러 개를 고르면 '또는', 다른 줄끼리는 '그리고'로 찾습니다.</div>
      </details>
    </div>
    <div class="filter-bar"><span>${shown.length}건</span>${hasFilter ? `<button class="linkbtn" id="reset">필터 초기화</button>` : ""}</div>
    ${dealTable(shown)}`;
    $app.innerHTML = html;

    $app.querySelectorAll(".chip").forEach((el) => el.addEventListener("click", () => {
      const axis = el.dataset.axis, v = el.dataset.v;
      f[axis].has(v) ? f[axis].delete(v) : f[axis].add(v);
      location.hash = filterHash(f, q);
    }));
    const qEl = document.getElementById("q");
    let t;
    qEl.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(() => { history.replaceState(null, "", filterHash(f, qEl.value.trim())); rerenderList(f, qEl.value.trim()); }, 180);
    });
    const r = document.getElementById("reset");
    if (r) r.addEventListener("click", () => (location.hash = "#/"));
  }

  function activeCount(f) { return Object.values(f).reduce((n, s) => n + s.size, 0); }

  function rerenderList(f, q) {
    const shown = DATA.deals.filter((d) => matches(d, f, q));
    $app.querySelector(".filter-bar span").textContent = `${shown.length}건`;
    const old = $app.querySelector(".deals, .empty");
    old.outerHTML = dealTable(shown);
  }

  function axisRow(axis, f, q) {
    let values = DATA.axes[axis].slice();
    if (axis === "지역") values.push("크로스보더");
    const chips = values.map((v) => {
      const n = DATA.deals.filter((d) => matches(d, f, q, axis) && AXIS_FIELD[axis](d).includes(v)).length;
      const on = f[axis].has(v);
      return `<button class="chip${on ? " on" : ""}${!n && !on ? " zero" : ""}" data-axis="${esc(axis)}" data-v="${esc(v)}" aria-pressed="${on}">${esc(v)}<span class="n">${n}</span></button>`;
    }).join("");
    return `<div class="axis"><div class="axis-name">${esc(axis.replace(" 구간", ""))}</div><div class="chips">${chips}</div></div>`;
  }

  function statusCls(s) { return s === "거래 완료" ? "done" : s === "무산" ? "fail" : ""; }

  function dealTable(list) {
    if (!list.length) return `<div class="empty">${DATA.deals.length ? "조건에 맞는 딜이 없습니다." : "아직 쌓인 딜이 없습니다."}</div>`;
    const rows = list.map((d) => `<tr>
      <td class="d-date">${fmtDate(d.is_updated ? d.updated : d.announced)}</td>
      <td class="d-title"><a href="#/deal/${enc(d.id)}">${esc(d.title)}</a>${d.is_updated ? `<span class="badge up">업데이트</span>` : ""}
        ${d.summary ? `<div class="d-sum">${esc(d.summary)}</div>` : ""}</td>
      <td class="d-size">${esc(d.size_krw && d.size_krw !== "비공개" ? d.size_krw : d.size)}</td>
      <td class="d-meta">${esc(d.regions.join("·"))}</td>
      <td class="d-statuscell"><span class="status ${statusCls(d.status)}">${esc(d.status)}</span><div class="conf">${esc(d.confidence)}</div></td>
    </tr>`).join("");
    return `<table class="deals"><thead><tr><th>날짜</th><th>딜</th><th>규모</th><th>지역</th><th>상태</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ---------------------------------------------------------------- 딜 상세
  function entLink(n) { return `<a class="ent" href="#/entity/${enc(n)}">${esc(n)}</a>`; }
  function tagLink(axis, v) { return `<a href="#/?${enc(axis)}=${enc(v)}">${esc(v)}</a>`; }

  function viewDeal(id) {
    setNav("home");
    const d = DATA.deals.find((x) => x.id === id);
    if (!d) { $app.innerHTML = `<p class="pad muted">딜을 찾을 수 없습니다. <a href="#/">목록으로</a></p>`; return; }
    document.title = `${d.title} · Deal Archive`;
    const tags = [
      ...d.regions.map((v) => tagLink("지역", v)),
      ...(d.crossborder ? [tagLink("지역", "크로스보더")] : []),
      tagLink("규모 구간", d.size),
      ...d.types.map((v) => tagLink("유형", v)),
      ...d.sectors.map((v) => tagLink("업종", v)),
      ...d.themes.map((v) => tagLink("테마", v)),
    ].join("");
    const fact = (k, v) => (v ? `<div><dt>${k}</dt><dd>${v}</dd></div>` : "");
    const names = (r) => (d.names[r] || []).map(entLink).join(", ");
    const sources = d.sources.length ? `<div class="sources"><div class="kicker"><span>출처</span></div><ol>${d.sources.map((s) => `<li><a href="${esc(s)}" target="_blank" rel="noopener">${esc(s.replace(/^https?:\/\//, "").slice(0, 80))}</a></li>`).join("")}</ol></div>` : "";

    $app.innerHTML = `<div class="crumb"><a href="#/">← 딜 아카이브</a></div>
      <header class="deal-head">
        <h1>${esc(d.title)}</h1>
        <div class="deal-sub"><span class="status ${statusCls(d.status)}">${esc(d.status)}</span>
          <span>${esc(d.confidence)}</span><span>발표 ${esc(d.announced)}</span>
          ${d.is_updated ? `<span>업데이트 ${esc(d.updated)}<span class="badge up">업데이트</span></span>` : ""}</div>
        <div class="taglist">${tags}</div>
      </header>
      <div class="layout">
        <article class="prose">${d.html}</article>
        <aside class="facts"><dl>
          ${fact("규모", `<span class="big">${esc(d.size_krw || d.size)}</span>${d.size_orig ? `<div class="muted">${esc(d.size_orig)}</div>` : ""}`)}
          ${ROLES.map((r) => fact(r, names(r))).join("")}
        </dl>${sources}</aside>
      </div>`;
  }

  // ---------------------------------------------------------------- 회사·기관
  function dealsOf(name) {
    return DATA.deals.map((d) => ({ d, roles: ROLES.filter((r) => (d.names[r] || []).includes(name)) }))
      .filter((x) => x.roles.length || x.d.html.includes(`#/entity/${esc(name)}"`));
  }

  function viewEntity(name) {
    setNav("entities");
    const e = DATA.entities[name] || {};
    const rows = dealsOf(name);
    document.title = `${name} · Deal Archive`;
    const meta = [e.type, e.country].filter(Boolean).map(esc).join(" · ");
    const list = rows.length ? `<table class="deals"><thead><tr><th>날짜</th><th>딜</th><th>역할</th><th>규모</th><th>상태</th></tr></thead><tbody>${
      rows.map(({ d, roles }) => `<tr><td class="d-date">${fmtDate(d.updated)}</td>
        <td class="d-title"><a href="#/deal/${enc(d.id)}">${esc(d.title)}</a></td>
        <td class="d-meta">${esc(roles.join(", ") || "언급")}</td>
        <td class="d-size">${esc(d.size_krw || d.size)}</td>
        <td class="d-statuscell"><span class="status ${statusCls(d.status)}">${esc(d.status)}</span></td></tr>`).join("")
    }</tbody></table>` : `<div class="empty">관련 딜이 없습니다.</div>`;
    $app.innerHTML = `<div class="crumb"><a href="#/entities">← 회사 · 기관</a></div>
      <header class="ent-head"><h1>${esc(name)}</h1>
        <div class="deal-sub">${meta}${e.aliases?.length ? ` <span class="muted">· 다른 표기: ${esc(e.aliases.join(", "))}</span>` : ""}</div></header>
      <div class="kicker"><span>관련 딜</span><span class="aside">${rows.length}건</span></div>${list}`;
  }

  function viewEntities() {
    setNav("entities");
    document.title = "회사 · 기관 · Deal Archive";
    const groups = {};
    for (const [name, e] of Object.entries(DATA.entities)) {
      const n = dealsOf(name).length;
      (groups[e.type || "기타"] ||= []).push({ name, n });
    }
    const order = ["PE·VC", "재무 자문사", "법률 자문사", "기업", "정부·기관", "기타"];
    const html = order.filter((t) => groups[t]).map((t) => {
      const items = groups[t].sort((a, b) => b.n - a.n || a.name.localeCompare(b.name, "ko"));
      return `<div class="ent-group"><div class="kicker"><span>${esc(t)}</span><span class="aside">${items.length}</span></div>
        <ul>${items.map((x) => `<li><a href="#/entity/${enc(x.name)}">${esc(x.name)}</a><span>${x.n}건</span></li>`).join("")}</ul></div>`;
    }).join("");
    $app.innerHTML = html ? `<div class="ent-groups">${html}</div>` : `<p class="pad muted">아직 등록된 이름이 없습니다.</p>`;
  }

  // ---------------------------------------------------------------- 브리핑
  function viewBriefings() {
    setNav("briefings");
    document.title = "지난 브리핑 · Deal Archive";
    $app.innerHTML = `<div class="kicker"><span>지난 브리핑</span><span class="aside">${DATA.briefings.length}건</span></div>
      <ul class="blist">${DATA.briefings.map((b) => `<li><a class="bd" href="#/briefing/${enc(b.date)}">${esc(b.date)}</a>
        <a class="ba" href="#/briefing/${enc(b.date)}">${esc(b.alert || "")}</a></li>`).join("") || `<li class="muted">없음</li>`}</ul>`;
  }

  function viewBriefing(date) {
    setNav("briefings");
    const b = DATA.briefings.find((x) => x.date === date);
    if (!b) { $app.innerHTML = `<p class="pad muted">브리핑을 찾을 수 없습니다.</p>`; return; }
    document.title = `${date} 브리핑 · Deal Archive`;
    $app.innerHTML = `<div class="crumb"><a href="#/briefings">← 지난 브리핑</a></div>
      <h1 class="brief-head">${esc(date)} 브리핑</h1><div class="prose">${b.html}</div>`;
  }

  // ---------------------------------------------------------------- 시작
  const d = new Date(Date.now() + 9 * 3600e3);
  document.getElementById("today").textContent =
    `${d.getUTCFullYear()}년 ${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 ${"일월화수목금토"[d.getUTCDay()]}요일`;

  fetch("data.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((data) => {
      DATA = data;
      document.getElementById("built").textContent = `업데이트 ${data.built_at}`;
      route();
    })
    .catch(() => { $app.innerHTML = `<p class="pad muted">데이터를 불러오지 못했습니다.</p>`; });

  window.addEventListener("hashchange", () => { document.title = "Deal Archive"; route(); });
})();
