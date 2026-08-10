/* Chart helpers for the dynamic dashboard engine (Chart.js). */

const PALETTE = [
  '#0891b2', '#f59e0b', '#16a34a', '#dc2626', '#7c3aed', '#db2777',
  '#0ea5e9', '#65a30d', '#f97316', '#64748b', '#0f766e', '#a21caf',
  '#eab308', '#2563eb', '#e11d48', '#84cc16',
];

const chartRegistry = {};

/* Party logo markup: parties with an uploaded logo image show the ACTUAL
   image file; parties without one get a coloured initials badge.
   Logos are never stretched - object-fit: contain keeps aspect ratio. */
function partyLogoHtml(label, logo, color) {
  if (logo) {
    return `<img class="party-logo" src="${logo}" alt="${label} logo" title="${label}">`;
  }
  const initials = String(label || '?').trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 3).toUpperCase();
  return `<span class="party-logo party-symbol-badge" style="background:${color || '#64748b'}" title="${label}">${initials}</span>`;
}

/* Custom HTML tooltip so chart tooltips can show the actual party logo
   (canvas tooltips can only draw text). logos: { partyLabel: logoUrl }. */
function makeLogoTooltip(logos) {
  return (context) => {
    const { chart, tooltip } = context;
    let el = chart.canvas.parentNode.querySelector('.chart-tooltip');
    if (!el) {
      el = document.createElement('div');
      el.className = 'chart-tooltip';
      chart.canvas.parentNode.appendChild(el);
    }
    if (tooltip.opacity === 0) { el.style.opacity = '0'; return; }
    const label = (tooltip.title || [])[0] || '';
    const lines = (tooltip.body || []).map((b) => b.lines.join(' '));
    const logo = logos && logos[label]
      ? `<img class="tt-logo" src="${logos[label]}" alt="">` : '';
    el.innerHTML = `${logo}<div class="tt-text"><strong>${label}</strong>`
      + lines.map((l) => `<div>${l}</div>`).join('') + '</div>';
    el.style.opacity = '1';
    el.style.left = tooltip.caretX + 'px';
    el.style.top = tooltip.caretY + 'px';
  };
}

function destroyChart(canvasId) {
  if (chartRegistry[canvasId]) {
    chartRegistry[canvasId].destroy();
    delete chartRegistry[canvasId];
  }
}

function makeBarChart(canvasId, labels, values, options = {}) {
  if (typeof Chart === 'undefined') return;
  destroyChart(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const colors = options.colors || labels.map((_, i) => PALETTE[i % PALETTE.length]);

  chartRegistry[canvasId] = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: options.label || '',
        data: values,
        backgroundColor: colors,
        borderRadius: 6,
      }],
    },
    options: {
      indexAxis: options.horizontal ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      onClick: (evt, elements) => {
        if (elements.length && options.onSelect) options.onSelect(elements[0].index);
      },
      onHover: (evt, elements) => {
        evt.native.target.style.cursor = elements.length && options.onSelect ? 'pointer' : 'default';
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (ctx) => ' ' + Number(ctx.raw).toLocaleString('en-IN') },
          ...(options.logos ? { external: makeLogoTooltip(options.logos) } : {}),
        },
      },
      scales: {
        x: { ticks: { autoSkip: false, maxRotation: 60, minRotation: labels.length > 6 ? 45 : 0 } },
        y: { beginAtZero: true, ticks: { callback: (v) => Number(v).toLocaleString('en-IN') } },
      },
    },
  });
}

function makeDoughnutChart(canvasId, labels, values, options = {}) {
  if (typeof Chart === 'undefined') return;
  destroyChart(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const colors = options.colors || labels.map((_, i) => PALETTE[i % PALETTE.length]);

  chartRegistry[canvasId] = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: '#ffffff',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '58%',
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 14, font: { size: 11 } } },
        tooltip: {
          callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.raw}%` },
          ...(options.logos ? { external: makeLogoTooltip(options.logos) } : {}),
        },
      },
    },
  });
}
