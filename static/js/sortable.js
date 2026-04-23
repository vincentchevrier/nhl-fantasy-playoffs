/**
 * sortable.js — generic click-to-sort for any table.
 *
 * Markup:
 *   <table class="js-sortable">
 *     <thead>
 *       <tr>
 *         <th data-sort="num">Points</th>   ← numeric sort
 *         <th data-sort="str">Name</th>     ← string sort
 *         <th>                              ← no data-sort = not sortable
 *       </tr>
 *     </thead>
 *     <tbody>
 *       <tr>
 *         <td data-val="42">42 pts</td>     ← data-val overrides text for sort key
 *         <td>Connor McDavid</td>
 *       </tr>
 *     </tbody>
 *   </table>
 *
 * CSS classes applied to <th>: sort-asc / sort-desc
 */

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("table.js-sortable").forEach(initSortable);
});

function initSortable(table) {
  // Track per-table sort state
  const state = { th: null, asc: true };

  // Use actual column position, not index within the sortable-only subset.
  const allThs = Array.from(table.querySelectorAll("thead tr th"));

  table.querySelectorAll("thead th[data-sort]").forEach((th) => {
    const colIdx = allThs.indexOf(th);
    th.style.cursor = "pointer";
    th.title = "Click to sort";

    th.addEventListener("click", () => {
      const type = th.dataset.sort;

      // Toggle direction if same column, otherwise default: num→desc, str→asc
      if (state.th === th) {
        state.asc = !state.asc;
      } else {
        state.asc = (type === "str" || type === "natural");
        if (state.th) state.th.classList.remove("sort-asc", "sort-desc");
        state.th = th;
      }

      th.classList.toggle("sort-asc", state.asc);
      th.classList.toggle("sort-desc", !state.asc);

      sortTable(table, colIdx, type, state.asc);
    });

    // Apply default sort if specified
    if (th.dataset.sortDefault) {
      const asc = th.dataset.sortDefault === "asc";
      state.asc = asc;
      state.th = th;
      th.classList.toggle("sort-asc", asc);
      th.classList.toggle("sort-desc", !asc);
      sortTable(table, colIdx, th.dataset.sort, asc);
    }
  });
}

function naturalCompare(a, b) {
  // Split into alternating non-digit / digit segments, compare each part.
  // "F9" < "F10" < "F12" because 9 < 10 < 12 numerically.
  const re = /(\d+)|(\D+)/g;
  const aParts = a.match(re) || [];
  const bParts = b.match(re) || [];
  for (let i = 0; i < Math.max(aParts.length, bParts.length); i++) {
    if (i >= aParts.length) return -1;
    if (i >= bParts.length) return 1;
    const aIsNum = /^\d+$/.test(aParts[i]);
    const bIsNum = /^\d+$/.test(bParts[i]);
    if (aIsNum && bIsNum) {
      const diff = parseInt(aParts[i], 10) - parseInt(bParts[i], 10);
      if (diff !== 0) return diff;
    } else {
      const diff = aParts[i].localeCompare(bParts[i], undefined, { sensitivity: "base" });
      if (diff !== 0) return diff;
    }
  }
  return 0;
}

function sortTable(table, colIdx, type, asc) {
  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.querySelectorAll("tr"));

  rows.sort((a, b) => {
    const aCell = a.querySelectorAll("td")[colIdx];
    const bCell = b.querySelectorAll("td")[colIdx];
    if (!aCell || !bCell) return 0;

    // Prefer explicit data-val, fall back to trimmed text content
    const aRaw = aCell.dataset.val ?? aCell.textContent.trim();
    const bRaw = bCell.dataset.val ?? bCell.textContent.trim();

    let cmp;
    if (type === "num") {
      cmp = (parseFloat(aRaw) || 0) - (parseFloat(bRaw) || 0);
    } else if (type === "natural") {
      cmp = naturalCompare(aRaw, bRaw);
    } else {
      cmp = aRaw.localeCompare(bRaw, undefined, { sensitivity: "base" });
    }

    return asc ? cmp : -cmp;
  });

  rows.forEach(r => tbody.appendChild(r));
}
