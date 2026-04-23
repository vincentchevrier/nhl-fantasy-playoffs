// draft.js — handles picks state, hover card, sorting, and submission

const picks = {};  // { "F3": {id, type, name, team}, ... }
const TOTAL_POOLS = 22;

// ─── Init ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  // Pre-populate from server-side existing picks
  if (typeof existingPicks !== "undefined") {
    document.querySelectorAll(".pool-radio:checked").forEach(radio => {
      const pool = radio.dataset.pool;
      picks[pool] = {
        id: parseInt(radio.dataset.id),
        type: radio.dataset.type,
        name: radio.dataset.name,
        team: radio.dataset.team,
      };
      updatePoolBadge(pool, radio.dataset.name);
    });
  }

  updateCounter();
  setupRadios();
  setupSorting();

  document.getElementById("team-name")?.addEventListener("input", updateSubmit);
});

// ─── Radio picks ────────────────────────────────────────────────────────────

function setupRadios() {
  document.querySelectorAll(".pool-radio").forEach(radio => {
    radio.addEventListener("change", () => {
      const pool = radio.dataset.pool;
      picks[pool] = {
        id: parseInt(radio.dataset.id),
        type: radio.dataset.type,
        name: radio.dataset.name,
        team: radio.dataset.team,
      };
      updatePoolBadge(pool, radio.dataset.name);
      updateCounter();
      updateSubmit();
    });
  });
}

function updatePoolBadge(pool, name) {
  const badge = document.getElementById(`selected-${pool}`);
  if (badge) {
    badge.textContent = name;
    badge.classList.remove("bg-secondary");
    badge.classList.add("bg-success");
  }
}

function updateCounter() {
  const count = Object.keys(picks).length;
  const counter = document.getElementById("pick-counter");
  const progress = document.getElementById("pick-progress");
  if (counter) counter.textContent = `${count} / ${TOTAL_POOLS} picks`;
  if (progress) progress.style.width = `${(count / TOTAL_POOLS) * 100}%`;
}

function updateSubmit() {
  const btn = document.getElementById("submit-btn");
  const hint = document.getElementById("submit-hint");
  if (!btn) return;

  const count = Object.keys(picks).length;
  const teamName = document.getElementById("team-name")?.value?.trim();
  const ready = count === TOTAL_POOLS && teamName;

  btn.disabled = !ready;
  if (hint) {
    if (!teamName) {
      hint.textContent = "Enter a team name.";
    } else if (count < TOTAL_POOLS) {
      hint.textContent = `${TOTAL_POOLS - count} more pick(s) needed.`;
    } else {
      hint.textContent = "Ready to submit!";
    }
  }
}

// ─── Submit ─────────────────────────────────────────────────────────────────

document.getElementById("submit-btn")?.addEventListener("click", async () => {
  const teamName = document.getElementById("team-name").value.trim();
  const picksArray = Object.entries(picks).map(([pool, pick]) => {
    const entry = { pool };
    if (pick.type === "goalie") {
      entry.goalie_id = pick.id;
    } else {
      entry.player_id = pick.id;
    }
    return entry;
  });

  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Submitting...';

  try {
    const resp = await fetch("/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ team_name: teamName, picks: picksArray }),
    });
    const data = await resp.json();

    if (data.success) {
      window.location.href = `/teams/${data.team_id}`;
    } else {
      alert("Error: " + (data.error || "Unknown error"));
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-check2-circle me-2"></i>Submit Team';
    }
  } catch (e) {
    alert("Network error. Please try again.");
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-check2-circle me-2"></i>Submit Team';
  }
});

// ─── Sorting ─────────────────────────────────────────────────────────────────

function setupSorting() {
  document.querySelectorAll(".sortable-table").forEach(table => {
    const state = { col: "rank", asc: true };

    table.querySelectorAll("th.sortable").forEach(th => {
      th.style.cursor = "pointer";
      th.addEventListener("click", () => {
        const col = th.dataset.col;
        if (state.col === col) {
          state.asc = !state.asc;
        } else {
          state.col = col;
          state.asc = col === "rank";  // rank defaults asc, others desc
        }
        sortTable(table, state.col, state.asc);
        // Update sort indicators
        table.querySelectorAll("th.sortable").forEach(h => h.classList.remove("sort-asc", "sort-desc"));
        th.classList.add(state.asc ? "sort-asc" : "sort-desc");
      });
    });
  });
}

function sortTable(table, col, asc) {
  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.querySelectorAll("tr.player-row"));

  rows.sort((a, b) => {
    let av = a.dataset[col] || a.dataset[col.replace("_", "")] || "0";
    let bv = b.dataset[col] || b.dataset[col.replace("_", "")] || "0";

    // Try numeric
    const an = parseFloat(av);
    const bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) {
      return asc ? an - bn : bn - an;
    }
    // String
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });

  rows.forEach(r => tbody.appendChild(r));
}


