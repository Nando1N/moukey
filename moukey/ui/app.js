// everything shown here comes from the python side (moukey/core.py), nothing is made up

const $ = (sel) => document.querySelector(sel);

const ICONS = {
  desktop:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
  laptop:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/></svg>',
  text:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 6h14M5 12h14M5 18h9"/></svg>',
  check:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
  shield:
    '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>',
};

const SIDE_NAME = { right: "direita", left: "esquerda", top: "de cima", bottom: "de baixo" };

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
      '<div class="notice error">O MouKey parece já estar aberto neste computador. Feche a outra janela e abra de novo.</div>',
    );
  }
  if (state.error) {
    parts.push(`<div class="notice error">${esc(state.error)}</div>`);
  }
  $("#notices").innerHTML = parts.join("");
}

function linkText(link) {
  if (link.role === "controlling") {
    return link.away
      ? `Controlando ${esc(link.name)} · o mouse está lá agora`
      : `Controlando ${esc(link.name)} · o mouse está aqui`;
  }
  return `Sendo controlado por ${esc(link.name)}`;
}

function renderMe() {
  const me = state.me;
  const link = state.link;
  const badge = link
    ? `<span class="tag purple">${link.role === "controlling" ? "Controlando" : "Controlado"}</span>`
    : '<span class="tag">Pronto</span>';
  const meta = link ? linkText(link) : esc(me.os);
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

function renderPeers() {
  if (!state.peers.length) {
    $("#peers").innerHTML = `
      <div class="empty">
        <strong><span class="spinner"></span>&nbsp; Procurando computadores...</strong>
        Abra o MouKey no outro computador. Os dois precisam estar na mesma rede.<br />
        Se o Windows perguntar sobre o firewall, clique em Permitir.
      </div>`;
    return;
  }
  $("#peers").innerHTML = state.peers
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
    text = `<b>${esc(pairing.who)}</b> quer controlar este computador com o mouse e o teclado dele. Confira se o mesmo código aparece lá.`;
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

// screens: our screen in the middle, the other one snaps to the side it was dropped on
const SPOTS = { right: [1, 0], left: [-1, 0], top: [0, -1], bottom: [0, 1] };

function sideFromOffset(dx, dy) {
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "right" : "left";
  return dy >= 0 ? "bottom" : "top";
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

  const peer = peers.find((p) => p.id === screenPeer);
  if (document.querySelector(".screen.dragging")) return;
  const note = peer.linked
    ? "Se mudar o lado agora, vale na próxima conexão."
    : `Hoje o mouse passa pela borda ${SIDE_NAME[peer.side]} da tela.`;
  $("#screens-body").innerHTML = `
    <div class="stage" id="stage">
      <div class="screen me"><div><b>1</b>${esc(state.me.name)}</div></div>
      <div class="screen other" id="other"><div><b>2</b>${esc(peer.name)}</div></div>
    </div>
    <p class="hint">${note} Por enquanto cada computador conta só com o monitor principal.</p>`;
  placeScreens(peer.side);
  dragScreen(peer);
}

function placeScreens(side) {
  const stage = $("#stage");
  const me = stage.querySelector(".me");
  const other = $("#other");
  const cx = (stage.clientWidth - me.offsetWidth) / 2;
  const cy = (stage.clientHeight - me.offsetHeight) / 2;
  me.style.left = `${cx}px`;
  me.style.top = `${cy}px`;
  const [sx, sy] = SPOTS[side];
  other.style.left = `${cx + sx * (me.offsetWidth + 8)}px`;
  other.style.top = `${cy + sy * (me.offsetHeight + 8)}px`;
}

function dragScreen(peer) {
  const other = $("#other");
  const stage = $("#stage");
  other.addEventListener("pointerdown", (ev) => {
    other.setPointerCapture(ev.pointerId);
    other.classList.add("dragging");
    const startX = ev.clientX - other.offsetLeft;
    const startY = ev.clientY - other.offsetTop;
    const move = (e) => {
      other.style.left = `${e.clientX - startX}px`;
      other.style.top = `${e.clientY - startY}px`;
    };
    const up = () => {
      other.removeEventListener("pointermove", move);
      other.classList.remove("dragging");
      const centerX = other.offsetLeft + other.offsetWidth / 2 - stage.clientWidth / 2;
      const centerY = other.offsetTop + other.offsetHeight / 2 - stage.clientHeight / 2;
      const side = sideFromOffset(centerX, centerY);
      placeScreens(side);
      peer.side = side;
      api().set_side(peer.id, side);
    };
    other.addEventListener("pointermove", move);
    other.addEventListener("pointerup", up, { once: true });
  });
}

const WELCOME = [
  {
    icon: ICONS.desktop,
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
        <img src="img/logo.png" alt="MouKey" />
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
  else if (act === "welcome-next") {
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
