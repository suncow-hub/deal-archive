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
  let MKT = { items: [], fx: {} };
  // 시세 설정 (market/settings.yml → docs/market/settings.json). 못 불러오면 이 기본값
  let CFG = {
    strip: ["KOSPI", "KOSDAQ", "USDKRW"], indices: ["KOSPI", "KOSDAQ"], stocks: [], exclude: [], auto: {},
    tape: [["FOREXCOM:SPXUSD", "S&P 500"], ["FOREXCOM:NSXUSD", "나스닥 100"], ["FOREXCOM:DJI", "다우"], ["FX_IDC:USDKRW", "원/달러"],
      ["FRED:DGS10", "미 10년물"], ["TVC:USOIL", "WTI"], ["TVC:GOLD", "금"]].map(([symbol, title]) => ({ symbol, title })),
    catalog: { indices: { KOSPI: "코스피", KOSDAQ: "코스닥" }, fx: { USDKRW: "원/달러" } },
  };
  // 편집 버튼은 주인 표시(이 브라우저에 한 번 #/?edit=1 로 켬)가 있을 때만 보인다.
  // 진짜 잠금은 GitHub 쪽: 설정 이슈는 리포 주인이 올린 것만 적용된다.
  const OWNER_KEY = "da_owner";
  const isOwner = () => { try { return localStorage.getItem(OWNER_KEY) === "1"; } catch { return false; } };
  const setOwner = (on) => { try { on ? localStorage.setItem(OWNER_KEY, "1") : localStorage.removeItem(OWNER_KEY); } catch { /* 저장 불가 */ } };
  const REPO = "https://github.com/suncow-hub/deal-archive";

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const enc = encodeURIComponent;
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? String(u) : "#");
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
    hideTip();
    $app.onclick = null; $app.oninput = null; $app.onchange = null;
    if (params.get("edit") === "1") setOwner(true);
    if (params.get("edit") === "0") setOwner(false);
    if (parts[0] === "deal" && parts[1]) return viewDeal(parts.slice(1).join("/"));
    if (parts[0] === "entity" && parts[1]) return viewEntity(parts.slice(1).join("/"));
    if (parts[0] === "entities") return viewEntities();
    if (parts[0] === "rumors") return viewRumors(params);
    if (parts[0] === "chart") return viewChart(params);
    if (parts[0] === "settings") return viewSettings(params);
    if (parts[0] === "glossary") return viewGlossary(params);
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
    if (!hasFilter) html += marketStrip();
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
    const tt = document.getElementById("tt");
    if (tt) tickerTape(tt);
    $app.querySelectorAll(".brief .prose").forEach(annotate);
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
    const sources = d.sources.length ? `<div class="sources"><div class="kicker"><span>출처</span></div><ol>${d.sources.map((s) => `<li><a href="${esc(safeUrl(s))}" target="_blank" rel="noopener">${esc(s.replace(/^https?:\/\//, "").slice(0, 80))}</a></li>`).join("")}</ol></div>` : "";

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
    annotate($app.querySelector("article.prose"));
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
        <div class="deal-sub">${meta}${e.aliases?.length ? ` <span class="muted">· 다른 표기: ${esc(e.aliases.join(", "))}</span>` : ""}
          ${e.krx || e.ticker ? `<a class="chartlink" href="#/chart?s=${enc(e.krx || e.ticker)}">차트 보기 →</a>` : ""}</div></header>
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

  // ---------------------------------------------------------------- 소문
  const RUMOR_CLS = { "미확인": "r-open", "사실로 확인": "r-true", "부인": "r-denied", "소멸": "r-faded" };

  function viewRumors(params) {
    setNav("rumors");
    document.title = "시장 소문 · Deal Archive";
    const all = DATA.rumors || [];
    const want = params.get("status") || "미확인";
    const list = want === "전체" ? all : all.filter((r) => r.status === want);
    const count = (s) => all.filter((r) => r.status === s).length;
    const closed = count("사실로 확인") + count("부인") + count("소멸");
    const hit = closed ? Math.round((count("사실로 확인") / closed) * 100) : null;
    const tabs = ["미확인", "사실로 확인", "부인", "소멸", "전체"].map((s) =>
      `<a class="chip${s === want ? " on" : ""}" href="#/rumors?status=${enc(s)}">${esc(s)}<span class="n">${s === "전체" ? all.length : count(s)}</span></a>`).join("");

    const cards = list.map((r) => {
      const deal = r.deal && DATA.deals.find((d) => d.id === r.deal);
      const comps = r.companies.map((c) => (DATA.entities[c] ? entLink(c) : esc(c))).join(", ");
      const srcs = r.sources.map((s) => `<li>${s.url ? `<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}
        <span class="cred cred-${s.credibility === "중간" ? "mid" : "low"}">공신력 ${esc(s.credibility)}</span></li>`).join("");
      return `<article class="rumor">
        <div class="rumor-top"><span class="rstatus ${RUMOR_CLS[r.status] || ""}">${esc(r.status)}</span>
          <span class="muted">처음 ${esc(r.first_seen)}${r.last_seen !== r.first_seen ? ` · 최근 ${esc(r.last_seen)}` : ""}</span></div>
        <h2>${esc(r.title)}</h2>
        <p class="rumor-claim">${esc(r.claim)}</p>
        ${r.why_watch ? `<p class="rumor-why"><b>사실이라면</b> ${esc(r.why_watch)}</p>` : ""}
        ${comps ? `<p class="rumor-meta">관련: ${comps}</p>` : ""}
        ${deal ? `<p class="rumor-meta">확인된 딜: <a href="#/deal/${enc(deal.id)}">${esc(deal.title)}</a></p>` : ""}
        ${r.status_note ? `<p class="rumor-meta">${esc(r.status_note)}</p>` : ""}
        <ul class="rumor-src">${srcs}</ul>
      </article>`;
    }).join("");

    $app.innerHTML = `<div class="kicker"><span>시장 소문</span><span class="aside">${hit === null ? "결과가 나온 소문이 아직 없음" : `결과가 나온 ${closed}건 중 ${hit}%가 사실로 확인`}</span></div>
      <div class="warn warn-strong">
        <b>소문입니다. 사실로 확인되지 않은 정보이며, 절대 투자 판단의 참고 자료가 아닙니다.</b>
        <p>이 탭은 운영자가 개인 자료 조사(시장 공부) 과정에서 접한 미확인 보도·풍문을 기록해 두고, 나중에 사실 여부를 대조해 보기 위한 학습 기록입니다.
        포트폴리오로 보여줄 수 있도록 공개해 두었을 뿐, 정보를 공유하거나 전달하려는 목적이 아닙니다.
        이곳의 내용을 근거로 매매하거나 다른 곳에 옮겨 퍼뜨리지 마세요. 각 항목은 원 출처가 보도한 내용을 '소문'으로 표시한 것이며, 운영자는 그 내용이 사실이라고 주장하지 않습니다.</p>
      </div>
      <div class="chips rumor-tabs">${tabs}</div>
      ${cards || `<div class="empty">해당하는 소문이 없습니다.</div>`}`;
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
    annotate($app.querySelector(".prose"));
  }

  // ---------------------------------------------------------------- 시세 공통
  const isDark = () => document.documentElement.dataset.theme === "dark" ||
    (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  const fmtNum = (v, idx) => (v == null ? "–" : Number(v).toLocaleString("ko-KR", idx ? { minimumFractionDigits: 2, maximumFractionDigits: 2 } : { maximumFractionDigits: 0 }));
  // 한국식: 상승 빨강, 하락 파랑
  const chg = (p) => (p == null ? "" : `<span class="${p > 0 ? "up" : p < 0 ? "dn" : ""}">${p > 0 ? "▲" : p < 0 ? "▼" : ""}${Math.abs(p).toFixed(2)}%</span>`);

  function stripItem(code) {
    if (code === "USDKRW") return MKT.fx.USD ? { code, name: "원/달러", close: MKT.fx.USD, change_pct: MKT.fx.USD_change_pct, idx: true, href: "FX_IDC:USDKRW" } : null;
    const x = MKT.items.find((i) => i.code === code);
    return x ? { code, name: x.name, close: x.close, change_pct: x.change_pct, idx: x.kind === "index", href: x.code, date: x.date } : null;
  }

  function marketStrip() {
    const items = CFG.strip.map(stripItem).filter(Boolean);
    const edit = isOwner() ? `<a class="mq-edit" href="#/settings" aria-label="위쪽 띠 편집">편집</a>` : "";
    if (!items.length) return `${edit ? `<div class="mstrip">${edit}</div>` : ""}<div id="tt" class="tt"></div>`;
    const date = items.find((x) => x.date)?.date;
    const chips = items.map((x) => `<a class="mq" href="#/chart?s=${enc(x.href)}"><span class="mq-n">${esc(x.name)}</span><b>${fmtNum(x.close, x.idx)}</b>${chg(x.change_pct)}</a>`).join("");
    const usesFx = items.some((x) => x.code === "USDKRW");
    return `<div class="mstrip"><div class="mq-row">${chips}</div><span class="mdate">${date ? `국내 ${fmtDate(date)} 종가` : ""}${usesFx && MKT.fx.date ? ` · 환율 ECB ${fmtDate(MKT.fx.date)}` : ""}${edit}</span></div>
      <div id="tt" class="tt"></div>`;
  }

  function tvEmbed(el, script, config) {
    el.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "tradingview-widget-container";
    const inner = document.createElement("div");
    inner.className = "tradingview-widget-container__widget";
    wrap.appendChild(inner);
    const s = document.createElement("script");
    s.src = `https://s3.tradingview.com/external-embedding/${script}`;
    s.async = true;
    s.text = JSON.stringify(config);
    wrap.appendChild(s);
    el.appendChild(wrap);
  }

  const globalPicks = () => CFG.tape.map((t) => [t.symbol, t.title]);

  function tickerTape(el) {
    tvEmbed(el, "embed-widget-ticker-tape.js", {
      symbols: CFG.tape.map((t) => ({ proName: t.symbol, title: t.title })),
      showSymbolLogo: false, isTransparent: true, displayMode: "compact",
      colorTheme: isDark() ? "dark" : "light", locale: "kr",
    });
  }

  let lwcLoading = null;
  function loadLWC() {
    if (window.LightweightCharts) return Promise.resolve();
    if (!lwcLoading) lwcLoading = new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = "https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js";
      s.onload = ok; s.onerror = fail;
      document.head.appendChild(s);
    });
    return lwcLoading;
  }

  // ---------------------------------------------------------------- 차트
  function krList() { return MKT.items.slice().sort((a, b) => (a.kind === b.kind ? (a.name || "").localeCompare(b.name || "", "ko") : a.kind === "index" ? -1 : 1)); }

  function searchMarket(q) {
    const s = q.trim().toLowerCase();
    if (!s) return { kr: krList(), global: [] };
    const kr = krList().filter((x) => (x.name || "").toLowerCase().includes(s) || (x.code || "").toLowerCase().includes(s) ||
      (s === "코스피" && x.code === "KOSPI") || (s === "코스닥" && x.code === "KOSDAQ"));
    const global = Object.entries(DATA.entities).filter(([n, e]) => e.ticker &&
      (n.toLowerCase().includes(s) || e.ticker.toLowerCase().includes(s) || (e.aliases || []).some((a) => a.toLowerCase().includes(s))))
      .map(([n, e]) => ({ name: n, ticker: e.ticker }));
    globalPicks().forEach(([sym, title]) => { if (title.toLowerCase().includes(s) || sym.toLowerCase().includes(s)) global.push({ name: title, ticker: sym }); });
    return { kr, global };
  }

  function viewChart(params) {
    setNav("chart");
    document.title = "차트 · Deal Archive";
    const sym = (params.get("s") || "KOSPI").trim();
    const krItem = MKT.items.find((x) => x.code === sym || x.code === sym.toUpperCase());
    const editLink = isOwner() ? `<a class="editbtn" href="#/settings">편집</a>` : "";

    $app.innerHTML = `<div class="kicker"><span>차트</span><span class="aside">국내는 일별 종가(공공데이터), 해외는 TradingView 지연 시세</span></div>
      <div class="chart-search">
        <input class="search" id="cq" type="search" placeholder="종목명, 종목코드, 해외 티커 (예: 삼성전자, 005930, AAPL, NASDAQ:DASH)" aria-label="차트 검색">
        <div id="cres" class="cres" hidden></div>
      </div>
      <div class="chart-head" id="chead"></div>
      <div id="cbox" class="cbox"></div>
      <div class="chart-foot">
        <div class="kicker"><span>추적 중인 국내 종목</span><span class="aside">${editLink}</span></div>
        <div class="klist">${krList().map((x) => `<a class="kitem${x.code === (krItem && krItem.code) ? " on" : ""}" href="#/chart?s=${enc(x.code)}">
          <span>${esc(x.name)}<small>${esc(x.kind === "index" ? "지수" : x.code)}</small></span><span><b>${fmtNum(x.close, x.kind === "index")}</b> ${chg(x.change_pct)}</span></a>`).join("") || `<p class="muted">아직 수집된 국내 시세가 없습니다.</p>`}</div>
        <div class="kicker"><span>해외 바로가기</span></div>
        <div class="chips">${globalPicks().map(([s, n]) => `<a class="chip${s === sym ? " on" : ""}" href="#/chart?s=${enc(s)}">${esc(n)}</a>`).join("")}</div>
      </div>`;

    const cq = document.getElementById("cq"), cres = document.getElementById("cres");
    const render = () => {
      const q = cq.value.trim();
      if (!q) { cres.hidden = true; return; }
      const { kr, global } = searchMarket(q);
      const up = q.toUpperCase().replace(/\s+/g, "");
      cres.innerHTML = [
        ...kr.slice(0, 8).map((x) => `<a href="#/chart?s=${enc(x.code)}">${esc(x.name)} <small>${esc(x.kind === "index" ? "지수" : x.code)} · 국내</small></a>`),
        ...global.slice(0, 6).map((x) => `<a href="#/chart?s=${enc(x.ticker)}">${esc(x.name)} <small>${esc(x.ticker)} · 해외</small></a>`),
        /^[A-Z0-9.:_!-]{1,20}$/.test(up) && !/^\d{6}$/.test(up) ? `<a href="#/chart?s=${enc(up)}">"${esc(up)}" 해외 티커로 보기 <small>TradingView</small></a>` : "",
        ...untracked(q, kr).map(([c, n]) => isOwner()
          ? `<a href="#/settings?add=${enc(c)}">${esc(n)} <small>${esc(c)} · 추적 안 함 — 눌러서 추가</small></a>`
          : `<span class="muted">${esc(n)} <small>${esc(c)} · 추적하지 않는 종목</small></span>`),
      ].filter(Boolean).join("") || `<span class="muted">결과 없음</span>`;
      cres.hidden = false;
    };
    cq.addEventListener("input", render);
    cq.addEventListener("focus", () => loadKrx().then(() => cq.value && render()), { once: true });
    cq.addEventListener("search", render);
    document.addEventListener("click", (e) => { if (!e.target.closest(".chart-search")) cres.hidden = true; });
    cq.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const first = cres.querySelector("a");
      if (first) location.hash = first.getAttribute("href");
    });

    const chead = document.getElementById("chead"), cbox = document.getElementById("cbox");
    if (krItem) {
      chead.innerHTML = `<h1>${esc(krItem.name)} <small>${esc(krItem.kind === "index" ? "지수" : `${krItem.code} · ${krItem.market || ""}`)}</small></h1>
        <div class="cq-last"><b>${fmtNum(krItem.close, krItem.kind === "index")}</b> ${chg(krItem.change_pct)} <span class="muted">${esc(krItem.date)} 종가</span></div>
        <div class="chips ranges">${["1M", "3M", "6M", "1Y", "전체"].map((r) => `<button class="chip${r === "6M" ? " on" : ""}" data-r="${r}">${r}</button>`).join("")}</div>`;
      krChart(cbox, krItem);
    } else {
      chead.innerHTML = `<h1>${esc(sym)} <small>TradingView</small></h1>`;
      cbox.classList.add("tv");
      tvEmbed(cbox, "embed-widget-advanced-chart.js", {
        autosize: true, symbol: sym, interval: "D", timezone: "Asia/Seoul", theme: isDark() ? "dark" : "light",
        style: "2", locale: "kr", allow_symbol_change: true, hide_side_toolbar: true, calendar: false,
        support_host: "https://www.tradingview.com",
      });
    }
  }

  function krChart(box, item) {
    box.innerHTML = `<p class="muted pad">차트 불러오는 중…</p>`;
    Promise.all([loadLWC(), fetch(`market/kr/${enc(item.code)}.json`, { cache: "no-cache" }).then((r) => r.json())])
      .then(([, data]) => {
        box.innerHTML = "";
        const css = getComputedStyle(document.documentElement);
        const ink = css.getPropertyValue("--ink-2").trim(), rule = css.getPropertyValue("--rule").trim();
        const chart = LightweightCharts.createChart(box, {
          autoSize: true,
          layout: { background: { color: "transparent" }, textColor: ink, fontFamily: "Pretendard Variable, sans-serif" },
          grid: { vertLines: { visible: false }, horzLines: { color: rule } },
          rightPriceScale: { borderVisible: false },
          timeScale: { borderVisible: false },
          localization: { locale: "ko-KR", priceFormatter: (v) => fmtNum(v, item.kind === "index") },
        });
        const s = data.series || [];
        const first = s[0]?.[4], last = s[s.length - 1]?.[4];
        const color = last >= first ? "#d6403a" : "#2f6fd1";
        const line = chart.addAreaSeries({ lineColor: color, topColor: color + "33", bottomColor: color + "00", lineWidth: 2,
          priceLineVisible: false });
        line.setData(s.filter((r) => r[4] != null).map((r) => ({ time: r[0], value: r[4] })));
        if (item.kind !== "index") {
          const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "", color: rule });
          vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
          vol.setData(s.filter((r) => r[5] != null).map((r) => ({ time: r[0], value: r[5] })));
        }
        const setRange = (r) => {
          if (r === "전체" || !s.length) return chart.timeScale().fitContent();
          const months = { "1M": 1, "3M": 3, "6M": 6, "1Y": 12 }[r];
          const to = new Date(s[s.length - 1][0]); const from = new Date(to); from.setMonth(from.getMonth() - months);
          chart.timeScale().setVisibleRange({ from: from.toISOString().slice(0, 10), to: s[s.length - 1][0] });
        };
        setRange("6M");
        document.querySelectorAll(".ranges .chip").forEach((b) => b.addEventListener("click", () => {
          document.querySelectorAll(".ranges .chip").forEach((x) => x.classList.toggle("on", x === b));
          setRange(b.dataset.r);
        }));
      })
      .catch(() => { box.innerHTML = `<p class="pad muted">차트를 불러오지 못했습니다.</p>`; });
  }

  // ---------------------------------------------------------------- 상장 종목 목록 (검색용, 필요할 때만 받음)
  let KRX = null, krxLoading = null;
  function loadKrx() {
    if (KRX) return Promise.resolve(KRX);
    if (!krxLoading) krxLoading = fetch("market/krx_list.json", { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : { items: [] })).then((d) => (KRX = d.items || [])).catch(() => (KRX = []));
    return krxLoading;
  }
  const norm = (x) => String(x || "").toLowerCase().replace(/\s+/g, "");
  function krxSearch(q, limit = 10) {
    const s = norm(q);
    if (!s || !KRX) return [];
    const hit = KRX.filter(([c, n]) => c.startsWith(s.toUpperCase()) || norm(n).includes(s));
    hit.sort((a, b) => (norm(a[1]).startsWith(s) ? 0 : 1) - (norm(b[1]).startsWith(s) ? 0 : 1) || a[1].length - b[1].length);
    return hit.slice(0, limit);
  }
  function untracked(q, kr) {
    const have = new Set(kr.map((x) => x.code).concat(MKT.items.map((x) => x.code)));
    return krxSearch(q, 6).filter(([c]) => !have.has(c));
  }

  // ---------------------------------------------------------------- 시세 설정 (주인만)
  const LIM = { strip: 8, stocks: 60, tape: 12 };
  const TV_RE = /^[A-Z0-9_]{1,20}:[A-Z0-9._!-]{1,30}$/;

  function viewSettings(params) {
    setNav("chart");
    document.title = "시세 설정 · Deal Archive";
    if (!isOwner()) {
      $app.innerHTML = `<div class="kicker"><span>시세 설정</span></div><p class="muted">이 화면은 사이트 주인만 사용합니다. <a href="#/chart">차트로 돌아가기</a></p>`;
      return;
    }
    const pick = (o) => JSON.parse(JSON.stringify({ strip: o.strip, indices: o.indices, stocks: o.stocks, exclude: o.exclude, tape: o.tape }));
    const orig = pick(CFG);
    const draft = pick(CFG);
    let found = [], msg = "";

    const nameOf = (code) => code === "USDKRW" ? "원/달러" : CFG.catalog.indices[code]
      || (draft.stocks.find((r) => r.code === code) || {}).name || CFG.auto[code]
      || (MKT.items.find((x) => x.code === code) || {}).name || code;
    const tracked = () => {
      const out = new Map(draft.stocks.map((r) => [r.code, r.name]));
      for (const [c, n] of Object.entries(CFG.auto)) if (!out.has(c) && !draft.exclude.includes(c)) out.set(c, n);
      return out;
    };
    const stripOptions = () => [...draft.indices, "USDKRW", ...tracked().keys()].filter((c) => !draft.strip.includes(c));
    const changes = () => Object.keys(orig).filter((k) => JSON.stringify(orig[k]) !== JSON.stringify(draft[k])).length;
    const cleanStrip = () => { const ok = new Set([...draft.indices, "USDKRW", ...tracked().keys()]); draft.strip = draft.strip.filter((c) => ok.has(c)); };
    const btns = (list, i) => `<span class="rowbtns">
      <button data-act="up" data-list="${list}" data-i="${i}" aria-label="위로"${i === 0 ? " disabled" : ""}>↑</button>
      <button data-act="down" data-list="${list}" data-i="${i}" aria-label="아래로"${i === draft[list].length - 1 ? " disabled" : ""}>↓</button>
      <button data-act="del" data-list="${list}" data-i="${i}" aria-label="빼기">×</button></span>`;

    const draw = () => {
      const n = changes();
      const tickers = Object.entries(DATA.entities).filter(([, e]) => e.ticker && !draft.tape.some((t) => t.symbol === e.ticker)).slice(0, 12);
      $app.innerHTML = `<div class="crumb"><a href="#/chart">← 차트</a></div>
      <div class="kicker"><span>시세 설정</span><span class="aside">주인 전용</span></div>
      <p class="set-note">여기서 고친 뒤 <b>저장</b>을 누르면 GitHub 이슈 작성 화면이 열립니다. 내용은 채워져 있으니 <b>Create</b>만 누르면 1~2분 뒤 사이트에 반영돼요.
        suncow-hub 계정으로 로그인돼 있어야 적용되고, 다른 사람이 올린 설정 이슈는 자동으로 무시됩니다.</p>

      <section class="set">
        <h2>첫 화면 위쪽 띠 <small>${draft.strip.length}/${LIM.strip} · 순서대로 보임</small></h2>
        <ol class="slist">${draft.strip.map((c, i) => `<li><span>${esc(nameOf(c))}<small>${esc(c === "USDKRW" ? "환율" : CFG.catalog.indices[c] ? "지수" : c)}</small></span>${btns("strip", i)}</li>`).join("") || `<li class="muted">비어 있음</li>`}</ol>
        <div class="set-add">${draft.strip.length < LIM.strip && stripOptions().length
          ? `<select id="strip-add" aria-label="띠에 넣을 항목">${stripOptions().map((c) => `<option value="${esc(c)}">${esc(nameOf(c))} (${esc(c)})</option>`).join("")}</select><button class="chip" data-act="strip-add">추가</button>`
          : `<span class="muted">${draft.strip.length >= LIM.strip ? "최대 개수입니다." : "더 넣을 항목이 없습니다. 아래에서 지수나 종목을 먼저 추가하세요."}</span>`}</div>
      </section>

      <section class="set">
        <h2>수집할 국내 지수</h2>
        <div class="chips">${Object.entries(CFG.catalog.indices).map(([c, nm]) => `<button class="chip${draft.indices.includes(c) ? " on" : ""}" data-act="idx" data-c="${esc(c)}" aria-pressed="${draft.indices.includes(c)}">${esc(nm)}</button>`).join("")}</div>
        <p class="hint">새로 켠 지수는 저장 직후 1년치를 받아 옵니다.</p>
      </section>

      <section class="set">
        <h2>관심 종목 <small>직접 추가 ${draft.stocks.length}/${LIM.stocks}</small></h2>
        <div class="chart-search"><input class="search" id="sq" type="search" placeholder="종목명이나 종목코드 (예: 네이버, 035420)" aria-label="종목 검색" autocomplete="off">
          <div id="sres" class="cres" hidden></div></div>
        <ul class="slist">${draft.stocks.map((r, i) => `<li><span>${esc(r.name)}<small>${esc(r.code)}</small></span><span class="rowbtns"><button data-act="del" data-list="stocks" data-i="${i}" aria-label="빼기">×</button></span></li>`).join("") || `<li class="muted">직접 추가한 종목이 없습니다.</li>`}</ul>
      </section>

      <section class="set">
        <h2>자동 추적 <small>딜 아카이브에 나온 상장사</small></h2>
        <ul class="slist">${Object.entries(CFG.auto).map(([c, nm]) => { const off = draft.exclude.includes(c); return `<li class="${off ? "off" : ""}"><span>${esc(nm)}<small>${esc(c)}</small></span>
          <button class="chip${off ? "" : " on"}" data-act="auto" data-c="${esc(c)}" aria-pressed="${!off}">${off ? "제외됨" : "추적 중"}</button></li>`; }).join("") || `<li class="muted">아직 없습니다.</li>`}</ul>
      </section>

      <section class="set">
        <h2>해외 시세 흐름띠 <small>${draft.tape.length}/${LIM.tape} · TradingView</small></h2>
        <ol class="slist">${draft.tape.map((t, i) => `<li><span>${esc(t.title)}<small>${esc(t.symbol)}</small></span>${btns("tape", i)}</li>`).join("") || `<li class="muted">비어 있음</li>`}</ol>
        ${draft.tape.length < LIM.tape ? `<div class="set-add tape-add">
          <input class="search" id="tsym" placeholder="거래소:티커 (예: NASDAQ:AAPL)" aria-label="TradingView 기호" autocapitalize="characters" autocomplete="off">
          <input class="search" id="tname" placeholder="보일 이름 (예: 애플)" aria-label="보일 이름" maxlength="20" autocomplete="off">
          <button class="chip" data-act="tape-add">추가</button></div>` : ""}
        ${tickers.length ? `<div class="chips sugg">${tickers.map(([nm, e]) => `<button class="chip" data-act="tape-sugg" data-c="${esc(e.ticker)}" data-n="${esc(nm)}">+ ${esc(nm)}</button>`).join("")}</div>` : ""}
        <p class="hint">한국·일본·홍콩 종목은 TradingView 무료 위젯에서 보이지 않습니다. 기호는 TradingView 검색창에 나오는 '거래소:티커' 그대로 쓰면 됩니다.</p>
      </section>

      <div class="savebar">
        <span>${n ? `바뀐 항목 ${n}개` : "바뀐 것 없음"}</span>
        <span><button class="linkbtn" data-act="reset"${n ? "" : " disabled"}>되돌리기</button>
        <button class="savebtn" data-act="save"${n ? "" : " disabled"}>저장</button></span>
      </div>`;
    };
    const results = () => {
      const el = document.getElementById("sres");
      if (!el) return;
      el.innerHTML = found.map(([c, nm, mk]) => `<button data-act="stock-add" data-c="${esc(c)}" data-n="${esc(nm)}">${esc(nm)} <small>${esc(c)}${mk ? " · " + esc(mk) : ""}${tracked().has(c) ? " · 이미 추적 중" : ""}</small></button>`).join("")
        + (msg ? `<span class="muted">${esc(msg)}</span>` : "");
      el.hidden = !found.length && !msg;
    };

    let lastQ = "";
    const redrawKeep = () => {
      const y = window.scrollY;
      const tsym = document.getElementById("tsym")?.value || "", tname = document.getElementById("tname")?.value || "";
      draw();
      window.scrollTo(0, y);
      const a = document.getElementById("tsym"), b = document.getElementById("tname");
      if (a) a.value = tsym; if (b) b.value = tname;
    };

    $app.oninput = (e) => {
      if (e.target.id !== "sq") return;
      lastQ = e.target.value;
      loadKrx().then(() => {
        found = krxSearch(lastQ, 8);
        msg = lastQ.trim() && !found.length ? (KRX.length ? "결과 없음" : "종목 목록이 아직 없습니다 (다음 시세 수집 뒤 생김). 6자리 코드를 그대로 넣으면 추가할 수 있어요.") : "";
        if (!found.length && /^\d{6}$/.test(lastQ.trim()) && !KRX.length) found = [[lastQ.trim(), lastQ.trim(), ""]];
        results();   // 입력칸은 그대로 두고 결과만 바꾼다 (한글 입력이 끊기지 않게)
      });
    };

    $app.onclick = (e) => {
      const b = e.target.closest("[data-act]");
      if (!b || b.disabled) return;
      const act = b.dataset.act, list = b.dataset.list, i = +b.dataset.i, c = b.dataset.c;
      if (act === "up" && i > 0) [draft[list][i - 1], draft[list][i]] = [draft[list][i], draft[list][i - 1]];
      if (act === "down" && i < draft[list].length - 1) [draft[list][i + 1], draft[list][i]] = [draft[list][i], draft[list][i + 1]];
      if (act === "del") { draft[list].splice(i, 1); cleanStrip(); }
      if (act === "strip-add") { const v = document.getElementById("strip-add").value; if (v && draft.strip.length < LIM.strip) draft.strip.push(v); }
      if (act === "idx") { draft.indices = draft.indices.includes(c) ? draft.indices.filter((x) => x !== c) : Object.keys(CFG.catalog.indices).filter((x) => x === c || draft.indices.includes(x)); cleanStrip(); }
      if (act === "auto") { draft.exclude = draft.exclude.includes(c) ? draft.exclude.filter((x) => x !== c) : draft.exclude.concat(c); cleanStrip(); }
      if (act === "stock-add") {
        if (CFG.auto[c] && draft.exclude.includes(c)) draft.exclude = draft.exclude.filter((x) => x !== c);
        else if (!tracked().has(c) && draft.stocks.length < LIM.stocks) draft.stocks.push({ code: c, name: b.dataset.n });
        found = []; msg = ""; lastQ = "";
      }
      if (act !== "stock-add" && e.target.closest(".chart-search")) return;
      if (act === "tape-add" || act === "tape-sugg") {
        const sym = (act === "tape-sugg" ? c : document.getElementById("tsym").value).trim().toUpperCase();
        const title = (act === "tape-sugg" ? b.dataset.n : document.getElementById("tname").value.trim() || sym.split(":")[1] || "").slice(0, 20);
        if (!TV_RE.test(sym)) { alertInline("'거래소:티커' 형식으로 적어 주세요. 예: NASDAQ:AAPL"); return; }
        if (draft.tape.some((t) => t.symbol === sym)) { alertInline("이미 들어 있습니다."); return; }
        if (draft.tape.length < LIM.tape) draft.tape.push({ symbol: sym, title });
        if (act === "tape-add") { document.getElementById("tsym").value = ""; document.getElementById("tname").value = ""; }
      }
      if (act === "reset") Object.assign(draft, pick(orig));
      if (act === "save") return save();
      redrawKeep();
    };

    const alertInline = (t) => {
      let el = document.getElementById("set-msg");
      if (!el) { el = document.createElement("p"); el.id = "set-msg"; el.className = "set-msg"; document.querySelector(".tape-add")?.after(el); }
      el.textContent = t;
    };

    const save = () => {
      const q = (v) => JSON.stringify(String(v));
      const yaml = [
        `strip: [${draft.strip.map(q).join(", ")}]`,
        `indices: [${draft.indices.map(q).join(", ")}]`,
        "stocks:" + (draft.stocks.length ? "" : " []"),
        ...draft.stocks.map((r) => `  - {code: ${q(r.code)}, name: ${q(r.name)}}`),
        `exclude: [${draft.exclude.map(q).join(", ")}]`,
        "tape:" + (draft.tape.length ? "" : " []"),
        ...draft.tape.map((t) => `  - {symbol: ${q(t.symbol)}, title: ${q(t.title)}}`),
      ].join("\n");
      const body = "사이트 편집 화면에서 만든 시세 설정입니다. 이대로 제출하면 자동으로 적용돼요.\n\n```yaml\n" + yaml + "\n```\n";
      window.open(`${REPO}/issues/new?title=${enc("[설정] 시세 설정 변경")}&body=${enc(body)}`, "_blank", "noopener");
      const bar = document.querySelector(".savebar span");
      if (bar) bar.textContent = "GitHub 창에서 Create를 누르면 적용돼요.";
    };

    const add = params.get("add");
    if (add && /^[0-9A-Z]{6}$/.test(add)) {
      loadKrx().then(() => {
        const hit = (KRX || []).find(([c2]) => c2 === add);
        if (hit && !tracked().has(add)) draft.stocks.push({ code: add, name: hit[1] });
        history.replaceState(null, "", "#/settings");
        draw();
      });
    } else draw();
    loadKrx();
  }

  // ---------------------------------------------------------------- 용어집
  const G_CATS = ["밸류에이션", "딜 구조", "자금 조달", "참여자·전략", "공시·규제", "거시경제"];
  let G_RE = null, G_BY = {}, G_LOOK = {};

  function prepGlossary() {
    const pats = [];
    for (const g of DATA.glossary || []) {
      G_BY[g.id] = g;
      for (const k of [g.term, ...(g.match || []), ...(g.aliases || []), g.en].filter(Boolean)) G_LOOK[k.toLowerCase()] = g.id;
      for (const m of g.match || []) pats.push([m, g.id]);
    }
    pats.sort((a, b) => b[0].length - a[0].length);
    const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (pats.length) {
      try {
        G_RE = new RegExp(pats.map(([m]) => /^[\x00-\x7F]+$/.test(m) ? `(?<![A-Za-z0-9])${escRe(m)}(?![A-Za-z0-9])` : escRe(m)).join("|"), "g");
      } catch (e) { // 오래된 브라우저(뒤쪽 경계 미지원)
        G_RE = new RegExp(pats.map(([m]) => escRe(m)).join("|"), "g");
      }
    }
    G_RE && (G_RE.pats = pats);
  }

  function idFor(text) { return G_LOOK[text.toLowerCase()]; }

  // 본문 텍스트에서 용어를 찾아 점선 밑줄을 친다 (용어마다 처음 한 번만)
  function annotate(root) {
    if (!root || !G_RE) return;
    const seen = new Set();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => n.parentElement.closest("a, code, .term, h1") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const text = node.nodeValue;
      G_RE.lastIndex = 0;
      let m, last = 0, frag = null;
      while ((m = G_RE.exec(text))) {
        const id = idFor(m[0]);
        if (!id || seen.has(id)) continue;
        seen.add(id);
        frag ||= document.createDocumentFragment();
        frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        const span = document.createElement("span");
        span.className = "term"; span.dataset.g = id; span.tabIndex = 0; span.textContent = m[0];
        frag.appendChild(span);
        last = m.index + m[0].length;
      }
      if (frag) { frag.appendChild(document.createTextNode(text.slice(last))); node.replaceWith(frag); }
    }
  }

  const tip = document.createElement("div");
  tip.className = "gtip"; tip.hidden = true; tip.setAttribute("role", "tooltip");
  document.body.appendChild(tip);
  let tipHideT = null;

  function showTipAt(rect, html) {
    clearTimeout(tipHideT);
    tip.innerHTML = html; tip.hidden = false;
    const w = Math.min(320, window.innerWidth - 24);
    tip.style.width = w + "px";
    let left = rect.left + window.scrollX + rect.width / 2 - w / 2;
    left = Math.max(12 + window.scrollX, Math.min(left, window.scrollX + window.innerWidth - w - 12));
    tip.style.left = left + "px";
    const below = rect.bottom + window.scrollY + 8;
    tip.style.top = below + "px";
    const h = tip.offsetHeight;
    if (rect.bottom + h + 16 > window.innerHeight && rect.top > h + 16) tip.style.top = (rect.top + window.scrollY - h - 8) + "px";
  }
  function hideTip() { tip.hidden = true; }

  function termHtml(id) {
    const g = G_BY[id];
    return `<div class="gt-h"><b>${esc(g.term)}</b>${g.en ? `<span>${esc(g.en)}</span>` : ""}</div><p>${esc(g.short)}</p>
      <a href="#/glossary?t=${enc(g.id)}">용어집에서 자세히 →</a>`;
  }

  function askHtml(word) {
    const url = `${REPO}/issues/new?title=${enc("[용어] " + word)}&body=${enc(`나온 곳: ${location.href}\n\n이대로 제출하면 다음 새벽 작업이 용어집에 풀이를 추가합니다.`)}`;
    return `<div class="gt-h"><b>${esc(word)}</b></div><p class="muted">아직 용어집에 없는 단어예요.</p>
      <a class="gt-ask" href="${url}" target="_blank" rel="noopener">이 단어 물어보기 →</a>`;
  }

  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest && e.target.closest(".term");
    if (t && matchMedia("(hover: hover)").matches) showTipAt(t.getBoundingClientRect(), termHtml(t.dataset.g));
  });
  document.addEventListener("mouseout", (e) => {
    const t = e.target.closest && e.target.closest(".term, .gtip");
    if (t && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".gtip, .term"))) tipHideT = setTimeout(hideTip, 250);
  });
  document.addEventListener("click", (e) => {
    const t = e.target.closest(".term");
    if (t) { e.preventDefault(); showTipAt(t.getBoundingClientRect(), termHtml(t.dataset.g)); return; }
    if (!e.target.closest(".gtip")) {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) hideTip();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideTip();
    if (e.key === "Enter" && document.activeElement?.classList.contains("term")) showTipAt(document.activeElement.getBoundingClientRect(), termHtml(document.activeElement.dataset.g));
  });

  // 드래그한 단어: 용어집에 있으면 풀이, 없으면 '물어보기'
  const PARTICLES = /(으로|에서|에게|까지|부터|이라|라는|이다|은|는|이|가|을|를|의|에|로|와|과|도|만)$/;
  function onSelect() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    if (!node || !node.closest("#app") || node.closest("input, textarea, .search")) return;
    let word = sel.toString().trim().replace(/[.,·()"'“”‘’]/g, "").trim();
    if (!word || word.length > 30 || /\n/.test(word)) return;
    let id = idFor(word);
    if (!id && PARTICLES.test(word)) { const w2 = word.replace(PARTICLES, ""); id = idFor(w2); if (!id) word = w2 || word; }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    showTipAt(rect, id ? termHtml(id) : askHtml(word));
  }
  document.addEventListener("mouseup", () => setTimeout(onSelect, 10));
  document.addEventListener("touchend", () => setTimeout(onSelect, 350));

  function viewGlossary(params) {
    setNav("glossary");
    document.title = "용어집 · Deal Archive";
    const focus = params.get("t");
    const all = (DATA.glossary || []).slice();
    const byTerm = Object.fromEntries(all.map((g) => [g.term, g]));
    const card = (g) => `<article class="gterm${g.id === focus ? " focus" : ""}" id="g-${esc(g.id)}" data-cat="${esc(g.category)}"
        data-text="${esc([g.term, g.en, ...(g.match || []), ...(g.aliases || []), g.short].join(" ").toLowerCase())}">
        <h2>${esc(g.term)} ${g.en ? `<small>${esc(g.en)}</small>` : ""}</h2>
        <p class="g-short">${esc(g.short)}</p>
        ${g.more ? `<p>${esc(g.more)}</p>` : ""}
        ${g.example ? `<p class="g-ex"><b>예시</b> ${esc(g.example)}${g.deal && DATA.deals.find((d) => d.id === g.deal) ? ` <a href="#/deal/${enc(g.deal)}">딜 노트 →</a>` : ""}</p>` : ""}
        ${(g.related || []).length ? `<p class="g-rel">같이 보기: ${g.related.map((r) => byTerm[r] ? `<a href="#/glossary?t=${enc(byTerm[r].id)}">${esc(r)}</a>` : esc(r)).join(" · ")}</p>` : ""}
        ${g.memo ? `<div class="g-memo"><b>내 메모</b> ${esc(g.memo)}</div>` : ""}
      </article>`;
    const sections = G_CATS.map((c) => {
      const items = all.filter((g) => g.category === c).sort((a, b) => a.term.localeCompare(b.term, "ko"));
      return items.length ? `<section class="gsec" data-cat="${esc(c)}"><div class="kicker"><span>${esc(c)}</span><span class="aside">${items.length}</span></div>${items.map(card).join("")}</section>` : "";
    }).join("");

    $app.innerHTML = `<div class="kicker"><span>용어집</span><span class="aside">${all.length}개 · <a href="${REPO}/edit/main/glossary.yml" target="_blank" rel="noopener">내 메모 쓰기</a></span></div>
      <div class="warn">딜 노트와 브리핑에서 점선 밑줄 단어에 마우스를 올리거나 탭하면 뜻이 떠요. 모르는 단어는 드래그하면 바로 찾아보고, 없으면 물어볼 수 있어요.</div>
      <input class="search" id="gq" type="search" placeholder="용어 검색 (한글·영어)" aria-label="용어 검색">
      <div class="chips gcats"><button class="chip on" data-c="">전체</button>${G_CATS.map((c) => `<button class="chip" data-c="${esc(c)}">${esc(c)}</button>`).join("")}</div>
      <div id="glist">${sections || `<p class="muted">아직 용어가 없습니다.</p>`}</div>`;

    let cat = "";
    const apply = () => {
      const q = document.getElementById("gq").value.trim().toLowerCase();
      $app.querySelectorAll(".gterm").forEach((el) => {
        el.hidden = !((!cat || el.dataset.cat === cat) && (!q || el.dataset.text.includes(q)));
      });
      $app.querySelectorAll(".gsec").forEach((s) => { s.hidden = ![...s.querySelectorAll(".gterm")].some((x) => !x.hidden); });
    };
    document.getElementById("gq").addEventListener("input", apply);
    $app.querySelectorAll(".gcats .chip").forEach((b) => b.addEventListener("click", () => {
      cat = b.dataset.c; $app.querySelectorAll(".gcats .chip").forEach((x) => x.classList.toggle("on", x === b)); apply();
    }));
    if (focus) { const el = document.getElementById(`g-${focus}`); if (el) setTimeout(() => el.scrollIntoView({ block: "center" }), 50); }
  }

  // ---------------------------------------------------------------- 시작
  const d = new Date(Date.now() + 9 * 3600e3);
  document.getElementById("today").textContent =
    `${d.getUTCFullYear()}년 ${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 ${"일월화수목금토"[d.getUTCDay()]}요일`;

  Promise.all([
    fetch("data.json", { cache: "no-cache" }).then((r) => r.json()),
    fetch("market/summary.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    fetch("market/settings.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
  ])
    .then(([data, mkt, cfg]) => {
      DATA = data;
      if (mkt) MKT = mkt;
      if (cfg) CFG = { ...CFG, ...cfg, catalog: { ...CFG.catalog, ...(cfg.catalog || {}) } };
      prepGlossary();
      document.getElementById("built").textContent = `업데이트 ${data.built_at}`;
      route();
    })
    .catch(() => { $app.innerHTML = `<p class="pad muted">데이터를 불러오지 못했습니다.</p>`; });

  window.addEventListener("hashchange", () => { document.title = "Deal Archive"; route(); });
})();
