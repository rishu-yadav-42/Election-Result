"""Global statistics service: numbers shown on the home page and admin dashboard.

All values are computed from uploaded data. With an empty database every value is 0.
"""

from collections import defaultdict

from sqlalchemy import func

from models.models import db, Election, State, Constituency, Result, Candidate


def global_stats():
    total_elections = Election.query.count()
    total_states = db.session.query(func.count(func.distinct(Election.state_id))).scalar() or 0
    total_constituencies = Constituency.query.count()
    total_candidates = Result.query.count()
    total_votes = db.session.query(func.sum(Result.votes)).scalar() or 0
    return {
        'total_elections': total_elections,
        'total_states': total_states,
        'total_constituencies': total_constituencies,
        'total_candidates': total_candidates,
        'total_votes': int(total_votes),
    }


def party_statistics(election_id=None):
    """Seats won and total votes per party (optionally for one election)."""
    query = (db.session.query(Candidate.party_id, Result.is_winner,
                              func.sum(Result.votes), func.count(Result.id))
             .join(Result, Result.candidate_id == Candidate.id))
    if election_id:
        query = query.filter(Result.election_id == election_id)
    rows = query.group_by(Candidate.party_id, Result.is_winner).all()

    from models.models import Party
    stats = defaultdict(lambda: {'seats': 0, 'votes': 0, 'contested': 0})
    for party_id, is_winner, votes, count in rows:
        party = Party.query.get(party_id)
        stats[party.name]['votes'] += int(votes or 0)
        stats[party.name]['contested'] += int(count or 0)
        if is_winner:
            stats[party.name]['seats'] += int(count or 0)

    return [{'party': name, **data} for name, data in
            sorted(stats.items(), key=lambda x: -x[1]['seats'])]


def margin_statistics(election_id=None):
    """Highest / lowest / average winning margin per election."""
    from services.dashboard_engine import build_dashboard_data
    query = Election.query
    if election_id:
        query = query.filter_by(id=election_id)

    output = []
    for election in query.all():
        data = build_dashboard_data([election])
        output.append({
            'election': election.name,
            'election_id': election.id,
            'highest_margin': data['kpis']['highest_margin'],
            'average_margin': data['kpis']['average_margin'],
        })
    return output


def candidate_statistics(election_id=None, limit=10):
    """Top candidates by votes polled."""
    query = (db.session.query(Candidate.name, func.sum(Result.votes).label('votes'))
             .join(Result, Result.candidate_id == Candidate.id))
    if election_id:
        query = query.filter(Result.election_id == election_id)
    rows = query.group_by(Candidate.id).order_by(func.sum(Result.votes).desc()).limit(limit).all()
    return [{'candidate': name, 'votes': int(votes or 0)} for name, votes in rows]
