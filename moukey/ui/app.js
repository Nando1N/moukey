// everything shown here comes from the python side (moukey/core.py), nothing is made up

const $ = (sel) => document.querySelector(sel);

const ICONS = {
  desktop:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
  laptop:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/></svg>',
  upload:
    '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3M12 15V4M7 9l5-5 5 5"/></svg>',
  file:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>',
  text:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 6h14M5 12h14M5 18h9"/></svg>',
  check:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
  shield:
    '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>',
};

let state = null;
let page = "devices";
let screenPeer = null;
let welcomeStep = 0;
let version = "";

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function api() {
  return window.pywebview && window.pywebview.api;
}

function render(next) {
  state = next;
  $("#splash").classList.add("gone");
  renderWelcome();
  renderFoot();
  renderNotices();
  renderMe();
  renderPeers();
  renderPairing();
  if (page === "screens") renderScreens();
  if (page === "settings") renderSettings();
  if (page === "clips") renderClips();
  if (page === "files") renderFiles();
}

function renderFoot() {
  const link = state.link;
  let html;
  if (link) {
    html = `<span class="dot green"></span>Conectado com ${esc(link.name)}`;
  } else if (state.dialing) {
    html = '<span class="dot amber pulse"></span>Conectando...';
  } else if (state.peers.length) {
    html = '<span class="dot"></span>Não conectado';
  } else {
    html = '<span class="dot amber pulse"></span>Procurando...';
  }
  $("#foot").innerHTML = html;
}

function renderNotices() {
  const parts = [];
  if (!state.server_ok) {
    parts.push(
      '<div class="notice error">Outro programa está usando a conexão do MouKey neste computador, provavelmente uma janela antiga do MouKey ou do Ponte. Feche pelo Gerenciador de Tarefas (Ctrl+Shift+Esc) e abra o MouKey de novo.</div>',
    );
  }
  if (state.error) {
    parts.push(`<div class="notice error">${esc(state.error)}</div>`);
  }
  if (state.link && state.version_warning) {
    parts.push(
      '<div class="notice">Os dois computadores estão com versões diferentes do MouKey. Se algo não funcionar, baixe a versão mais nova nos dois.</div>',
    );
  }
  $("#notices").innerHTML = parts.join("");
}

function linkText(link) {
  if (link.away) return `Conectado com ${esc(link.name)} · o seu mouse está lá agora`;
  if (link.guest) return `Conectado com ${esc(link.name)} · o mouse de lá está aqui agora`;
  return `Conectado com ${esc(link.name)} · leve o mouse até a borda da tela`;
}

function renderMe() {
  const me = state.me;
  const link = state.link;
  const badge = link ? '<span class="tag purple">Conectado</span>' : '<span class="tag">Pronto</span>';
  const meta = link ? linkText(link) : `${esc(me.os)} · IP ${esc(me.ip)}`;
  $("#me").innerHTML = `
    <div class="row">
      <div class="ico">${ICONS.desktop}</div>
      <div class="info">
        <div class="name">${esc(me.name)}<small>este computador</small></div>
        <div class="meta">${meta}</div>
      </div>
      ${badge}
    </div>`;
}

function peerButton(peer) {
  if (peer.linked) {
    return '<button class="btn" data-act="disconnect">Desconectar</button>';
  }
  if (state.dialing && !state.link) {
    return '<span class="tag"><span class="spinner"></span> Conectando</span>';
  }
  const disabled = state.busy ? "disabled" : "";
  return `<button class="btn primary" data-act="connect" data-id="${esc(peer.id)}" ${disabled}>Conectar</button>`;
}

let ipOpen = false;
let ipError = "";

function ipForm() {
  if (!ipOpen) {
    return '<button class="link-btn" data-act="show-ip">O outro computador não aparece? Conectar pelo IP</button>';
  }
  return `
    <div class="ip-form">
      <input id="ip" placeholder="Ex.: 192.168.0.10" spellcheck="false" />
      <button class="btn primary" data-act="connect-ip">Conectar</button>
    </div>
    <div class="hint">O IP de cada computador aparece na tela Dispositivos do MouKey dele, ao lado do nome.</div>
    ${ipError ? `<div class="notice error" style="margin-top: 8px">${esc(ipError)}</div>` : ""}`;
}

function renderPeers() {
  const typed = $("#ip") ? $("#ip").value : "";
  let html;
  if (!state.peers.length) {
    html = `
      <div class="empty">
        <strong><span class="spinner"></span>&nbsp; Procurando computadores...</strong>
        Abra o MouKey no outro computador. Os dois precisam estar na mesma rede.<br />
        Se o Windows perguntar sobre o firewall, clique em Permitir.
      </div>`;
  } else {
    html = state.peers
      .map((peer) => {
        const status = peer.linked
          ? '<span class="dot green"></span>Conectado'
          : '<span class="dot"></span>Disponível';
        const os = peer.os ? `${esc(peer.os)} · ` : "";
        const remembered = peer.remembered && !peer.linked ? '<span class="tag">Reconecta sozinho</span>' : "";
        return `
          <div class="row ${peer.linked ? "linked" : ""}">
            <div class="ico">${ICONS.laptop}</div>
            <div class="info">
              <div class="name">${esc(peer.name)}</div>
              <div class="meta">${os}${status}</div>
            </div>
            ${remembered}
            ${peerButton(peer)}
          </div>`;
      })
      .join("");
  }
  $("#peers").innerHTML = html + (state.link ? "" : `<div style="margin-top: 12px">${ipForm()}</div>`);
  if ($("#ip")) $("#ip").value = typed;
}

function renderPairing() {
  const box = $("#pairing");
  const pairing = state.pairing;
  if (!pairing) {
    box.classList.add("hidden");
    return;
  }
  const digits = pairing.code
    .split("")
    .map((d) => `<span>${esc(d)}</span>`)
    .join("");
  let text, actions;
  if (pairing.asking) {
    text = `<b>${esc(pairing.who)}</b> quer se conectar com este computador. Confira se o mesmo código aparece lá.`;
    actions = `
      <button class="btn primary" data-act="accept">Confirmar e parear</button>
      <button class="btn" data-act="refuse">Recusar</button>`;
  } else {
    text = "Confira se este mesmo código aparece no outro computador e confirme por lá.";
    actions = '<button class="btn" data-act="disconnect">Cancelar</button>';
  }
  box.innerHTML = `
    <div class="dialog">
      <div class="shield">${ICONS.shield}</div>
      <h3>${pairing.asking ? "Confirmar conexão" : "Pareamento"}</h3>
      <p>${text}</p>
      <div class="code">${digits}</div>
      <div class="actions">${actions}</div>
    </div>`;
  box.classList.remove("hidden");
}

// screens: every monitor of both computers, drawn at their real size and position.
// ours stay put (windows decides where they are), the other computer's group can be dragged
function ratio(w, h) {
  const r = w / h;
  const known = [
    [2.37, "21:9"],
    [1.78, "16:9"],
    [1.6, "16:10"],
    [1.5, "3:2"],
    [1.33, "4:3"],
  ];
  const hit = known.find(([v]) => Math.abs(r - v) < 0.04);
  return hit ? hit[1] : r.toFixed(2);
}

function screenBox(rect, n, owner, main) {
  const [, , w, h] = rect;
  return `<div class="mon"><div><b>${n}</b><span>${esc(owner)}${main ? " · principal" : ""}</span><span>${w} × ${h} · ${ratio(w, h)}</span></div></div>`;
}

function renderScreens() {
  const peers = state.peers;
  if (!peers.length) {
    $("#screen-tabs").innerHTML = "";
    $("#screens-body").innerHTML =
      '<div class="empty"><strong>Nenhum outro computador ainda</strong>Assim que o MouKey achar outro computador na rede, ele aparece aqui.</div>';
    return;
  }
  if (!peers.some((p) => p.id === screenPeer)) {
    const linked = peers.find((p) => p.linked);
    screenPeer = (linked || peers[0]).id;
  }
  $("#screen-tabs").innerHTML =
    peers.length > 1
      ? peers
          .map(
            (p) =>
              `<button class="btn ${p.id === screenPeer ? "on" : ""}" data-act="pick-screen" data-id="${esc(p.id)}">${esc(p.name)}</button>`,
          )
          .join("")
      : "";
  if (document.querySelector(".group.dragging")) return;

  const peer = peers.find((p) => p.id === screenPeer);
  const layout = state.layouts[peer.id];
  const mine = state.me.screens;
  const [ox, oy] = layout.offset;
  const theirs = layout.screens.map(([x, y, w, h]) => [x + ox, y + oy, w, h]);
  const all = mine.concat(theirs);
  const left = Math.min(...all.map((r) => r[0]));
  const top = Math.min(...all.map((r) => r[1]));
  const right = Math.max(...all.map((r) => r[0] + r[2]));
  const bottom = Math.max(...all.map((r) => r[1] + r[3]));

  $("#screens-body").innerHTML = `
    <div class="stage" id="stage"></div>
    <p class="hint">
      As telas roxas são deste computador e ficam onde o Windows colocou. Arraste as do ${esc(peer.name)}
      para onde ele fica na mesa. O mouse passa onde as telas se encostam.
      ${layout.known ? "" : "<br />O tamanho real das telas dele aparece depois da primeira conexão."}
      ${peer.linked ? "<br />Mudanças valem na hora." : ""}
    </p>`;

  const stage = $("#stage");
  // leave room around everything so there's space to drag
  const pad = Math.max(right - left, bottom - top) * 0.18;
  const worldW = right - left + pad * 2;
  const worldH = bottom - top + pad * 2;
  const scale = Math.min(stage.clientWidth / worldW, stage.clientHeight / worldH);
  const originX = left - pad - (stage.clientWidth / scale - worldW) / 2;
  const originY = top - pad - (stage.clientHeight / scale - worldH) / 2;
  const px = (v, o) => (v - o) * scale;

  let html = "";
  mine.forEach((r, i) => {
    html += `<div class="screen me" style="left:${px(r[0], originX)}px;top:${px(r[1], originY)}px;width:${r[2] * scale}px;height:${r[3] * scale}px">${screenBox(r, i + 1, state.me.name, i === 0)}</div>`;
  });
  const gLeft = Math.min(...theirs.map((r) => r[0]));
  const gTop = Math.min(...theirs.map((r) => r[1]));
  const gRight = Math.max(...theirs.map((r) => r[0] + r[2]));
  const gBottom = Math.max(...theirs.map((r) => r[1] + r[3]));
  html += `<div class="group" id="group" style="left:${px(gLeft, originX)}px;top:${px(gTop, originY)}px;width:${(gRight - gLeft) * scale}px;height:${(gBottom - gTop) * scale}px">`;
  theirs.forEach((r, i) => {
    html += `<div class="screen other" style="left:${(r[0] - gLeft) * scale}px;top:${(r[1] - gTop) * scale}px;width:${r[2] * scale}px;height:${r[3] * scale}px">${screenBox(r, mine.length + i + 1, peer.name, i === 0)}</div>`;
  });
  html += "</div>";
  stage.innerHTML = html;

  const group = $("#group");
  group.addEventListener("pointerdown", (ev) => {
    group.setPointerCapture(ev.pointerId);
    group.classList.add("dragging");
    const startX = ev.clientX - group.offsetLeft;
    const startY = ev.clientY - group.offsetTop;
    const move = (e) => {
      group.style.left = `${e.clientX - startX}px`;
      group.style.top = `${e.clientY - startY}px`;
    };
    const up = () => {
      group.removeEventListener("pointermove", move);
      group.classList.remove("dragging");
      // back to real pixels: where the group's corner landed, minus where it is on their side
      const worldX = group.offsetLeft / scale + originX;
      const worldY = group.offsetTop / scale + originY;
      const baseX = Math.min(...layout.screens.map((r) => r[0]));
      const baseY = Math.min(...layout.screens.map((r) => r[1]));
      api().set_offset(peer.id, Math.round(worldX - baseX), Math.round(worldY - baseY));
    };
    group.addEventListener("pointermove", move);
    group.addEventListener("pointerup", up, { once: true });
  });
}

const WELCOME = [
  {
    icon: '<img src="img/icone.svg" alt="" style="width: 44px" />',
    title: "Bem-vindo ao MouKey",
    body: "Use um mouse e um teclado em vários computadores, como se fossem uma mesa só. É só levar o cursor até a borda da tela.",
  },
  {
    icon: ICONS.laptop,
    title: "O que dá para fazer",
    feats: [
      ["Controle compartilhado", "O mouse e o teclado passam de um computador para o outro pela borda."],
      ["Área de transferência", "Copie um texto em um e cole no outro."],
      ["Conexão segura", "Tudo criptografado e só com o computador que você confirmar."],
    ],
  },
  {
    icon: ICONS.shield,
    title: "Pronto para começar",
    body: "O MouKey procura sozinho os outros computadores da sua rede. Abra ele no outro computador também e clique em Conectar no que tem o mouse.",
  },
];

function renderWelcome() {
  const box = $("#welcome");
  if (state.options.onboarded) {
    box.classList.add("hidden");
    return;
  }
  const step = WELCOME[welcomeStep];
  const feats = (step.feats || [])
    .map(([t, d]) => `<div class="feat">${ICONS.check}<div><b>${t}</b><span>${d}</span></div></div>`)
    .join("");
  const last = welcomeStep === WELCOME.length - 1;
  const dots = WELCOME.map((_, i) => `<i class="${i === welcomeStep ? "on" : ""}"></i>`).join("");
  const back =
    welcomeStep > 0
      ? '<button class="btn" data-act="welcome-back">Voltar</button>'
      : '<button class="btn" data-act="welcome-done">Pular</button>';
  box.innerHTML = `
    <div class="welcome">
      <div class="icon">${step.icon}</div>
      <h3>${step.title}</h3>
      ${step.body ? `<p>${step.body}</p>` : ""}
      ${feats}
      <div class="foot">
        <div class="steps">${dots}</div>
        <div>
          ${back}
          <button class="btn primary" data-act="${last ? "welcome-done" : "welcome-next"}">${last ? "Começar a usar" : "Próximo"}</button>
        </div>
      </div>
    </div>`;
  box.classList.remove("hidden");
}

function size(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function renderFiles() {
  const link = state.link;
  $("#drop").innerHTML = link
    ? `<div class="drop" id="dropzone">
        ${ICONS.upload}
        <div><strong style="color: var(--text)">Arraste arquivos para cá</strong><br />ou escolha para mandar para ${esc(link.name)}</div>
        <button class="btn primary" data-act="choose-files">Escolher arquivos</button>
      </div>`
    : `<div class="drop off">
        ${ICONS.upload}
        <div>Conecte os dois computadores em Dispositivos para mandar arquivos.</div>
      </div>`;

  const list = state.transfers;
  $("#clear-transfers").disabled = !list.some((t) => t.status !== "active");
  if (!list.length) {
    $("#transfers").innerHTML = '<div class="empty">Nenhuma transferência ainda.</div>';
    return;
  }
  $("#transfers").innerHTML = list
    .map((t) => {
      const where = t.incoming ? `Recebido de ${esc(t.peer)}` : `Enviado para ${esc(t.peer)}`;
      const pct = t.size ? Math.floor((t.done / t.size) * 100) : 100;
      let right;
      let detail = `${where} · ${size(t.size)}`;
      if (t.status === "active") {
        detail += ` · ${pct}%${t.speed ? ` · ${size(t.speed)}/s` : ""}`;
        right = `<button class="btn" data-act="cancel-transfer" data-id="${esc(t.id)}">Cancelar</button>`;
      } else if (t.status === "done") {
        right = '<span class="tag green">Concluído</span>';
      } else if (t.status === "canceled") {
        right = '<span class="tag">Cancelado</span>';
      } else {
        right = `<span class="tag red">${esc(t.error || "Erro")}</span>`;
      }
      const bar = t.status === "active" ? `<div class="progress"><span style="width: ${pct}%"></span></div>` : "";
      return `
        <div class="row">
          <div class="ico">${ICONS.file}</div>
          <div class="info">
            <div class="name">${esc(t.name)}</div>
            <div class="meta">${detail}</div>
            ${bar}
          </div>
          ${right}
        </div>`;
    })
    .join("");
}

// highlight the drop area while something is dragged over the window
document.addEventListener("dragover", (ev) => {
  ev.preventDefault();
  const zone = $("#dropzone");
  if (zone) zone.classList.add("over");
});
document.addEventListener("dragleave", () => {
  const zone = $("#dropzone");
  if (zone) zone.classList.remove("over");
});
document.addEventListener("drop", (ev) => {
  ev.preventDefault();
  const zone = $("#dropzone");
  if (zone) zone.classList.remove("over");
});

function renderClips() {
  const clips = state.clips;
  $("#clear-clips").disabled = !clips.length;
  if (!clips.length) {
    $("#clips").innerHTML = `
      <div class="empty">
        <strong>Nada copiado ainda</strong>
        Conecte os dois computadores e copie um texto em qualquer um deles. Ele aparece aqui e já fica pronto para colar no outro.
      </div>`;
    return;
  }
  $("#clips").innerHTML = clips
    .map((c) => {
      const more = c.size > c.preview.length ? "…" : "";
      return `
        <div class="row clip">
          <div class="ico">${ICONS.text}</div>
          <div class="info">
            <div class="meta">${esc(c.origin)} · ${esc(c.time)} · ${c.size} caracteres</div>
            <div class="text">${esc(c.preview)}${more}</div>
          </div>
          <button class="btn" data-act="copy-clip" data-id="${c.id}">Copiar</button>
        </div>`;
    })
    .join("");
}

function toggle(name, on, disabled = false) {
  return `<button class="switch ${on ? "on" : ""}" data-act="toggle" data-name="${name}" ${disabled ? "disabled" : ""} aria-pressed="${on}"></button>`;
}

function option(title, desc, control) {
  return `
    <div class="opt">
      <div class="info"><div class="title">${title}</div><div class="desc">${desc}</div></div>
      ${control}
    </div>`;
}

function renderSettings() {
  const o = state.options;
  const auto = state.autostart;
  const always = '<span class="tag green">Sempre ligado</span>';
  const autoDesc = auto.available
    ? "Abre o MouKey quando você entra no Windows."
    : "Disponível só no MouKey.exe.";
  const paired = state.paired.length
    ? state.paired
        .map((p) =>
          option(
            esc(p.name),
            "Conecta sem pedir código",
            `<button class="btn" data-act="forget" data-key="${esc(p.key)}">Esquecer</button>`,
          ),
        )
        .join("")
    : '<div class="opt"><div class="info"><div class="desc">Nenhum computador pareado ainda.</div></div></div>';

  $("#settings-body").innerHTML = `
    <div class="group">
      <h3>Geral</h3>
      ${option("Reconectar automaticamente", "Volta a conectar sozinho no último computador que você controlou.", toggle("auto_reconnect", o.auto_reconnect))}
      ${option("Iniciar com o Windows", autoDesc, toggle("autostart", auto.on, !auto.available))}
      ${option("Boas-vindas", "Mostra de novo as telas do primeiro acesso.", '<button class="btn" data-act="welcome-again">Mostrar</button>')}
    </div>

    <div class="group">
      <h3>Segurança</h3>
      ${option("Criptografia de ponta a ponta", "Tudo que passa entre os computadores é criptografado (X25519 e ChaCha20-Poly1305).", always)}
      ${option("Pareamento com código", "Um computador novo só conecta depois que você confirma o mesmo código nos dois.", always)}
      ${option("Só rede local", "Conexões vindas de fora da sua rede são recusadas.", always)}
      ${option("Nada do que você digita é gravado", "O MouKey não guarda teclas em arquivo nem em registro.", always)}
    </div>

    <div class="group">
      <h3>Computadores pareados</h3>
      ${paired}
    </div>

    <div class="group">
      <h3>Atalhos</h3>
      ${option("Emergência", "Devolve o mouse e o teclado para este computador na hora.", "<span><kbd>Ctrl</kbd> <kbd>Alt</kbd> <kbd>Shift</kbd> <kbd>Esc</kbd></span>")}
    </div>

    <div class="group">
      <h3>Sobre</h3>
      <div class="about">
        <img src="img/logo.svg" alt="MouKey" />
        <div class="desc">
          Versão ${esc(version)} · Licença MIT<br />
          Código aberto em <span class="link" data-act="link" data-url="https://github.com/Nando1N/moukey">github.com/Nando1N/moukey</span><br />
          Fonte <span class="link" data-act="link" data-url="https://rsms.me/inter/">Inter</span>, licença SIL OFL
        </div>
      </div>
    </div>`;
}

function show(name) {
  page = name;
  document.querySelectorAll(".nav button").forEach((b) => b.classList.toggle("on", b.dataset.page === name));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("hidden", p.id !== `page-${name}`));
  if (state) render(state);
}

document.addEventListener("click", (ev) => {
  const nav = ev.target.closest(".nav button");
  if (nav) return show(nav.dataset.page);

  const el = ev.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const act = el.dataset.act;
  if (act === "connect") api().connect(el.dataset.id);
  else if (act === "disconnect") api().disconnect();
  else if (act === "accept") api().answer(true);
  else if (act === "refuse") api().answer(false);
  else if (act === "show-ip") {
    ipOpen = true;
    renderPeers();
    $("#ip").focus();
  } else if (act === "connect-ip") {
    api()
      .connect_ip($("#ip").value)
      .then((err) => {
        ipError = err || "";
        if (!err) ipOpen = false;
        renderPeers();
      });
  } else if (act === "welcome-next") {
    welcomeStep += 1;
    renderWelcome();
  } else if (act === "welcome-back") {
    welcomeStep -= 1;
    renderWelcome();
  } else if (act === "welcome-done") {
    welcomeStep = 0;
    api().set_option("onboarded", true);
  } else if (act === "welcome-again") {
    api().set_option("onboarded", false);
  } else if (act === "toggle") {
    const on = !el.classList.contains("on");
    if (el.dataset.name === "autostart") api().set_autostart(on);
    else api().set_option(el.dataset.name, on);
  } else if (act === "choose-files") {
    api().choose_files();
  } else if (act === "cancel-transfer") {
    api().cancel_transfer(el.dataset.id);
  } else if (act === "clear-transfers") {
    api().clear_transfers();
  } else if (act === "open-downloads") {
    api().open_downloads();
  } else if (act === "copy-clip") {
    api().copy_clip(Number(el.dataset.id));
    el.textContent = "Copiado";
    setTimeout(() => (el.textContent = "Copiar"), 1200);
  } else if (act === "clear-clips") {
    api().clear_clips();
  } else if (act === "forget") {
    api().forget(el.dataset.key);
  } else if (act === "link") {
    api().open_link(el.dataset.url);
  } else if (act === "pick-screen") {
    screenPeer = el.dataset.id;
    renderScreens();
  }
});

window.addEventListener("resize", () => {
  if (page === "screens" && state) renderScreens();
});

window.moukey = { render };

window.addEventListener("pywebviewready", async () => {
  version = await api().version();
  const first = await api().state();
  if (first && first.me) render(first);
});
