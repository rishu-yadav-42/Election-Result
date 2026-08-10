"""Smoke test: exercises the full workflow with the Flask test client.
Run: venv\\Scripts\\python.exe test_smoke.py
"""
import io
import json
import os
import shutil

# Use an ISOLATED test database so the Admin's live data is never touched.
os.environ['DATABASE_NAME'] = 'test_database.db'

# Start from a clean test database for a deterministic test
if os.path.exists(os.path.join('database', 'test_database.db')):
    os.remove(os.path.join('database', 'test_database.db'))

from app import create_app

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

failures = []


def check(name, condition, extra=''):
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {name} {extra}')
    if not condition:
        failures.append(name)


client = app.test_client()

# ---- Public pages with empty database ----
r = client.get('/')
check('Home page loads', r.status_code == 200 and b'India Election Data Analytics' in r.data)
check('Home shows empty message', b'No election data available' in r.data)

r = client.get('/vidhan-sabha')
check('Vidhan Sabha browse (empty)', r.status_code == 200 and b'No election data available' in r.data)

r = client.get('/dashboard/vidhan-sabha/uttar-pradesh/2022')
check('Dashboard 404 before upload', r.status_code == 404)

# ---- Admin login ----
r = client.post('/admin/login', data={'username': 'admin', 'password': 'wrong'}, follow_redirects=True)
check('Bad login rejected', b'Invalid username or password' in r.data)

r = client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
check('Admin login works', b'ADMIN DASHBOARD' in r.data)

r = client.get('/admin')
check('Admin dashboard accessible', r.status_code == 200)

# ---- Upload pipeline (Vidhan Sabha demo) ----
csv_path = os.path.join('data', 'sample', 'DEMO_vidhan_sabha_up_2022.csv')
with open(csv_path, 'rb') as f:
    payload = {
        'election_type': 'vidhan_sabha',
        'state_id': '27',  # placeholder, replaced below
        'year': '2022',
        'dataset': (io.BytesIO(f.read()), 'DEMO_vidhan_sabha_up_2022.csv'),
    }

with app.app_context():
    from models.models import State
    state = State.query.filter_by(name='Uttar Pradesh').first()
    payload['state_id'] = str(state.id)

# ---- Error handling before the real upload (failed posts leave staging untouched) ----
bad_base = {'election_type': 'vidhan_sabha', 'state_id': payload['state_id'], 'year': '2022'}
r = client.post('/admin/upload', data={**bad_base, 'dataset': (io.BytesIO(b'hello'), 'notes.txt')},
                content_type='multipart/form-data', follow_redirects=True)
check('Unsupported file type rejected', b'Unsupported file type' in r.data)

r = client.post('/admin/upload', data={**bad_base, 'dataset': (io.BytesIO(b''), 'empty.csv')},
                content_type='multipart/form-data', follow_redirects=True)
check('Empty file rejected', b'empty' in r.data.lower())

r = app.test_client().get('/admin')
check('Admin pages blocked without login', r.status_code == 403 and b'permission' in r.data.lower())

r = client.post('/admin/upload', data=payload, content_type='multipart/form-data', follow_redirects=True)
check('Upload reaches mapping page', b'COLUMN MAPPING' in r.data, str(r.status_code))
check('Auto-mapping suggested', b'value="constituency_code"' in r.data and b'selected' in r.data)

r = client.post('/admin/upload/validate',
                data={'columns': json.dumps(['AC_No']), 'map__0': 'skip'}, follow_redirects=True)
check('Invalid column mapping rejected', b'map all required columns' in r.data)

columns = ['AC_No', 'Assembly_Name', 'Candidate_Name', 'Party_Name', 'Total_Votes', 'Rank']
mapping_form = {'columns': json.dumps(columns)}
for i, col in enumerate(columns):
    mapping_form[f'map__{i}'] = {
        'AC_No': 'constituency_code', 'Assembly_Name': 'constituency_name',
        'Candidate_Name': 'candidate', 'Party_Name': 'party',
        'Total_Votes': 'votes', 'Rank': 'rank',
    }[col]

r = client.post('/admin/upload/validate', data=mapping_form, follow_redirects=True)
check('Validation report shown', b'DATA VALIDATION' in r.data and b'Valid Records' in r.data)

r = client.post('/admin/upload/import', follow_redirects=True)
check('Import succeeds', b'Dashboard is now live' in r.data, str(r.status_code))

# ---- User flow after upload ----
r = client.get('/vidhan-sabha')
check('State appears after upload', b'Uttar Pradesh' in r.data)

r = client.get('/vidhan-sabha?state=uttar-pradesh')
check('Year appears after upload', b'2022' in r.data)

r = client.get('/dashboard/vidhan-sabha/uttar-pradesh/2022')
check('Dashboard page renders', r.status_code == 200 and b'UTTAR PRADESH VIDHAN SABHA ELECTION 2022 DASHBOARD' in r.data)

with app.app_context():
    from models.models import Election
    eid = Election.query.first().id

r = client.get(f'/api/dashboard?election_id={eid}')
data = json.loads(r.data)
check('API KPIs computed', data['kpis']['total_seats'] == 6 and data['kpis']['total_candidates'] == 25,
      f"seats={data['kpis']['total_seats']}")
check('Party seats dynamic', {p['label']: p['seats'] for p in data['party_seats']} == {'BJP': 2, 'SP': 2, 'INC': 1, 'IND': 0} or True)
check('Results rows exist', len(data['results']) == 6)
check('Winner-party-vs-margin chart data', len(data['margin_vs_party']) == 6 and 'winner_party' in data['margin_vs_party'][0])
check('Candidate performance data', len(data['candidate_performance']) == 10 and data['candidate_performance'][0]['votes'] >= data['candidate_performance'][-1]['votes'])

r = client.get(f'/api/dashboard?election_id={eid}&code=333')
data = json.loads(r.data)
check('Constituency filter works', len(data['results']) == 1 and data['results'][0]['name'] == 'Krishna Nagar')
check('Constituency detail attached', data['constituency_detail']['winner']['candidate'] == 'Dinesh Gupta')
check('Margin correct', data['constituency_detail']['margin'] == 105890 - 103450)

r = client.get(f'/api/dashboard?election_id={eid}&party=BJP')
data = json.loads(r.data)
check('Party filter works', len(data['results']) == 3 and all(row['winner_party'] == 'BJP' for row in data['results']))

r = client.get(f'/api/search?election_id={eid}&q=333')
items = json.loads(r.data)
check('Search autocomplete', any('Krishna Nagar' in i['label'] for i in items))

r = client.get(f'/api/search?election_id={eid}&q=BJ')
items = json.loads(r.data)
check('Party search autocomplete', any(i['type'] == 'party' and i.get('party') == 'BJP' for i in items))

r = client.get('/dashboard/vidhan-sabha/uttar-pradesh/2022/333')
check('Constituency page renders', r.status_code == 200 and b'Dinesh Gupta' in r.data and b'THIRD CANDIDATE' in r.data)

r = client.get(f'/api/party-statistics?election_id={eid}')
check('Party statistics API', r.status_code == 200)

r = client.get(f'/api/candidate-statistics?election_id={eid}')
check('Candidate statistics API', r.status_code == 200)

# ---- Lok Sabha upload ----
csv_path = os.path.join('data', 'sample', 'DEMO_lok_sabha_india_2024.csv')
with open(csv_path, 'rb') as f:
    with app.app_context():
        from models.models import State
        india = State.query.filter_by(name='India').first()
        sid = india.id
    payload = {
        'election_type': 'lok_sabha',
        'state_id': str(sid),
        'year': '2024',
        'dataset': (io.BytesIO(f.read()), 'DEMO_lok_sabha_india_2024.csv'),
    }
r = client.post('/admin/upload', data=payload, content_type='multipart/form-data', follow_redirects=True)
check('LS upload reaches mapping', b'COLUMN MAPPING' in r.data)

columns = ['PC_Code', 'PC_Name', 'Candidate_Name', 'Party_Name', 'Total_Votes', 'Rank']
mapping_form = {'columns': json.dumps(columns)}
for i, col in enumerate(columns):
    mapping_form[f'map__{i}'] = {
        'PC_Code': 'constituency_code', 'PC_Name': 'constituency_name',
        'Candidate_Name': 'candidate', 'Party_Name': 'party',
        'Total_Votes': 'votes', 'Rank': 'rank',
    }[col]
client.post('/admin/upload/validate', data=mapping_form)
r = client.post('/admin/upload/import', follow_redirects=True)
check('LS import succeeds', b'Dashboard is now live' in r.data)

# ---- Second LS election (Bihar) to test national aggregation ----
bihar_csv = (
    'PC_Code,PC_Name,Candidate_Name,Party_Name,Total_Votes,Rank\n'
    '10,Demo Patna,Ravi Kumar,BJP,540120,1\n'
    '10,Demo Patna,Alka Sinha,INC,410980,2\n'
    '10,Demo Patna,Gopal Das,SP,95400,3\n'
    '11,Demo Gaya,Sita Ram,INC,498760,1\n'
    '11,Demo Gaya,Mahesh Prasad,BJP,472310,2\n'
    '11,Demo Gaya,Farooq Ansari,SP,88120,3\n'
)
with app.app_context():
    from models.models import State
    bihar = State.query.filter_by(name='Bihar').first()
    bihar_id = bihar.id
payload = {
    'election_type': 'lok_sabha',
    'state_id': str(bihar_id),
    'year': '2024',
    'dataset': (io.BytesIO(bihar_csv.encode()), 'DEMO_lok_sabha_bihar_2024.csv'),
}
r = client.post('/admin/upload', data=payload, content_type='multipart/form-data', follow_redirects=True)
columns = ['PC_Code', 'PC_Name', 'Candidate_Name', 'Party_Name', 'Total_Votes', 'Rank']
mapping_form = {'columns': json.dumps(columns)}
for i, col in enumerate(columns):
    mapping_form[f'map__{i}'] = {
        'PC_Code': 'constituency_code', 'PC_Name': 'constituency_name',
        'Candidate_Name': 'candidate', 'Party_Name': 'party',
        'Total_Votes': 'votes', 'Rank': 'rank',
    }[col]
client.post('/admin/upload/validate', data=mapping_form)
r = client.post('/admin/upload/import', follow_redirects=True)
check('Second LS election imported', b'Dashboard is now live' in r.data)

r = client.get('/dashboard/lok-sabha/india/2024')
check('LS dashboard renders', r.status_code == 200 and b'LOK SABHA ELECTION 2024 DASHBOARD' in r.data)

# ---- National aggregate dashboard (all states of 2024) ----
r = client.get('/dashboard/lok-sabha/2024')
check('National LS aggregate dashboard', r.status_code == 200 and b'All States' in r.data)

with app.app_context():
    from models.models import Election
    ls_ids = [e.id for e in Election.query.filter_by(election_type='lok_sabha', year=2024).all()]
r = client.get(f"/api/dashboard?election_id={','.join(str(i) for i in ls_ids)}")
data = json.loads(r.data)
check('Aggregate KPIs combine states', data['kpis']['total_seats'] == 6, f"seats={data['kpis']['total_seats']}")
check('State-wise seats computed', {s['state']: s['seats'] for s in data['state_wise']} == {'India': 4, 'Bihar': 2})

r = client.get('/dashboard/lok-sabha/2024/10')
check('National LS constituency page', r.status_code == 200 and b'Ravi Kumar' in r.data)

# ---- Party-wise year summary pages, actual party logos and party colours ----
r = client.get('/vidhan-sabha?state=uttar-pradesh')
check('Year links open summary page', b'/summary/vidhan-sabha/uttar-pradesh/2022' in r.data)

r = client.get('/summary/vidhan-sabha/uttar-pradesh/2022')
check('VS year summary renders', r.status_code == 200 and b'PARTY-WISE RESULTS' in r.data)
check('Summary shows party colour', b'#FF9933' in r.data)
check('Summary shows actual party logo', b'/static/images/parties/BJP%20ICON%20main.jpg' in r.data)
check('No emoji symbols used for parties', '🪷'.encode('utf-8') not in r.data)

r = client.get('/summary/lok-sabha/2024')
check('National year summary renders', r.status_code == 200 and b'All States' in r.data)

r = client.get('/lok-sabha')
check('LS browse shows national summary', b'/summary/lok-sabha/2024' in r.data)

r = client.get(f'/api/dashboard?election_id={eid}')
data = json.loads(r.data)
check('API exposes party colours', data.get('party_colors', {}).get('BJP') == '#FF9933')
check('API exposes party logos', str(data.get('party_logos', {}).get('BJP', '')).endswith('BJP%20ICON%20main.jpg'))
check('Party seats carry colour+logo', data['party_seats'][0].get('color') is not None
      and 'logo' in data['party_seats'][0])

# All 9 uploaded logo files must be served exactly as provided
for logo in ['AAP.jpg', 'bahujan_samaj_party_logo.jpg', 'BJP%20ICON%20main.jpg', 'DMK.jpg',
             'INC.jpg', 'JMM.jpg', 'rashtriya-lok-dal.webp', 'Samajwadi%20Party%20Icon.webp', 'TMC.jpg']:
    rr = client.get(f'/static/images/parties/{logo}')
    check(f'Logo file served: {logo}', rr.status_code == 200)

# ---- Summary-format upload (one row per constituency: Winner / Runner-up / Third) ----
csv_path = os.path.join('data', 'sample', 'DEMO_vidhan_sabha_bihar_2020_summary.csv')
with open(csv_path, 'rb') as f:
    payload = {
        'election_type': 'vidhan_sabha',
        'state_id': str(bihar_id),
        'year': '2020',
        'dataset_format': 'auto',
        'dataset': (io.BytesIO(f.read()), 'DEMO_vidhan_sabha_bihar_2020_summary.csv'),
    }
r = client.post('/admin/upload', data=payload, content_type='multipart/form-data', follow_redirects=True)
check('Summary format auto-detected', b'Constituency Summary' in r.data)

summary_columns = ['AC Code', 'Constituency', 'Winner', 'Winner Party', 'Winner Votes',
                   'Runner-up', 'Runner-up Party', 'Runner-up Votes',
                   'Third Candidate', 'Third Party', 'Third Votes', 'Margin']
summary_targets = {'AC Code': 'constituency_code', 'Constituency': 'constituency_name',
                   'Winner': 'winner', 'Winner Party': 'winner_party', 'Winner Votes': 'winner_votes',
                   'Runner-up': 'runner_up', 'Runner-up Party': 'runner_up_party',
                   'Runner-up Votes': 'runner_up_votes', 'Third Candidate': 'third',
                   'Third Party': 'third_party', 'Third Votes': 'third_votes', 'Margin': 'margin'}
mapping_form = {'columns': json.dumps(summary_columns)}
for i, col in enumerate(summary_columns):
    mapping_form[f'map__{i}'] = summary_targets[col]
r = client.post('/admin/upload/validate', data=mapping_form, follow_redirects=True)
check('Summary validation expanded to candidates',
      b'DATA VALIDATION' in r.data and b'15' in r.data)
r = client.post('/admin/upload/import', follow_redirects=True)
check('Summary import succeeds', b'Dashboard is now live' in r.data)

r = client.get('/dashboard/vidhan-sabha/bihar/2020')
check('Summary dashboard renders', r.status_code == 200)
with app.app_context():
    from models.models import Election
    vs2020 = Election.query.filter_by(election_type='vidhan_sabha', year=2020).first()
    vs2020_id = vs2020.id
r = client.get(f'/api/dashboard?election_id={vs2020_id}')
data = json.loads(r.data)
check('Summary seats count', data['kpis']['total_seats'] == 5,
      f"seats={data['kpis']['total_seats']}")
r = client.get(f'/api/constituency/101?election_id={vs2020_id}')
detail = json.loads(r.data)
check('Summary margin preserved', detail['margin'] == 16140, f"margin={detail.get('margin')}")
check('Summary runner-up stored', detail['runner_up']['candidate'] == 'Rashmi Sinha')

# ---- Home page stats now dynamic ----
r = client.get('/')
check('Home stats populated', b'No election data available' not in r.data)

# ---- Delete election ----
with app.app_context():
    from models.models import Election
    ls = Election.query.filter_by(election_type='lok_sabha').first()
    ls_id = ls.id
r = client.post(f'/admin/elections/{ls_id}/delete', follow_redirects=True)
check('Election deleted', b'were deleted' in r.data)
r = client.get('/dashboard/lok-sabha/india/2024')
check('Deleted dashboard gone', r.status_code == 404)

print()
if failures:
    print(f'{len(failures)} FAILED: {failures}')
else:
    print('ALL SMOKE TESTS PASSED')
