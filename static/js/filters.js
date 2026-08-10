/* Filter wiring for the dynamic dashboard: apply / reset / autocomplete search. */

function initDashboardFilters() {
  const applyBtn = document.getElementById('applyFilters');
  const resetBtn = document.getElementById('resetFilters');
  const codeInput = document.getElementById('filterCode');
  const nameInput = document.getElementById('filterName');
  const partySelect = document.getElementById('filterParty');
  const autoComplete = document.getElementById('codeAutocomplete');

  function readFilters() {
    return {
      code: codeInput.value.trim(),
      name: nameInput.value.trim(),
      party: partySelect.value,
    };
  }

  applyBtn.addEventListener('click', () => {
    Dashboard.setFilters(readFilters());
    Dashboard.load();
  });

  resetBtn.addEventListener('click', () => {
    codeInput.value = '';
    nameInput.value = '';
    Dashboard.setPartyValue('');
    Dashboard.setFilters({ code: '', name: '', party: '' });
    Dashboard.load();
  });

  [codeInput, nameInput].forEach((el) =>
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        Dashboard.setFilters(readFilters());
        Dashboard.load();
      }
    })
  );

  partySelect.addEventListener('change', () => {
    Dashboard.setFilters(readFilters());
    Dashboard.load();
  });

  // Autocomplete for constituency code / name / candidate
  let debounceTimer = null;
  codeInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = codeInput.value.trim();
    if (q.length < 1) {
      autoComplete.style.display = 'none';
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?election_id=${Dashboard.electionId}&q=${encodeURIComponent(q)}`);
        const items = await res.json();
        autoComplete.innerHTML = '';
        if (!items.length) {
          autoComplete.style.display = 'none';
          return;
        }
        items.forEach((item) => {
          const div = document.createElement('div');
          div.textContent = item.label;
          div.addEventListener('click', () => {
            autoComplete.style.display = 'none';
            if (item.type === 'party') {
              Dashboard.setPartyValue(item.party);
              codeInput.value = '';
            } else {
              codeInput.value = item.code;
            }
            Dashboard.setFilters(readFilters());
            Dashboard.load();
          });
          autoComplete.appendChild(div);
        });
        autoComplete.style.display = 'block';
      } catch (err) {
        autoComplete.style.display = 'none';
      }
    }, 200);
  });

  document.addEventListener('click', (e) => {
    if (!autoComplete.contains(e.target) && e.target !== codeInput) {
      autoComplete.style.display = 'none';
    }
  });
}
