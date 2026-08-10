"""Data processing service: file parsing, column mapping and database import.

Dashboards are 100% data driven - nothing is imported until the Admin uploads
a CSV / XLSX / XLS file and confirms the column mapping.
"""

import os
import re

import pandas as pd

from models.models import db, Election, Constituency, Party, Candidate, Result, Upload

ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}

# Canonical system columns the dashboard engine understands
SYSTEM_COLUMNS = [
    ('constituency_code', 'Constituency Code (AC Code / PC Code)', True),
    ('constituency_name', 'Constituency Name', True),
    ('candidate', 'Candidate', True),
    ('party', 'Party', True),
    ('votes', 'Votes', True),
    ('rank', 'Rank', False),
    ('margin', 'Winning Margin', False),
    ('vote_percentage', 'Vote Percentage', False),
]

# Aliases used to auto-suggest a mapping for uploaded columns
COLUMN_ALIASES = {
    'constituency_code': ['ac_no', 'ac_code', 'ac code', 'ac', 'ac number', 'pc_code', 'pc code',
                          'pc_no', 'pc', 'constituency_code', 'constituency code', 'code',
                          'seat_no', 'seat no', 'seat code'],
    'constituency_name': ['assembly_name', 'assembly name', 'constituency', 'constituency_name',
                          'constituency name', 'pc_name', 'pc name', 'ac_name', 'ac name',
                          'seat_name', 'seat name', 'name_of_constituency'],
    'candidate': ['candidate_name', 'candidate name', 'candidate', 'candidates', 'name_of_candidate'],
    'party': ['party_name', 'party name', 'party', 'party_abbr', 'party abbreviation', 'political_party'],
    'votes': ['total_votes', 'total votes', 'votes', 'votes_polled', 'votes secured', 'vote_count'],
    'rank': ['rank', 'position', 'position secured', 'rank_secured'],
    'margin': ['margin', 'winning_margin', 'winning margin', 'vote_margin'],
    'vote_percentage': ['vote_percentage', 'vote percentage', 'vote_share', 'vote share', 'votes_percent'],
}

# ------------------------------------------------------------------
# Summary datasets: one row per constituency carrying the Winner,
# Runner-up and Third candidate. Expanded into candidate rows on import.
SUMMARY_COLUMNS = [
    ('constituency_code', 'Constituency Code (AC Code / PC Code)', True),
    ('constituency_name', 'Constituency Name', True),
    ('winner', 'Winner (Candidate)', True),
    ('winner_party', 'Winner Party', True),
    ('winner_votes', 'Winner Votes', True),
    ('runner_up', 'Runner-up (Candidate)', False),
    ('runner_up_party', 'Runner-up Party', False),
    ('runner_up_votes', 'Runner-up Votes', False),
    ('third', 'Third Candidate', False),
    ('third_party', 'Third Party', False),
    ('third_votes', 'Third Votes', False),
    ('margin', 'Winning Margin', False),
]

SUMMARY_ALIASES = {
    'constituency_code': COLUMN_ALIASES['constituency_code'],
    'constituency_name': COLUMN_ALIASES['constituency_name'],
    'winner': ['winner', 'winner_name', 'winner name', 'winner candidate'],
    'winner_party': ['winner_party', 'winner party', 'winning_party', 'winning party'],
    'winner_votes': ['winner_votes', 'winner votes', 'winner_total_votes', 'winning votes'],
    'runner_up': ['runner_up', 'runner-up', 'runner up', 'runnerup', 'runner_up_name',
                  'second_candidate', 'second candidate'],
    'runner_up_party': ['runner_up_party', 'runner-up party', 'runner up party',
                        'second_party', 'second party'],
    'runner_up_votes': ['runner_up_votes', 'runner-up votes', 'runner up votes',
                        'second_votes', 'second votes'],
    'third': ['third', 'third_candidate', 'third candidate', 'third_name', '3rd_candidate'],
    'third_party': ['third_party', 'third party', '3rd_party'],
    'third_votes': ['third_votes', 'third votes', '3rd_votes'],
    'margin': COLUMN_ALIASES['margin'],
}


def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def secure_name(filename):
    """Keep only safe characters in an uploaded filename."""
    name = os.path.basename(filename)
    name = re.sub(r'[^\w.\-]', '_', name)
    return name


def read_dataset(path):
    """Read a CSV / XLSX / XLS file into a pandas DataFrame."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError('Could not decode CSV file. Please save it as UTF-8.')
    if ext == '.xlsx':
        return pd.read_excel(path, engine='openpyxl')
    if ext == '.xls':
        return pd.read_excel(path, engine='xlrd')
    raise ValueError('Unsupported file type. Upload .csv, .xlsx or .xls')


def suggest_mapping(columns, dataset_format='candidate'):
    """Auto-suggest system column for every uploaded column."""
    aliases = SUMMARY_ALIASES if dataset_format == 'summary' else COLUMN_ALIASES
    mapping = {}
    for col in columns:
        key = str(col).strip().lower()
        for system_col, alias_list in aliases.items():
            if key in alias_list:
                mapping[str(col)] = system_col
                break
        else:
            mapping[str(col)] = ''
    return mapping


def detect_format(columns):
    """Guess whether a file is a constituency-summary sheet (one row per
    constituency with Winner / Runner-up columns) or candidate-level data."""
    keys = {str(c).strip().lower() for c in columns}
    for alias_list in (SUMMARY_ALIASES['winner'], SUMMARY_ALIASES['runner_up']):
        if keys & set(alias_list):
            return 'summary'
    return 'candidate'


def expand_summary(df):
    """Convert a mapped summary DataFrame (winner / runner-up / third columns)
    into candidate-level rows so the existing validation and import pipeline
    can process it unchanged."""
    rows = []
    for _, r in df.iterrows():
        code = r.get('constituency_code')
        name = r.get('constituency_name')
        for rank, (cand, party, votes) in (
                (1, ('winner', 'winner_party', 'winner_votes')),
                (2, ('runner_up', 'runner_up_party', 'runner_up_votes')),
                (3, ('third', 'third_party', 'third_votes'))):
            cand_val = r.get(cand)
            votes_val = r.get(votes)
            if pd.isna(cand_val) or not str(cand_val).strip():
                continue  # e.g. uncontested seat with no runner-up
            rows.append({
                'constituency_code': code,
                'constituency_name': name,
                'candidate': cand_val,
                'party': r.get(party),
                'votes': votes_val,
                'rank': rank,
            })
    return pd.DataFrame(rows)


def apply_mapping(df, mapping):
    """Rename uploaded columns to system column names (first match wins)."""
    rename = {}
    used = set()
    for col, system_col in mapping.items():
        if system_col and system_col not in used and col in df.columns:
            rename[col] = system_col
            used.add(system_col)
    return df.rename(columns=rename)


def get_or_create_election(election_type, state, year):
    """Return an existing election for (type, state, year) or create a new one."""
    election = Election.query.filter_by(
        election_type=election_type, state_id=state.id, year=year).first()
    if election:
        return election, False

    if election_type == 'lok_sabha':
        name = f'Lok Sabha Election {year}' if state.name == 'India' \
            else f'{state.name} Lok Sabha Election {year}'
    else:
        name = f'{state.name} Vidhan Sabha Election {year}'

    election = Election(election_type=election_type, year=year, state_id=state.id, name=name)
    db.session.add(election)
    db.session.flush()
    return election, True


def clear_election_data(election):
    """Remove all records of one election only (used when replacing a dataset)."""
    Result.query.filter_by(election_id=election.id).delete()
    Constituency.query.filter_by(election_id=election.id).delete()
    db.session.flush()


def import_data(election, df, original_filename):
    """Import a validated, mapped DataFrame into the database.

    Computes rank / margin / vote percentage when they are not present in the file,
    so the dashboard engine always has complete data.
    """
    ctype = 'PC' if election.election_type == 'lok_sabha' else 'AC'

    constituency_cache = {}
    party_cache = {p.name.lower(): p for p in Party.query.all()}
    candidate_cache = {}

    grouped = df.groupby('constituency_code', sort=False)

    for code, rows in grouped:
        code_str = str(code).strip()
        name_col = 'constituency_name' if 'constituency_name' in rows.columns else None
        const_name = str(rows[name_col].dropna().iloc[0]).strip() if name_col and rows[name_col].dropna().size else code_str

        constituency = constituency_cache.get(code_str)
        if not constituency:
            constituency = Constituency.query.filter_by(election_id=election.id, code=code_str).first()
            if not constituency:
                constituency = Constituency(election_id=election.id, code=code_str,
                                            name=const_name, type=ctype)
                db.session.add(constituency)
                db.session.flush()
            constituency_cache[code_str] = constituency

        entries = []
        for _, row in rows.iterrows():
            party_name = str(row['party']).strip()
            party = party_cache.get(party_name.lower())
            if not party:
                party = Party(name=party_name)
                db.session.add(party)
                db.session.flush()
                party_cache[party_name.lower()] = party

            cand_key = (row['candidate'].strip().lower(), party.id)
            candidate = candidate_cache.get(cand_key)
            if not candidate:
                candidate = Candidate(name=str(row['candidate']).strip(), party_id=party.id)
                db.session.add(candidate)
                db.session.flush()
                candidate_cache[cand_key] = candidate

            entries.append({
                'candidate_id': candidate.id,
                'votes': int(row['votes']),
                'rank': row.get('rank') if isinstance(row.get('rank'), (int, float)) else None,
            })

        # Rank by votes if rank missing
        entries.sort(key=lambda e: e['votes'], reverse=True)
        total_votes = sum(e['votes'] for e in entries)
        margin = (entries[0]['votes'] - entries[1]['votes']) if len(entries) > 1 else entries[0]['votes']

        for idx, entry in enumerate(entries, start=1):
            rank = int(entry['rank']) if entry['rank'] else idx
            pct = round(entry['votes'] / total_votes * 100, 2) if total_votes else 0
            db.session.add(Result(
                election_id=election.id,
                constituency_id=constituency.id,
                candidate_id=entry['candidate_id'],
                votes=entry['votes'],
                rank=rank,
                margin=margin if rank == 1 else None,
                vote_percentage=pct,
                is_winner=(rank == 1),
            ))

    db.session.add(Upload(election_id=election.id, filename=original_filename,
                          record_count=len(df)))
    db.session.commit()
    return len(df)
