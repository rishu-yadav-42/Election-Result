/* Dynamic dashboard renderer.
   ONE dashboard template serves every election - all content comes from
   /api/dashboard, which is built from Admin-uploaded data only. */

const Dashboard = (() => {
  const root = document.getElementById('dashboard-root');
  const electionId = root ? root.dataset.electionId : null;
  const electionType = root ? root.dataset.electionType : null;

  let filters = { code: '', name: '', party: '' };
  let lastResults = [];
  let partyColors = {};
  let partyLogos = {};

  const fmt = (n) => Number(n || 0).toLocaleString('en-IN');

  function setFilters(next) {
    filters = next;
  }

  /* Cross-filtering: clicking a party (card or chart) filters every visual to it. */
  function applyPartyFilter(party) {
    document.getElementById('filterParty').value = party;
    document.getElementById('filterCode').value = '';
    document.getElementById('filterName').value = '';
    syncPartyDropdown();
    setFilters({ code: '', name: '', party });
    load();
  }

  /* Programmatic party selection (used by filters.js reset / autocomplete). */
  function setPartyValue(party) {
    document.getElementById('filterParty').value = party || '';
    syncPartyDropdown();
  }

  function setStatus(text, isError = false) {
    const el = document.getElementById('dashStatus');
    if (el) {
      el.textContent = text;
      el.style.color = isError ? '#dc2626' : '';
    }
  }

  async function load() {
    if (!electionId) return;
    setStatus('Loading dashboard…');
    const params = new URLSearchParams({ election_id: electionId });
    if (filters.code) params.set('code', filters.code);
    if (filters.name) params.set('name', filters.name);
    if (filters.party) params.set('party', filters.party);

    try {
      const res = await fetch(`/api/dashboard?${params.toString()}`);
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      render(data);
      if (!data.results.length) {
        setStatus('No election data matches the selected filters.');
      } else {
        setStatus('');
      }
    } catch (err) {
      setStatus('Could not load dashboard data.', true);
    }
  }

  function render(data) {
    partyColors = Object.assign({}, data.party_colors || {});
    partyLogos = Object.assign({}, data.party_logos || {});
    (data.party_seats || []).forEach((p, i) => {
      if (!partyColors[p.label]) partyColors[p.label] = p.color || PALETTE[i % PALETTE.length];
      if (!partyLogos[p.label] && p.logo) partyLogos[p.label] = p.logo;
    });
    renderKpis(data.kpis);
    renderPartyCards(data.party_seats, data.party_vote_share || []);
    populatePartyFilter(data.parties);
    renderCharts(data);
    renderTable(data.results);
    renderConstituencyDetail(data.constituency_detail);
    lastResults = data.results;
  }

  function renderKpis(k) {
    const grid = document.getElementById('kpiGrid');
    grid.innerHTML = `
      <div class="stat-card"><div class="stat-value">${fmt(k.total_seats)}</div><div class="stat-label">Total Seats</div></div>
      <div class="stat-card"><div class="stat-value">${fmt(k.total_votes)}</div><div class="stat-label">Total Votes</div></div>
      <div class="stat-card"><div class="stat-value">${fmt(k.total_candidates)}</div><div class="stat-label">Total Candidates</div></div>
      <div class="stat-card"><div class="stat-value" style="font-size:1.15rem;padding-top:0.5rem;">${k.winner_party}</div><div class="stat-label">Winner Party</div></div>
      <div class="stat-card"><div class="stat-value">${fmt(k.highest_margin)}</div><div class="stat-label">Highest Margin</div></div>
      <div class="stat-card"><div class="stat-value">${fmt(k.average_margin)}</div><div class="stat-label">Average Margin</div></div>
    `;
  }

  function renderPartyCards(partySeats, voteShare) {
    const shareMap = {};
    voteShare.forEach((p) => { shareMap[p.label] = p; });
    const wrap = document.getElementById('partyCards');
    wrap.innerHTML = '';
    partySeats.forEach((p) => {
      const share = shareMap[p.label] || {};
      const card = document.createElement('div');
      card.className = 'party-card clickable';
      card.title = `Click to filter dashboard to ${p.label}`;
      card.style.borderTop = `5px solid ${p.color || partyColors[p.label] || '#64748b'}`;
      card.innerHTML = `
        <div class="party-head">${partyLogoHtml(p.label, p.logo || partyLogos[p.label], p.color)}<span class="party-name">${p.label}</span></div>
        <div class="party-seats">${p.seats} ${p.seats === 1 ? 'Seat' : 'Seats'}</div>
        <div class="party-sub">Seats Won</div>
        <div class="party-votes">${fmt(share.votes || 0)} votes · ${share.pct || 0}% Vote Share</div>
      `;
      card.addEventListener('click', () => applyPartyFilter(p.label));
      wrap.appendChild(card);
    });
  }

  function populatePartyFilter(parties) {
    const select = document.getElementById('filterParty');
    const current = select.value;
    select.innerHTML = '<option value="">All Parties</option>';
    parties.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = p;
      select.appendChild(opt);
    });
    if (parties.includes(current)) select.value = current;
    syncPartyDropdown();
  }

  /* Custom party dropdown with actual party logos (the native <select> stays
     hidden as the source of truth so filters.js keeps working). */
  let dropdownBuilt = false;
  function buildPartyDropdown() {
    if (dropdownBuilt) return;
    const select = document.getElementById('filterParty');
    select.classList.add('hidden-select');
    const wrap = document.createElement('div');
    wrap.className = 'party-dropdown';
    wrap.innerHTML = `
      <button type="button" class="party-dropdown-toggle" id="partyDropdownToggle">
        <span class="party-dropdown-label" id="partyDropdownLabel">All Parties</span>
        <span class="caret"></span>
      </button>
      <div class="party-dropdown-menu" id="partyDropdownMenu" hidden></div>`;
    select.parentNode.appendChild(wrap);
    const menu = wrap.querySelector('#partyDropdownMenu');
    wrap.querySelector('#partyDropdownToggle').addEventListener('click', (e) => {
      e.stopPropagation();
      menu.hidden = !menu.hidden;
    });
    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) menu.hidden = true;
    });
    dropdownBuilt = true;
  }

  function syncPartyDropdown() {
    const select = document.getElementById('filterParty');
    if (!select) return;
    buildPartyDropdown();
    const menu = document.getElementById('partyDropdownMenu');
    const label = document.getElementById('partyDropdownLabel');
    menu.innerHTML = '';

    const addItem = (value, name, logo) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'party-dropdown-item' + (select.value === value ? ' active' : '');
      item.innerHTML = value
        ? `${partyLogoHtml(name, logo, partyColors[name])}<span>${name}</span>`
        : '<span>All Parties</span>';
      item.addEventListener('click', () => {
        select.value = value;
        select.dispatchEvent(new Event('change'));
        menu.hidden = true;
      });
      menu.appendChild(item);
    };

    addItem('', 'All Parties', null);
    Array.from(select.options).slice(1).forEach((opt) =>
      addItem(opt.value, opt.value, partyLogos[opt.value]));

    const cur = select.value;
    label.innerHTML = cur
      ? `${partyLogoHtml(cur, partyLogos[cur], partyColors[cur])}<span>${cur}</span>`
      : 'All Parties';
  }

  function renderCharts(data) {
    const constLogos = {};
    if (data.top_margins) {
      data.top_margins.forEach((m) => {
        if (partyLogos[m.party]) constLogos[m.constituency] = partyLogos[m.party];
      });
    }
    if (data.bottom_margins) {
      data.bottom_margins.forEach((m) => {
        if (partyLogos[m.party]) constLogos[m.constituency] = partyLogos[m.party];
      });
    }
    if (data.margin_vs_party) {
      data.margin_vs_party.forEach((m) => {
        if (partyLogos[m.winner_party]) constLogos[m.constituency] = partyLogos[m.winner_party];
      });
    }
    if (data.top_winner_votes) {
      data.top_winner_votes.forEach((w) => {
        const label = `${w.candidate} (${w.constituency})`;
        if (partyLogos[w.party]) constLogos[label] = partyLogos[w.party];
      });
    }
    if (data.candidate_performance) {
      data.candidate_performance.forEach((c) => {
        const label = `${c.candidate} (${c.party})`;
        if (partyLogos[c.party]) constLogos[label] = partyLogos[c.party];
      });
    }

    makeBarChart('chartSeats',
      data.party_seats.map((p) => p.label),
      data.party_seats.map((p) => p.seats),
      {
        label: 'Seats',
        colors: data.party_seats.map((p) => partyColors[p.label]),
        logos: partyLogos,
        onSelect: (index) => applyPartyFilter(data.party_seats[index].label),
      });

    makeDoughnutChart('chartVoteShare',
      data.party_vote_share.map((p) => p.label),
      data.party_vote_share.map((p) => p.pct),
      {
        colors: data.party_vote_share.map((p) => p.color || partyColors[p.label]),
        logos: partyLogos,
      });

    makeBarChart('chartTopMargins',
      data.top_margins.map((m) => `${m.constituency}`),
      data.top_margins.map((m) => m.margin),
      { horizontal: true, label: 'Margin', logos: constLogos });

    makeBarChart('chartBottomMargins',
      data.bottom_margins.map((m) => `${m.constituency}`),
      data.bottom_margins.map((m) => m.margin),
      { horizontal: true, label: 'Margin', logos: constLogos });

    makeBarChart('chartWinnerVotes',
      data.top_winner_votes.map((w) => `${w.candidate} (${w.constituency})`),
      data.top_winner_votes.map((w) => w.votes),
      { horizontal: true, label: 'Votes', logos: constLogos });

    // Winner party vs winning margin - bars coloured by the winner party
    makeBarChart('chartMarginParty',
      data.margin_vs_party.map((m) => m.constituency),
      data.margin_vs_party.map((m) => m.margin),
      {
        label: 'Margin',
        colors: data.margin_vs_party.map((m) => partyColors[m.winner_party] || '#64748b'),
        logos: constLogos,
      });

    makeBarChart('chartPartyVotes',
      data.party_total_votes.map((p) => p.label),
      data.party_total_votes.map((p) => p.votes),
      {
        label: 'Votes',
        colors: data.party_total_votes.map((p) => partyColors[p.label]),
        logos: partyLogos,
      });

    // Candidate performance - top candidates by votes polled
    makeBarChart('chartCandidatePerf',
      data.candidate_performance.map((c) => `${c.candidate} (${c.party})`),
      data.candidate_performance.map((c) => c.votes),
      {
        horizontal: true,
        label: 'Votes',
        colors: data.candidate_performance.map((c) => partyColors[c.party] || '#64748b'),
        logos: constLogos,
      });

    // State-wise seats - only shown when multiple states are aggregated
    const stateCard = document.getElementById('stateWiseCard');
    if (data.state_wise && data.state_wise.length > 1) {
      stateCard.hidden = false;
      makeBarChart('chartStateWise',
        data.state_wise.map((s) => s.state),
        data.state_wise.map((s) => s.seats),
        { label: 'Seats' });
    } else {
      stateCard.hidden = true;
      destroyChart('chartStateWise');
    }
  }

  function constituencyUrl(code) {
    const base = window.location.pathname.replace(/\/+$/, '');
    return `${base}/${encodeURIComponent(code)}`;
  }

  function partyCell(party) {
    return `<span class="cell-party">${partyLogoHtml(party, partyLogos[party], partyColors[party])}<span>${party}</span></span>`;
  }

  function renderTable(rows) {
    const tbody = document.querySelector('#resultsTable tbody');
    tbody.innerHTML = '';
    rows.forEach((r) => {
      const tr = document.createElement('tr');
      const runnerUpHtml = (r.runner_up && r.runner_up !== '-' && r.runner_up_party && r.runner_up_party !== '-')
        ? `${r.runner_up} ${partyCell(r.runner_up_party)}`
        : '-';
      tr.innerHTML = `
        <td><a href="${constituencyUrl(r.code)}">${r.code}</a></td>
        <td><a href="${constituencyUrl(r.code)}">${r.name}</a></td>
        <td>${r.winner}</td>
        <td>${partyCell(r.winner_party)}</td>
        <td>${fmt(r.winner_votes)}</td>
        <td>${runnerUpHtml}</td>
        <td>${fmt(r.margin)}</td>
        <td>${r.winner_pct}%</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderConstituencyDetail(detail) {
    const section = document.getElementById('constituencyDetail');
    if (!detail) {
      section.hidden = true;
      section.innerHTML = '';
      return;
    }

    const podium = (title, cls, c) => c ? `
      <div class="podium-card ${cls}">
        <div class="podium-label">${title}</div>
        <div class="podium-party">${partyLogoHtml(c.party, c.logo, c.color)}<span>${c.party}</span></div>
        <h3>${c.candidate}</h3>
        <p class="podium-votes">${fmt(c.votes)} votes · ${c.pct}%</p>
      </div>` : '';

    const rows = detail.candidates.map((c) => `
      <tr class="${c.is_winner ? 'winner-row' : ''}">
        <td>${c.rank}</td><td>${c.candidate}</td>
        <td><span class="cell-party">${partyLogoHtml(c.party, c.logo, c.color)}<span>${c.party}</span></span></td>
        <td>${fmt(c.votes)}</td><td>${c.pct}%</td>
      </tr>`).join('');

    section.innerHTML = `
      <div class="const-detail-header">
        <h3>CONSTITUENCY RESULT — ${detail.name} (${detail.type} ${detail.code})</h3>
        <p class="muted">${detail.state} · ${detail.year} · Winning margin ${fmt(detail.margin)} · Total votes ${fmt(detail.total_votes)}</p>
      </div>
      <div class="podium">
        ${podium('WINNER', 'gold', detail.winner)}
        ${podium('RUNNER-UP', 'silver', detail.runner_up)}
        ${podium('THIRD CANDIDATE', 'bronze', detail.third)}
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>Rank</th><th>Candidate</th><th>Party</th><th>Votes</th><th>Vote %</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
    section.hidden = false;
  }

  // Client-side quick filter for the results table
  function initTableSearch() {
    const input = document.getElementById('tableSearch');
    if (!input) return;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      const tbody = document.querySelector('#resultsTable tbody');
      const visible = q
        ? lastResults.filter((r) =>
            [r.code, r.name, r.winner, r.winner_party, r.runner_up].join(' ').toLowerCase().includes(q))
        : lastResults;
      renderTable(visible);
    });
  }

  function init() {
    initDashboardFilters();
    initTableSearch();
    load();
  }

  return { init, load, setFilters, setPartyValue, electionId, electionType };
})();

document.addEventListener('DOMContentLoaded', Dashboard.init);
