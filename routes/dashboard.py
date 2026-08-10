"""Public routes: home page, election browsing and the dynamic dashboards.

Only elections that exist in the database (i.e. uploaded by the Admin) are shown.
"""

import re

from flask import Blueprint, render_template, abort, request

from models.models import db, Election, State, Result, ELECTION_TYPES
from services.statistics import global_stats
from services.dashboard_engine import build_dashboard_data, constituency_detail

dashboard_bp = Blueprint('dashboard', __name__)


def slugify(text):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', text.lower())).strip('-')


def _find_state_by_slug(slug):
    for state in State.query.all():
        if slugify(state.name) == slug:
            return state
    return None


def _available(type_key):
    """States that actually have uploaded data for an election type."""
    rows = (db.session.query(Election.state_id)
            .filter(Election.election_type == type_key)
            .distinct().all())
    states = [State.query.get(r[0]) for r in rows if r[0] is not None]
    return sorted([s for s in states if s.name.lower() != 'india'], key=lambda s: s.name)


@dashboard_bp.route('/')
def index():
    stats = global_stats()
    elections = Election.query.order_by(Election.created_at.desc()).all()
    return render_template('index.html', stats=stats, elections=elections, slugify=slugify)


@dashboard_bp.route('/about')
def about():
    return render_template('about.html')


@dashboard_bp.route('/states')
def states_page():
    items = []
    for state in State.query.order_by(State.name).all():
        if state.name.lower() == 'india':
            continue
        count = Election.query.filter_by(state_id=state.id).count()
        if count:
            items.append({'state': state, 'slug': slugify(state.name), 'count': count})
    return render_template('states.html', items=items)


@dashboard_bp.route('/lok-sabha')
@dashboard_bp.route('/vidhan-sabha')
def browse():
    type_key = 'lok_sabha' if request.path == '/lok-sabha' else 'vidhan_sabha'
    states = _available(type_key)
    selected_slug = request.args.get('state')
    selected_state = _find_state_by_slug(selected_slug) if selected_slug else None

    years = []
    if selected_state:
        years = sorted({e.year for e in Election.query.filter_by(
            election_type=type_key, state_id=selected_state.id).all()}, reverse=True)

    national_years = []
    if type_key == 'lok_sabha':
        national_years = sorted({e.year for e in Election.query.filter_by(
            election_type='lok_sabha').all()}, reverse=True)

    return render_template('browse.html',
                           type_key=type_key,
                           type_label=ELECTION_TYPES[type_key],
                           states=states,
                           selected_state=selected_state,
                           selected_slug=selected_slug,
                           years=years,
                           national_years=national_years,
                           slugify=slugify)


def _election_or_404(type_key, year, state_slug=None):
    year = int(year)
    query = Election.query.filter_by(election_type=type_key, year=year)
    if state_slug:
        state = _find_state_by_slug(state_slug)
        if not state:
            abort(404)
        query = query.filter_by(state_id=state.id)
    election = query.first()
    if not election:
        abort(404)
    return election


def _render_dashboard(elections, type_key, year):
    """Render the ONE reusable dashboard template for any election or aggregate."""
    ids = [e.id for e in elections]
    if Result.query.filter(Result.election_id.in_(ids)).count() == 0:
        return render_template('empty_dashboard.html', election=elections[0])

    code_label = 'PC Code' if type_key == 'lok_sabha' else 'AC Code'
    template = 'loksabha.html' if type_key == 'lok_sabha' else 'vidhan_sabha.html'

    if type_key == 'lok_sabha':
        title = f'LOK SABHA ELECTION {year} DASHBOARD'
        if len(elections) > 1:
            subtitle = 'All States · Parliamentary Constituencies'
        else:
            subtitle = f'{elections[0].state.name} · Parliamentary Constituencies'
    else:
        state_name = elections[0].state.name
        title = f'{state_name.upper()} VIDHAN SABHA ELECTION {year} DASHBOARD'
        subtitle = 'Assembly Constituencies · Vidhan Sabha'

    return render_template(template,
                           election=elections[0],
                           election_ids=','.join(str(i) for i in ids),
                           dash_title=title,
                           dash_subtitle=subtitle,
                           code_label=code_label,
                           slugify=slugify)


@dashboard_bp.route('/dashboard/lok-sabha/<int:year>')
def lok_sabha_dashboard(year):
    """National aggregate view: combines every uploaded Lok Sabha election of the year."""
    elections = Election.query.filter_by(election_type='lok_sabha', year=year).all()
    if not elections:
        abort(404)
    return _render_dashboard(elections, 'lok_sabha', year)


# ------------------------------------------------------- party-wise summaries
def _render_summary(elections, type_key, year):
    """Party-wise seat summary for a year (any state / national aggregate)."""
    if not elections:
        abort(404)
    ids = [e.id for e in elections]
    if Result.query.filter(Result.election_id.in_(ids)).count() == 0:
        abort(404)

    data = build_dashboard_data(elections)
    multi = len(elections) > 1

    if type_key == 'lok_sabha':
        title = f'LOK SABHA ELECTION {year} — PARTY-WISE RESULTS'
        subtitle = 'All States · Parliamentary Constituencies' if multi \
            else f'{elections[0].state.name} · Parliamentary Constituencies'
        dashboard_url = f'/dashboard/lok-sabha/{year}' if multi \
            else f'/dashboard/lok-sabha/{slugify(elections[0].state.name)}/{year}'
    else:
        title = f'{elections[0].state.name.upper()} VIDHAN SABHA ELECTION {year} — PARTY-WISE RESULTS'
        subtitle = 'Assembly Constituencies · Vidhan Sabha'
        dashboard_url = f'/dashboard/vidhan-sabha/{slugify(elections[0].state.name)}/{year}'

    return render_template('year_summary.html',
                           title=title, subtitle=subtitle,
                           dashboard_url=dashboard_url,
                           payload=data, slugify=slugify)


@dashboard_bp.route('/summary/lok-sabha/<int:year>')
def lok_sabha_summary(year):
    elections = Election.query.filter_by(election_type='lok_sabha', year=year).all()
    return _render_summary(elections, 'lok_sabha', year)


@dashboard_bp.route('/summary/lok-sabha/<state_slug>/<int:year>')
def lok_sabha_state_summary(state_slug, year):
    election = _election_or_404('lok_sabha', year, state_slug)
    return _render_summary([election], 'lok_sabha', year)


@dashboard_bp.route('/summary/vidhan-sabha/<state_slug>/<int:year>')
def vidhan_sabha_summary(state_slug, year):
    election = _election_or_404('vidhan_sabha', year, state_slug)
    return _render_summary([election], 'vidhan_sabha', year)


@dashboard_bp.route('/dashboard/lok-sabha/<state_slug>/<int:year>')
def lok_sabha_state_dashboard(state_slug, year):
    election = _election_or_404('lok_sabha', year, state_slug)
    return _render_dashboard([election], 'lok_sabha', year)


@dashboard_bp.route('/dashboard/vidhan-sabha/<state_slug>/<int:year>')
def vidhan_sabha_dashboard(state_slug, year):
    election = _election_or_404('vidhan_sabha', year, state_slug)
    return _render_dashboard([election], 'vidhan_sabha', year)


def _constituency_page(elections, election_type, year, code):
    for election in elections:
        detail = constituency_detail(election, code)
        if detail:
            return render_template('constituency.html', election=election, detail=detail,
                                   slugify=slugify)
    abort(404)


@dashboard_bp.route('/dashboard/vidhan-sabha/<state_slug>/<int:year>/<code>')
def vidhan_sabha_constituency(state_slug, year, code):
    election = _election_or_404('vidhan_sabha', year, state_slug)
    return _constituency_page([election], 'vidhan_sabha', year, code)


@dashboard_bp.route('/dashboard/lok-sabha/<state_slug>/<int:year>/<code>')
def lok_sabha_constituency(state_slug, year, code):
    election = _election_or_404('lok_sabha', year, state_slug)
    return _constituency_page([election], 'lok_sabha', year, code)


@dashboard_bp.route('/dashboard/lok-sabha/<int:year>/<code>')
def lok_sabha_national_constituency(year, code):
    elections = Election.query.filter_by(election_type='lok_sabha', year=year).all()
    if not elections:
        abort(404)
    return _constituency_page(elections, 'lok_sabha', year, code)
