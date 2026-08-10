from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

ELECTION_TYPES = {
    'lok_sabha': 'Lok Sabha',
    'vidhan_sabha': 'Vidhan Sabha',
}


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='admin')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class State(db.Model):
    __tablename__ = 'states'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Election(db.Model):
    __tablename__ = 'elections'
    id = db.Column(db.Integer, primary_key=True)
    election_type = db.Column(db.String(20), nullable=False, index=True)  # lok_sabha | vidhan_sabha
    year = db.Column(db.Integer, nullable=False, index=True)
    state_id = db.Column(db.Integer, db.ForeignKey('states.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    state = db.relationship('State', backref='elections')
    constituencies = db.relationship('Constituency', backref='election', cascade='all, delete-orphan')
    results = db.relationship('Result', backref='election', cascade='all, delete-orphan')
    uploads = db.relationship('Upload', backref='election', cascade='all, delete-orphan')

    @property
    def type_label(self):
        return ELECTION_TYPES.get(self.election_type, self.election_type)


class Constituency(db.Model):
    __tablename__ = 'constituencies'
    __table_args__ = (
        db.UniqueConstraint('election_id', 'code', name='uq_constituency_election_code'),
        db.Index('ix_constituency_code', 'code'),
        db.Index('ix_constituency_name', 'name'),
    )
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(10), default='AC')  # AC | PC


class Party(db.Model):
    __tablename__ = 'parties'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)


class Candidate(db.Model):
    __tablename__ = 'candidates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    party_id = db.Column(db.Integer, db.ForeignKey('parties.id'), nullable=False, index=True)

    party = db.relationship('Party', backref='candidates')


class Result(db.Model):
    __tablename__ = 'results'
    __table_args__ = (
        db.Index('ix_result_election', 'election_id'),
        db.Index('ix_result_constituency', 'constituency_id'),
        db.Index('ix_result_candidate', 'candidate_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False)
    constituency_id = db.Column(db.Integer, db.ForeignKey('constituencies.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    votes = db.Column(db.Integer, nullable=False, default=0)
    rank = db.Column(db.Integer, nullable=True)
    margin = db.Column(db.Integer, nullable=True)
    vote_percentage = db.Column(db.Float, nullable=True)
    is_winner = db.Column(db.Boolean, default=False)

    constituency = db.relationship('Constituency')
    candidate = db.relationship('Candidate')


class Upload(db.Model):
    __tablename__ = 'uploads'
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    record_count = db.Column(db.Integer, default=0)
