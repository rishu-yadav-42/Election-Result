"""Validation service: checks the mapped dataset before import."""

import pandas as pd

REQUIRED_COLUMNS = ['constituency_code', 'constituency_name', 'candidate', 'party', 'votes']


def validate_dataset(df):
    """Validate a mapped DataFrame.

    Returns a dict with totals, a cleaned DataFrame containing only valid rows,
    plus error / warning messages shown to the Admin.
    """
    errors = []
    warnings = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return {
            'total': len(df), 'valid': 0,
            'errors': [f'Required column missing after mapping: {c}' for c in missing],
            'warnings': [], 'df': df.iloc[0:0],
        }

    total = len(df)
    work = df.copy()

    # Empty rows
    empty_mask = work.isna().all(axis=1)
    empty_count = int(empty_mask.sum())
    if empty_count:
        warnings.append(f'{empty_count} completely empty row(s) removed.')
        work = work[~empty_mask]

    # Required text fields
    for col, label in (('constituency_code', 'Constituency Code'),
                       ('candidate', 'Candidate'),
                       ('party', 'Party')):
        work[col] = work[col].astype('string').str.strip()
        bad = work[col].isna() | (work[col] == '') | (work[col].str.lower() == 'nan')
        n = int(bad.sum())
        if n:
            errors.append(f'{n} row(s) missing {label} - these rows will be skipped.')
            work = work[~bad]

    if 'constituency_name' in work.columns:
        work['constituency_name'] = work['constituency_name'].astype('string').str.strip()

    # Vote values
    work['votes'] = pd.to_numeric(work['votes'], errors='coerce')
    bad_votes = work['votes'].isna() | (work['votes'] < 0) | (work['votes'] % 1 != 0)
    n = int(bad_votes.sum())
    if n:
        errors.append(f'{n} row(s) have invalid vote values - these rows will be skipped.')
        work = work[~bad_votes]
    work['votes'] = work['votes'].astype(int)

    # Optional rank sanity check
    if 'rank' in work.columns:
        rank_num = pd.to_numeric(work['rank'], errors='coerce')
        bad_rank = rank_num.notna() & ((rank_num < 1) | (rank_num % 1 != 0))
        n = int(bad_rank.sum())
        if n:
            warnings.append(f'{n} row(s) have invalid Rank values - rank will be recomputed from votes.')
            rank_num[bad_rank] = pd.NA
        work['rank'] = rank_num

    # Duplicate candidate inside the same constituency
    dup_mask = work.duplicated(subset=['constituency_code', 'candidate'], keep='first')
    n = int(dup_mask.sum())
    if n:
        warnings.append(f'{n} duplicate candidate record(s) removed.')
        work = work[~dup_mask]

    return {
        'total': total,
        'valid': len(work),
        'errors': errors,
        'warnings': warnings,
        'df': work,
    }
