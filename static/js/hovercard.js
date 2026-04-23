// hovercard.js — floating player card on row hover (shared across pages)

document.addEventListener("DOMContentLoaded", () => {
  const card = document.getElementById("hover-card");
  if (!card) return;

  let hoverTimer = null;

  document.querySelectorAll("tr.player-row").forEach(row => {
    row.addEventListener("mouseenter", e => {
      hoverTimer = setTimeout(() => showHoverCard(row, e), 200);
    });
    row.addEventListener("mouseleave", () => {
      clearTimeout(hoverTimer);
      card.classList.add("d-none");
    });
    row.addEventListener("mousemove", e => {
      positionHoverCard(card, e);
    });
  });
});

function showHoverCard(row, e) {
  const card = document.getElementById("hover-card");
  const name = row.dataset.name;
  const team = row.dataset.team;
  const pos = row.dataset.position;
  const playerId = row.dataset.playerId || row.dataset.goalieId;
  const type = row.dataset.type;

  document.getElementById("hc-name").textContent = name;
  document.getElementById("hc-team-pos").textContent = `${team} · ${pos}`;

  document.getElementById("hc-headshot").src =
    `https://assets.nhle.com/mugs/nhl/20252026/${team}/${playerId}.png`;
  document.getElementById("hc-logo").src =
    `https://assets.nhle.com/logos/nhl/svg/${team}_light.svg`;

  const statsEl = document.getElementById("hc-stats");
  if (type === "goalie") {
    statsEl.innerHTML =
      `<span class="badge bg-light text-dark">${row.dataset.gp} GP</span> ` +
      `<span class="badge bg-dark text-white">${row.dataset.wins}W ${row.dataset.shutouts}SO</span> ` +
      `<span class="badge bg-light text-dark">${row.dataset.gaa} GAA</span> ` +
      `<span class="badge bg-light text-dark">${parseFloat(row.dataset.sv_pct || 0).toFixed(3)} SV%</span>`;
  } else {
    statsEl.innerHTML =
      `<span class="badge bg-light text-dark">${row.dataset.gp} GP</span> ` +
      `<span class="badge bg-light text-dark">${row.dataset.goals}G</span> ` +
      `<span class="badge bg-light text-dark">${row.dataset.assists}A</span> ` +
      `<span class="badge bg-dark text-white">${row.dataset.points} PTS</span>`;
  }

  card.classList.remove("d-none");
  positionHoverCard(card, e);
}

function positionHoverCard(card, e) {
  const offset = 15;
  let x = e.clientX + offset;
  let y = e.clientY + offset;
  if (x + 260 > window.innerWidth)  x = e.clientX - 260 - offset;
  if (y + card.offsetHeight > window.innerHeight) y = e.clientY - card.offsetHeight - offset;
  card.style.left = x + "px";
  card.style.top  = y + "px";
}
