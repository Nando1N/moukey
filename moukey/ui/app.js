// everything shown here comes from the python side (moukey/core.py), nothing is made up

const $ = (sel) => document.querySelector(sel);

const ICONS = {
  desktop:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
  laptop:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/></svg>',
  shield:
    '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>',
};

const SIDE_NAME = { right: "direita", left: "esquerda", top: "de cima", bottom: "de baixo" };

let state = null;
let page = "devices";
let screenPeer = null;

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
  renderFoot();
  renderNotices();
  renderMe();
  renderPeers();
  renderPairing();
  if (page === "screens") renderScreens();
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
  else if (act === "pick-screen") {
    screenPeer = el.dataset.id;
    renderScreens();
  }
});

window.addEventListener("resize", () => {
  if (page === "screens" && state) renderScreens();
});

window.moukey = { render };

window.addEventListener("pywebviewready", async () => {
  const first = await api().state();
  if (first && first.me) render(first);
});
