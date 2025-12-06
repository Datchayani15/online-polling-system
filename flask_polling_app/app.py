from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from collections import Counter

app = Flask(__name__)
app.secret_key = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polling.db'
db = SQLAlchemy(app)

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(10))  # user/admin

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)

class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'))
    option_text = db.Column(db.String(100))

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    poll_id = db.Column(db.Integer)
    option_id = db.Column(db.Integer)

# ---------------- Routes ----------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please login.")
            return redirect('/login')
        user = User(username=username,email=email,password=password,role='user')
        db.session.add(user)
        try:
            db.session.commit()
            flash("Registered successfully!")
            return redirect('/login')
        except IntegrityError:
            db.session.rollback()
            flash("Email already registered.")
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password,request.form['password']):
            session['user_id'] = user.id
            session['role'] = user.role
            flash("Login successful!")
            return redirect('/dashboard')
        else:
            flash("Invalid credentials.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')
@app.route('/delete_option/<int:option_id>', methods=['POST'])
def delete_option(option_id):
    if session.get('role') != 'admin':
        return "Access Denied"

    option = Option.query.get(option_id)
    if not option:
        return "Option not found."

    # Delete all votes associated with this option
    Vote.query.filter_by(option_id=option.id).delete()

    # Delete the option itself
    db.session.delete(option)
    db.session.commit()
    return redirect(f'/edit_poll/{option.poll_id}')
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    user = User.query.get(session['user_id'])
    polls = Poll.query.all()
    return render_template('dashboard.html', polls=polls, user=user)

# ---------------- Admin Create Poll ----------------
@app.route('/create_poll', methods=['GET','POST'])
def create_poll():
    if session.get('role')!='admin':
        return "Access Denied"
    if request.method=='POST':
        title = request.form['title']
        description = request.form['description']
        options = request.form.getlist('options')
        poll = Poll(title=title,description=description,start_time=datetime.now(),end_time=datetime(2099,1,1))
        db.session.add(poll)
        db.session.commit()
        for opt in options:
            if opt.strip():
                db.session.add(Option(poll_id=poll.id, option_text=opt.strip()))
        db.session.commit()
        flash("Poll created successfully!")
        return redirect('/dashboard')
    return render_template('create_poll.html')

# ---------------- Admin Edit Poll ----------------
@app.route('/edit_poll/<int:poll_id>', methods=['GET', 'POST'])
def edit_poll(poll_id):
    if session.get('role') != 'admin':
        return "Access Denied"
    
    poll = Poll.query.get(poll_id)
    options = Option.query.filter_by(poll_id=poll_id).all()

    if request.method == 'POST':
        # Update poll title and description
        poll.title = request.form['title']
        poll.description = request.form['description']
        db.session.commit()

        # Update existing options or delete them
        for opt in options:
            if f'delete_{opt.id}' in request.form:
                db.session.delete(opt)
            else:
                opt.option_text = request.form.get(f'option_{opt.id}', opt.option_text)
        db.session.commit()

        # Add new options
        new_options = request.form.getlist('new_options')
        for opt_text in new_options:
            if opt_text.strip():
                db.session.add(Option(poll_id=poll.id, option_text=opt_text.strip()))
        db.session.commit()

        flash("Poll updated successfully!")
        return redirect('/dashboard')

    return render_template('edit_poll.html', poll=poll, options=options)
# ---------------- Admin Delete Poll ----------------
@app.route('/delete_poll/<int:poll_id>', methods=['POST'])
def delete_poll(poll_id):
    if session.get('role')!='admin':
        return "Access Denied"
    poll = Poll.query.get(poll_id)
    Option.query.filter_by(poll_id=poll.id).delete()
    Vote.query.filter_by(poll_id=poll.id).delete()
    db.session.delete(poll)
    db.session.commit()
    flash("Poll deleted!")
    return redirect('/dashboard')

# ---------------- Voting ----------------
@app.route('/vote/<int:poll_id>', methods=['GET','POST'])
def vote(poll_id):
    if 'user_id' not in session:
        return redirect('/login')
    poll = Poll.query.get(poll_id)
    options = Option.query.filter_by(poll_id=poll_id).all()
    if request.method=='POST':
        selected = int(request.form['option'])
        if not Vote.query.filter_by(user_id=session['user_id'],poll_id=poll_id).first():
            db.session.add(Vote(user_id=session['user_id'],poll_id=poll_id,option_id=selected))
            db.session.commit()
            flash("Vote submitted!")
        return redirect(f'/results/{poll_id}')
    return render_template('vote.html', poll=poll, options=options)

# ---------------- Results ----------------
@app.route('/results/<int:poll_id>')
def results(poll_id):
    poll = Poll.query.get(poll_id)
    options = Option.query.filter_by(poll_id=poll_id).all()
    votes = Vote.query.filter_by(poll_id=poll_id).all()
    vote_counts = Counter([v.option_id for v in votes])
    results_data = [(opt.option_text, vote_counts.get(opt.id,0)) for opt in options]
    return render_template('results.html', poll=poll, results=results_data)

# ---------------- DB Setup ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        admin_email = 'admin@example.com'
        existing_admin = User.query.filter_by(email=admin_email, role='admin').first()
        if not existing_admin:
            admin_user = User(username='admin', email=admin_email, password=generate_password_hash('adminpass'), role='admin')
            db.session.add(admin_user)
            try:
                db.session.commit()
                print("Admin created: admin@example.com / adminpass")
            except IntegrityError:
                db.session.rollback()
        else:
            print("Admin exists")
    app.run(debug=True)
