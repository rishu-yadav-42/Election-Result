/* Chart helpers for the dynamic dashboard engine (Chart.js). */

const PALETTE = [
  '#0891b2', '#f59e0b', '#16a34a', '#dc2626', '#7c3aed', '#db2777',
  '#0ea5e9', '#65a30d', '#f97316', '#64748b', '#0f766e', '#a21caf',
  '#eab308', '#2563eb', '#e11d48', '#84cc16',
];

const chartRegistry = {};

/* Compact number formatter (e.g., 1.5K, 2.4L, 10M, or standard en-IN string) */
function formatCompactNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return '0';
  const val = Number(num);
  if (Math.abs(val) >= 10000000) return (val / 10000000).toFixed(1) + ' Cr';
  if (Math.abs(val) >= 100000) return (val / 100000).toFixed(1) + ' Lakh';
  if (Math.abs(val) >= 1000) return (val / 1000).toFixed(1) + 'k';
  return val.toLocaleString('en-IN');
}

/* Party logo markup: parties with an uploaded logo image show the ACTUAL
   image file; parties without one get a coloured initials badge. */
function partyLogoHtml(label, logo, color) {
  if (logo) {
    return `<img class="party-logo" src="${logo}" alt="${label} logo" title="${label}">`;
  }
  const initials = String(label || '?').trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 3).toUpperCase();
  return `<span class="party-logo party-symbol-badge" style="background:${color || '#64748b'}" title="${label}">${initials}</span>`;
}

/* Custom HTML tooltip so chart tooltips can show the actual party logo */
function makeLogoTooltip(logos, suffix = '') {
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
      + lines.map((l) => `<div>${l}${suffix}</div>`).join('') + '</div>';
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
  const suffix = options.suffix || '';

  chartRegistry[canvasId] = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: options.label || '',
        data: values,
        backgroundColor: colors,
        borderRadius: 8,
        borderSkipped: false,
      }],
    },
    options: {
      indexAxis: options.horizontal ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 750,
        easing: 'easeOutQuart',
      },
      onClick: (evt, elements) => {
        if (elements.length && options.onSelect) options.onSelect(elements[0].index);
      },
      onHover: (evt, elements) => {
        evt.native.target.style.cursor = elements.length && options.onSelect ? 'pointer' : 'default';
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ' ' + Number(ctx.raw).toLocaleString('en-IN') + suffix,
          },
          ...(options.logos ? { external: makeLogoTooltip(options.logos, suffix) } : {}),
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            autoSkip: false,
            maxRotation: 60,
            minRotation: labels.length > 6 ? 45 : 0,
            font: { size: 11, weight: '500' },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(211, 233, 240, 0.4)' },
          ticks: {
            callback: (v) => formatCompactNumber(v) + suffix,
            font: { size: 11 },
          },
        },
      },
    },
  });
}

function makeGroupedBarChart(canvasId, labels, datasets, options = {}) {
  if (typeof Chart === 'undefined') return;
  destroyChart(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const formattedDatasets = datasets.map((ds) => ({
    label: ds.label,
    data: ds.data,
    backgroundColor: ds.color,
    borderRadius: 6,
    borderSkipped: false,
  }));

  chartRegistry[canvasId] = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: formattedDatasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 750, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: true, position: 'top', labels: { font: { size: 12, weight: '600' }, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.raw}%`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11, weight: '500' } } },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(211, 233, 240, 0.4)' },
          ticks: { callback: (v) => `${v}%`, font: { size: 11 } },
        },
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
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      animation: { duration: 800, easing: 'easeOutBounce' },
      plugins: {
        legend: {
          position: options.horizontal ? 'bottom' : 'right',
          labels: { boxWidth: 12, font: { size: 11, weight: '600' }, padding: 12 },
        },
        tooltip: {
          callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.raw}%` },
          ...(options.logos ? { external: makeLogoTooltip(options.logos, '%') } : {}),
        },
      },
    },
  });
}

