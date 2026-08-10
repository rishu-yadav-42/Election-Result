"""Admin routes: dashboard, election management and the upload pipeline
(upload file -> preview -> column mapping -> validation -> import)."""

import json
import os
import uuid

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, current_app, abort)

from models.models import db, Election, State, Result, Upload, Constituency, Candidate
from routes.auth import admin_required
from services import data_processor
from services.data_processor import SYSTEM_COLUMNS, SUMMARY_COLUMNS
from services.validation import validate_dataset
from services.statistics import global_stats

admin_bp = Blueprint('admin', __name__)

MIN_YEAR, MAX_YEAR = 1950, 2100


def _parse_year(value):
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if MIN_YEAR <= year <= MAX_YEAR:
        return year
    return None


@admin_bp.route('/admin')
@admin_required
def dashboard():
    stats = global_stats()
    elections = Election.query.order_by(Election.created_at.desc()).limit(5).all()
    recent_uploads = (Upload.query.order_by(Upload.uploaded_at.desc()).limit(5)
                      .all())
    return render_template('admin.html', stats=stats, elections=elections,
                           recent_uploads=recent_uploads)


# ---------------------------------------------------------------- add election
@admin_bp.route('/admin/add-election', methods=['GET', 'POST'])
@admin_required
def add_election():
    states = State.query.order_by(State.name).all()

    if request.method == 'POST':
        election_type = request.form.get('election_type')
        state_id = request.form.get('state_id')
        year = _parse_year(request.form.get('year'))

        if election_type not in ('lok_sabha', 'vidhan_sabha'):
            flash('Please select a valid election type (Lok Sabha or Vidhan Sabha).', 'danger')
        elif not year:
            flash(f'Please enter a valid election year ({MIN_YEAR}-{MAX_YEAR}).', 'danger')
        elif not state_id:
            flash('Please select a state.', 'danger')
        else:
            state = State.query.get(state_id)
            election, created = data_processor.get_or_create_election(election_type, state, year)
            db.session.commit()
            if created:
                flash(f'Election "{election.name}" created. You can now upload its dataset.', 'success')
            else:
                flash(f'Election "{election.name}" already exists.', 'info')
            return redirect(url_for('admin.upload', election_id=election.id))

    return render_template('add_election.html', states=states)


# ------------------------------------------------------------------- upload
@admin_bp.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def upload():
    states = State.query.order_by(State.name).all()
    elections = Election.query.order_by(Election.created_at.desc()).all()

    if request.method == 'GET':
        return render_template('upload.html', states=states, elections=elections,
                               preselected=request.args.get('election_id'))

    # ---- POST: receive file, parse it and go to column mapping ----
    election_type = request.form.get('election_type')
    state_id = request.form.get('state_id')
    year = _parse_year(request.form.get('year'))
    file = request.files.get('dataset')
    replace = request.form.get('replace') == '1'

    if election_type not in ('lok_sabha', 'vidhan_sabha'):
        flash('Please select a valid election type.', 'danger')
    elif not state_id:
        flash('Please select a state.', 'danger')
    elif not year:
        flash(f'Please enter a valid election year ({MIN_YEAR}-{MAX_YEAR}).', 'danger')
    elif not file or not file.filename:
        flash('Please choose a file to upload.', 'danger')
    elif not data_processor.allowed_file(file.filename):
        flash('Unsupported file type. Allowed: .csv, .xlsx, .xls', 'danger')
    else:
        filename = data_processor.secure_name(file.filename)
        temp_name = f'{uuid.uuid4().hex}_{filename}'
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_name)
        file.save(temp_path)

        if os.path.getsize(temp_path) == 0:
            os.remove(temp_path)
            flash('The uploaded file is empty.', 'danger')
            return redirect(url_for('admin.upload'))

        try:
            df = data_processor.read_dataset(temp_path)
        except Exception as exc:
            os.remove(temp_path)
            if 'No columns to parse' in str(exc):
                flash('The uploaded file is empty.', 'danger')
            else:
                flash(f'Could not read the file: {exc}', 'danger')
            return redirect(url_for('admin.upload'))

        if df.empty:
            os.remove(temp_path)
            flash('The uploaded file is empty.', 'danger')
            return redirect(url_for('admin.upload'))

        columns = [str(c) for c in df.columns]
        chosen_format = request.form.get('dataset_format', 'auto')
        dataset_format = data_processor.detect_format(columns) if chosen_format == 'auto' \
            else ('summary' if chosen_format == 'summary' else 'candidate')
        system_columns = SUMMARY_COLUMNS if dataset_format == 'summary' else SYSTEM_COLUMNS

        session['upload_staging'] = {
            'temp_name': temp_name,
            'original_filename': filename,
            'election_type': election_type,
            'state_id': int(state_id),
            'year': year,
            'replace': replace,
            'dataset_format': dataset_format,
            'mapping': data_processor.suggest_mapping(columns, dataset_format),
        }

        preview = df.head(10).fillna('').astype(str).values.tolist()
        return render_template('mapping.html',
                               columns=columns,
                               system_columns=system_columns,
                               dataset_format=dataset_format,
                               suggested=data_processor.suggest_mapping(columns, dataset_format),
                               preview=preview,
                               total_rows=len(df),
                               filename=filename)

    return redirect(url_for('admin.upload'))


@admin_bp.route('/admin/upload/validate', methods=['POST'])
@admin_required
def upload_validate():
    staging = session.get('upload_staging')
    if not staging:
        flash('Upload session expired. Please upload the file again.', 'warning')
        return redirect(url_for('admin.upload'))

    columns = json.loads(request.form.get('columns', '[]'))
    mapping = {col: request.form.get(f'map__{i}', '') for i, col in enumerate(columns)}

    dataset_format = staging.get('dataset_format', 'candidate')
    required = {'constituency_code', 'constituency_name', 'winner', 'winner_party', 'winner_votes'} \
        if dataset_format == 'summary' \
        else {'constituency_code', 'constituency_name', 'candidate', 'party', 'votes'}
    if not required.issubset(set(mapping.values())):
        missing = required - set(mapping.values())
        flash('Please map all required columns: ' + ', '.join(sorted(missing)), 'danger')
        return redirect(url_for('admin.upload'))

    staging['mapping'] = mapping
    session['upload_staging'] = staging

    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], staging['temp_name'])
    df = data_processor.read_dataset(temp_path)
    df = data_processor.apply_mapping(df, mapping)
    if dataset_format == 'summary':
        df = data_processor.expand_summary(df)
    report = validate_dataset(df)

    if report['valid'] == 0:
        flash('No valid records found. Please fix the mapping or the file.', 'danger')

    return render_template('validate.html', report=report, filename=staging['original_filename'])


@admin_bp.route('/admin/upload/import', methods=['POST'])
@admin_required
def upload_import():
    staging = session.get('upload_staging')
    if not staging:
        flash('Upload session expired. Please upload the file again.', 'warning')
        return redirect(url_for('admin.upload'))

    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], staging['temp_name'])
    if not os.path.exists(temp_path):
        flash('Uploaded file no longer available. Please upload again.', 'danger')
        return redirect(url_for('admin.upload'))

    state = State.query.get(staging['state_id'])
    election, created = data_processor.get_or_create_election(
        staging['election_type'], state, staging['year'])

    df = data_processor.read_dataset(temp_path)
    df = data_processor.apply_mapping(df, staging['mapping'])
    if staging.get('dataset_format') == 'summary':
        df = data_processor.expand_summary(df)
    report = validate_dataset(df)

    if report['valid'] == 0:
        flash('No valid records to import.', 'danger')
        return redirect(url_for('admin.upload'))

    if staging['replace'] and not created:
        data_processor.clear_election_data(election)

    try:
        count = data_processor.import_data(election, report['df'], staging['original_filename'])
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Import failed')
        flash(f'Database error while importing: {exc}. Nothing was saved.', 'danger')
        return redirect(url_for('admin.upload'))

    os.remove(temp_path)
    session.pop('upload_staging', None)

    flash(f'Imported {count} records into "{election.name}". Dashboard is now live!', 'success')
    return redirect(url_for('admin.elections'))


@admin_bp.route('/admin/upload/cancel')
@admin_required
def upload_cancel():
    staging = session.pop('upload_staging', None)
    if staging:
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], staging['temp_name'])
        if os.path.exists(temp_path):
            os.remove(temp_path)
    flash('Upload cancelled.', 'info')
    return redirect(url_for('admin.upload'))


# --------------------------------------------------------- manage elections
@admin_bp.route('/admin/elections')
@admin_required
def elections():
    items = Election.query.order_by(Election.created_at.desc()).all()
    details = []
    for e in items:
        details.append({
            'election': e,
            'records': Result.query.filter_by(election_id=e.id).count(),
            'constituencies': Constituency.query.filter_by(election_id=e.id).count(),
        })
    return render_template('elections.html', details=details)


@admin_bp.route('/admin/elections/<int:election_id>/delete', methods=['POST'])
@admin_required
def delete_election(election_id):
    election = Election.query.get_or_404(election_id)
    name = election.name
    db.session.delete(election)
    db.session.commit()
    flash(f'Election "{name}" and all of its data were deleted.', 'success')
    return redirect(url_for('admin.elections'))


# ------------------------------------------------------------ view/edit data
@admin_bp.route('/admin/elections/<int:election_id>/data')
@admin_required
def view_data(election_id):
    election = Election.query.get_or_404(election_id)
    page = max(1, request.args.get('page', 1, type=int))
    pagination = (Result.query
                  .filter_by(election_id=election.id)
                  .order_by(Result.constituency_id, Result.rank)
                  .paginate(page=page, per_page=50, error_out=False))
    return render_template('view_data.html', election=election, pagination=pagination)


@admin_bp.route('/admin/records/<int:record_id>/edit', methods=['POST'])
@admin_required
def edit_record(record_id):
    record = Result.query.get_or_404(record_id)
    votes = request.form.get('votes', type=int)
    rank = request.form.get('rank', type=int)
    if votes is not None and votes >= 0:
        record.votes = votes
    if rank is not None and rank >= 1:
        record.rank = rank
    db.session.commit()
    flash('Record updated.', 'success')
    return redirect(request.referrer or url_for('admin.elections'))


@admin_bp.route('/admin/records/<int:record_id>/delete', methods=['POST'])
@admin_required
def delete_record(record_id):
    record = Result.query.get_or_404(record_id)
    election_id = record.election_id
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted.', 'success')
    return redirect(request.referrer or url_for('admin.view_data', election_id=election_id))


# ------------------------------------------------------------ upload history
@admin_bp.route('/admin/uploads')
@admin_required
def upload_history():
    uploads = Upload.query.order_by(Upload.uploaded_at.desc()).all()
    return render_template('uploads.html', uploads=uploads)
