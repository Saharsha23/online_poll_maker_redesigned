from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/flask_poll_maker_1'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize database
def init_db():
    with app.app_context():
        try:
            db.create_all()  # This will create the database if it doesn't exist
            print("Database tables created successfully!")
        except Exception as e:
            print(f"Error creating database tables: {str(e)}")
            raise

# Drop all tables and recreate them
with app.app_context():
    db.drop_all()
    db.create_all()

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    polls = db.relationship('Poll', backref='creator', lazy=True)
    votes = db.relationship('Vote', backref='voter', lazy=True)

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    options = db.relationship('PollOption', backref='poll', lazy=True, cascade='all, delete-orphan')
    votes = db.relationship('Vote', backref='poll', lazy=True)

class PollOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    votes = db.relationship('Vote', backref='option', lazy=True)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('poll_option.id'), nullable=False)
    voted_at = db.Column(db.DateTime, default=db.func.current_timestamp())

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
@login_required
def index():
    polls = Poll.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', polls=polls)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_poll():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        options = request.form.getlist('options')
        
        if len(options) < 2:
            flash('A poll must have at least 2 options.', 'error')
            return redirect(url_for('create_poll'))
        
        poll = Poll(title=title, description=description, user_id=current_user.id)
        db.session.add(poll)
        db.session.commit()
        
        for option_text in options:
            option = PollOption(text=option_text, poll_id=poll.id)
            db.session.add(option)
        
        db.session.commit()
        flash('Poll created successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('create_poll.html')

@app.route('/poll/<int:poll_id>')
def view_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    
    if not current_user.is_authenticated:
        flash('Please login to view and vote on this poll.', 'info')
        return redirect(url_for('login', next=url_for('view_poll', poll_id=poll_id)))
    
    user_vote = Vote.query.filter_by(user_id=current_user.id, poll_id=poll_id).first()
    return render_template('view_poll.html', poll=poll, user_vote=user_vote)

@app.route('/vote/<int:poll_id>', methods=['POST'])
@login_required
def vote(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    option_id = request.form.get('option')
    
    if not option_id:
        flash('Please select an option to vote.', 'error')
        return redirect(url_for('view_poll', poll_id=poll_id))
    
    # Check if user has already voted
    existing_vote = Vote.query.filter_by(user_id=current_user.id, poll_id=poll_id).first()
    if existing_vote:
        flash('You have already voted on this poll.', 'error')
        return redirect(url_for('view_poll', poll_id=poll_id))
    
    vote = Vote(user_id=current_user.id, poll_id=poll_id, option_id=option_id)
    db.session.add(vote)
    db.session.commit()
    
    flash('Your vote has been recorded!', 'success')
    return redirect(url_for('view_poll', poll_id=poll_id))

@app.route('/my_polls')
@login_required
def my_polls():
    created_polls = Poll.query.filter_by(user_id=current_user.id).all()
    voted_polls = Poll.query.join(Vote).filter(Vote.user_id == current_user.id).all()
    return render_template('my_polls.html', created_polls=created_polls, voted_polls=voted_polls)

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 