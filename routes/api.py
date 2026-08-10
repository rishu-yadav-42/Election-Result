"""REST API: JSON endpoints consumed by the dashboard frontend."""

from flask import Blueprint, jsonify, request, abort

from models.models import db, Election, State, Constituency, Result, Candidate, Party
from services.dashboard_engine import build_dashboard_data, constituency_detail
from services.statistics import party_statistics, margin_statistics, candidate_statistics

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _elections_or_404():
    """Accept a single election_id or a comma-separated list (national aggregate view)."""
    raw = request.args.get('election_id', '')
    ids = [int(part) for part in str(raw).split(',') if part.strip().isdigit()]
    elections = Election.query.filter(Election.id.in_(ids)).all() if ids else []
    if not elections:
        abort(404)
    elections.sort(key=lambda e: ids.index(e.id))
    return elections


def _election_or_404():
    return _elections_or_404()[0]


@api_bp.route('/elections')
def elections():
    items = [{
        'id': e.id, 'name': e.name, 'type': e.election_type,
        'type_label': e.type_label, 'year': e.year, 'state': e.state.name,
    } for e in Election.query.order_by(Election.year.desc()).all()]
    return jsonify(items)


@api_bp.route('/states')
def states():
    return jsonify([{'id': s.id, 'name': s.name} for s in State.query.order_by(State.name).all()])


@api_bp.route('/elections/<int:election_id>')
def election_detail(election_id):
    election = Election.query.get_or_404(election_id)
    constituencies = [{'code': c.code, 'name': c.name, 'type': c.type}
                      for c in Constituency.query.filter_by(election_id=election.id)
                      .order_by(Constituency.code).all()]
    return jsonify({
        'id': election.id, 'name': election.name, 'type': election.election_type,
        'type_label': election.type_label, 'year': election.year,
        'state': election.state.name, 'constituencies': constituencies,
    })


@api_bp.route('/results')
def results():
    elections = _elections_or_404()
    data = build_dashboard_data(
        elections,
        party=request.args.get('party'),
        constituency_code=request.args.get('code'),
        constituency_name=request.args.get('name'),
    )
    return jsonify(data['results'])


@api_bp.route('/constituency/<code>')
def constituency(code):
    elections = _elections_or_404()
    for election in elections:
        detail = constituency_detail(election, code)
        if detail:
            return jsonify(detail)
    abort(404)


@api_bp.route('/dashboard')
def dashboard_data():
    elections = _elections_or_404()
    data = build_dashboard_data(
        elections,
        party=request.args.get('party'),
        constituency_code=request.args.get('code'),
        constituency_name=request.args.get('name'),
    )
    # Include full detail when the filters point at exactly one constituency
    if len(data['results']) == 1:
        detail = None
        for election in elections:
            detail = constituency_detail(election, data['results'][0]['code'])
            if detail:
                break
        data['constituency_detail'] = detail
    else:
        data['constituency_detail'] = None
    return jsonify(data)


@api_bp.route('/party-statistics')
def party_stats():
    return jsonify(party_statistics(request.args.get('election_id', type=int)))


@api_bp.route('/margin-statistics')
def margin_stats():
    return jsonify(margin_statistics(request.args.get('election_id', type=int)))


@api_bp.route('/candidate-statistics')
def candidate_stats():
    return jsonify(candidate_statistics(request.args.get('election_id', type=int)))


@api_bp.route('/search')
def search():
    """Autocomplete for constituency code / name / candidate / party."""
    election = _election_or_404()
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])

    matches = []
    seen = set()
    for c in Constituency.query.filter_by(election_id=election.id).all():
        if q in c.code.lower() or q in c.name.lower():
            if c.id not in seen:
                matches.append({'type': 'constituency', 'code': c.code, 'label': f'{c.code} - {c.name}'})
                seen.add(c.id)

    # Party suggestions (parties that contested this election)
    party_names = (db.session.query(Party.name)
                   .join(Candidate, Candidate.party_id == Party.id)
                   .join(Result, Result.candidate_id == Candidate.id)
                   .filter(Result.election_id == election.id)
                   .distinct().all())
    for (name,) in party_names:
        if q in name.lower():
            matches.append({'type': 'party', 'party': name, 'label': f'Party: {name}'})

    rows = (db.session.query(Result.id, Constituency.code, Constituency.name,
                             Candidate.name)
            .join(Constituency, Result.constituency_id == Constituency.id)
            .join(Candidate, Result.candidate_id == Candidate.id)
            .filter(Result.election_id == election.id).all())
    for _, code, cname, candidate_name in rows:
        if q in candidate_name.lower() and (code, candidate_name) not in seen:
            matches.append({'type': 'candidate', 'code': code,
                            'label': f'{candidate_name} ({cname})'})
            seen.add((code, candidate_name))
        if len(matches) >= 15:
            break

    return jsonify(matches[:15])
