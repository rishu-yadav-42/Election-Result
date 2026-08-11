"""Dynamic dashboard engine.

ONE reusable engine generates every dashboard (any state, any year, any election
type) purely from database data. Nothing here is hardcoded - if the Admin has not
uploaded data for an election, no dashboard exists for it.
"""

from collections import defaultdict

from sqlalchemy.orm import joinedload

from models.models import db, Result, Constituency, Candidate, Party, Election
from services.party_meta import party_color, party_logo


def _constituency_summaries(results):
    """Group result rows into per-constituency summaries (winner, runner-up, margin...)."""
    by_const = defaultdict(list)
    for r in results:
        by_const[r.constituency_id].append(r)

    summaries = []
    for const_id, rows in by_const.items():
        rows = sorted(rows, key=lambda x: (x.rank if x.rank else 9999, -x.votes))
        winner = rows[0]
        runner = rows[1] if len(rows) > 1 else None
        margin = winner.votes - runner.votes if runner else winner.votes
        total_votes = sum(r.votes for r in rows)
        summaries.append({
            'constituency_id': const_id,
            'code': winner.constituency.code,
            'name': winner.constituency.name,
            'state': winner.constituency.election.state.name,
            'winner': winner.candidate.name,
            'winner_party': winner.candidate.party.name,
            'winner_votes': winner.votes,
            'winner_pct': round(winner.votes / total_votes * 100, 2) if total_votes else 0,
            'runner_up': runner.candidate.name if runner else '-',
            'runner_up_party': runner.candidate.party.name if runner else '-',
            'runner_up_votes': runner.votes if runner else 0,
            'margin': margin,
            'total_votes': total_votes,
            'candidates': len(rows),
        })

    summaries.sort(key=lambda s: (len(s['code']), s['code']))
    return summaries


def build_dashboard_data(elections, party=None, constituency_code=None, constituency_name=None):
    """Build the full dashboard payload for one election OR an aggregate of several
    elections (e.g. the national Lok Sabha view), honouring the active filters."""
    if not isinstance(elections, (list, tuple)):
        elections = [elections]
    election_ids = [e.id for e in elections]

    query = (Result.query
             .options(joinedload(Result.constituency)
                      .joinedload(Constituency.election)
                      .joinedload(Election.state),
                      joinedload(Result.candidate).joinedload(Candidate.party))
             .filter(Result.election_id.in_(election_ids)))

    results = query.all()

    # Party filter keeps only constituencies WON by that party, so margins and
    # totals stay correct against all opponents.
    if party:
        won_ids = {r.constituency_id for r in results
                   if r.is_winner and r.candidate.party.name.lower() == party.lower()}
        results = [r for r in results if r.constituency_id in won_ids]
    if constituency_code:
        results = [r for r in results if r.constituency.code == str(constituency_code).strip()]
    if constituency_name:
        needle = constituency_name.strip().lower()
        results = [r for r in results if needle in r.constituency.name.lower()]

    summaries = _constituency_summaries(results)

    # ---- KPIs ----
    total_seats = len(summaries)
    total_votes = sum(s['total_votes'] for s in summaries)
    total_candidates = sum(s['candidates'] for s in summaries)
    margins = [s['margin'] for s in summaries]

    seat_counter = defaultdict(int)
    for s in summaries:
        seat_counter[s['winner_party']] += 1
    winner_party = max(seat_counter, key=seat_counter.get) if seat_counter else '-'

    kpis = {
        'total_seats': total_seats,
        'total_votes': total_votes,
        'total_candidates': total_candidates,
        'winner_party': winner_party,
        'highest_margin': max(margins) if margins else 0,
        'average_margin': round(sum(margins) / len(margins)) if margins else 0,
    }

    # ---- Party aggregates ----
    party_votes = defaultdict(int)
    for r in results:
        party_votes[r.candidate.party.name] += r.votes

    party_seats = sorted(
        [{'label': p, 'seats': c, 'color': party_color(p), 'logo': party_logo(p),
          'votes': party_votes[p],
          'pct': round(party_votes[p] / total_votes * 100, 2) if total_votes else 0}
         for p, c in seat_counter.items()],
        key=lambda x: -x['seats'])

    party_vote_share = sorted(
        [{'label': p, 'votes': v,
          'pct': round(v / total_votes * 100, 2) if total_votes else 0,
          'color': party_color(p), 'logo': party_logo(p)}
         for p, v in party_votes.items()],
        key=lambda x: -x['votes'])

    # ---- Margin charts ----
    by_margin = sorted(summaries, key=lambda s: -s['margin'])
    top_margins = [
        {'constituency': s['name'], 'code': s['code'], 'winner': s['winner'],
         'party': s['winner_party'], 'margin': s['margin']}
        for s in by_margin[:10]]
    bottom_margins = [
        {'constituency': s['name'], 'code': s['code'], 'winner': s['winner'],
         'party': s['winner_party'], 'margin': s['margin']}
        for s in sorted(summaries, key=lambda s: s['margin'])[:10]]

    # ---- Candidate-wise winning votes (top 10) ----
    top_winner_votes = [
        {'candidate': s['winner'], 'constituency': s['name'],
         'party': s['winner_party'], 'votes': s['winner_votes']}
        for s in sorted(summaries, key=lambda s: -s['winner_votes'])[:10]]

    # ---- Winner party vs winning margin (coloured by party on the client) ----
    margin_vs_party = [
        {'constituency': s['name'], 'winner_party': s['winner_party'],
         'margin': s['margin'], 'color': party_color(s['winner_party'])}
        for s in by_margin[:20]]

    # ---- Candidate performance: top candidates by votes polled ----
    top_candidates = sorted(results, key=lambda r: -r.votes)[:10]
    candidate_performance = [{
        'candidate': r.candidate.name,
        'party': r.candidate.party.name,
        'constituency': r.constituency.name,
        'votes': r.votes,
        'color': party_color(r.candidate.party.name),
    } for r in top_candidates]

    # ---- State-wise seats (only meaningful when aggregating multiple states) ----
    state_seat_counter = defaultdict(int)
    for s in summaries:
        state_seat_counter[s['state']] += 1
    state_wise = [{'state': st, 'seats': c} for st, c in
                  sorted(state_seat_counter.items(), key=lambda x: -x[1])]

    # ---- Margin Range Distribution ----
    margin_buckets = {
        'Nail-Biter (< 5k)': 0,
        'Close (5k - 20k)': 0,
        'Decisive (20k - 50k)': 0,
        'Landslide (> 50k)': 0,
    }
    for m in margins:
        if m < 5000:
            margin_buckets['Nail-Biter (< 5k)'] += 1
        elif m < 20000:
            margin_buckets['Close (5k - 20k)'] += 1
        elif m < 50000:
            margin_buckets['Decisive (20k - 50k)'] += 1
        else:
            margin_buckets['Landslide (> 50k)'] += 1

    margin_distribution = [
        {'label': k, 'count': v, 'pct': round(v / total_seats * 100, 1) if total_seats else 0}
        for k, v in margin_buckets.items()
    ]

    # ---- Executive Data Insights ----
    top_seat_party = party_seats[0] if party_seats else None
    top_vote_party = party_vote_share[0] if party_vote_share else None
    closest_s = min(summaries, key=lambda s: s['margin']) if summaries else None
    largest_s = max(summaries, key=lambda s: s['margin']) if summaries else None
    nail_biter_count = margin_buckets['Nail-Biter (< 5k)']

    seat_vs_vote_comparison = []
    vote_share_map = {p['label']: p['pct'] for p in party_vote_share}
    for p in party_seats[:6]:  # Top 6 parties
        s_pct = round(p['seats'] / total_seats * 100, 1) if total_seats else 0
        v_pct = vote_share_map.get(p['label'], 0)
        ratio = round(s_pct / v_pct, 2) if v_pct > 0 else 0
        seat_vs_vote_comparison.append({
            'label': p['label'],
            'seats': p['seats'],
            'seat_pct': s_pct,
            'vote_pct': v_pct,
            'conversion_ratio': ratio,
            'color': p['color'],
            'logo': p['logo'],
        })

    insights = {
        'dominant_party': {
            'name': top_seat_party['label'] if top_seat_party else '-',
            'seats': top_seat_party['seats'] if top_seat_party else 0,
            'seat_pct': round(top_seat_party['seats'] / total_seats * 100, 1) if (top_seat_party and total_seats) else 0,
            'vote_pct': vote_share_map.get(top_seat_party['label'], 0) if top_seat_party else 0,
            'color': top_seat_party['color'] if top_seat_party else '#64748b',
            'logo': top_seat_party['logo'] if top_seat_party else None,
        },
        'closest_race': {
            'constituency': closest_s['name'],
            'code': closest_s['code'],
            'winner': closest_s['winner'],
            'winner_party': closest_s['winner_party'],
            'runner_up': closest_s['runner_up'],
            'runner_up_party': closest_s['runner_up_party'],
            'margin': closest_s['margin'],
            'color': party_color(closest_s['winner_party']),
        } if closest_s else None,
        'biggest_landslide': {
            'constituency': largest_s['name'],
            'code': largest_s['code'],
            'winner': largest_s['winner'],
            'winner_party': largest_s['winner_party'],
            'margin': largest_s['margin'],
            'color': party_color(largest_s['winner_party']),
        } if largest_s else None,
        'nail_biters_count': nail_biter_count,
        'nail_biters_pct': round(nail_biter_count / total_seats * 100, 1) if total_seats else 0,
        'conversion_leaders': seat_vs_vote_comparison,
    }

    primary = elections[0]
    return {
        'election': {
            'id': primary.id,
            'name': primary.name,
            'type': primary.election_type,
            'type_label': primary.type_label,
            'year': primary.year,
            'state': primary.state.name,
        },
        'is_multi': len(elections) > 1 or len(state_seat_counter) > 1,
        'kpis': kpis,
        'insights': insights,
        'margin_distribution': margin_distribution,
        'seat_vs_vote_comparison': seat_vs_vote_comparison,
        'party_seats': party_seats,
        'party_vote_share': party_vote_share,
        'party_total_votes': [{'label': p['label'], 'votes': p['votes'], 'color': p['color']}
                              for p in party_vote_share],
        'party_colors': {p: party_color(p) for p in party_votes},
        'party_logos': {p: party_logo(p) for p in party_votes},
        'top_margins': top_margins,
        'bottom_margins': bottom_margins,
        'top_winner_votes': top_winner_votes,
        'margin_vs_party': margin_vs_party,
        'candidate_performance': candidate_performance,
        'state_wise': state_wise,
        'results': summaries,
        'parties': sorted(party_votes.keys()),
    }


def constituency_detail(election, code):
    """Full candidate list for one constituency (dynamic number of candidates)."""
    constituency = Constituency.query.filter_by(election_id=election.id, code=str(code).strip()).first()
    if not constituency:
        return None

    rows = (Result.query
            .options(joinedload(Result.candidate).joinedload(Candidate.party))
            .filter_by(constituency_id=constituency.id)
            .all())
    rows.sort(key=lambda r: (r.rank if r.rank else 9999, -r.votes))

    total_votes = sum(r.votes for r in rows)
    candidates = [{
        'rank': idx,
        'candidate': r.candidate.name,
        'party': r.candidate.party.name,
        'logo': party_logo(r.candidate.party.name),
        'color': party_color(r.candidate.party.name),
        'votes': r.votes,
        'pct': round(r.votes / total_votes * 100, 2) if total_votes else 0,
        'is_winner': idx == 1,
    } for idx, r in enumerate(rows, start=1)]

    winner = candidates[0] if candidates else None
    runner = candidates[1] if len(candidates) > 1 else None
    third = candidates[2] if len(candidates) > 2 else None

    return {
        'code': constituency.code,
        'name': constituency.name,
        'type': constituency.type,
        'state': election.state.name,
        'year': election.year,
        'total_votes': total_votes,
        'margin': (winner['votes'] - runner['votes']) if winner and runner else (winner['votes'] if winner else 0),
        'winner': winner,
        'runner_up': runner,
        'third': third,
        'candidates': candidates,
    }
