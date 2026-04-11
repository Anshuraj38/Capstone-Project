from flask import Flask, render_template, request, session, redirect, url_for
from db import Database
app = Flask(__name__)

app.secret_key = 'some_random_secret_key'

dbo = Database()

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    name = session.get('name', 'User')
    return render_template('dashboard.html', user_name=name)

@app.route('/perform_registration' , methods=['POST'])
def perform_registration():
    name = request.form.get('username')
    email = request.form.get('user_ka_email')
    password = request.form.get('user_ka_password')
    
    response = dbo.insert(name, email, password)

    if response:
        session['name'] = name
        session['email'] = email
        return redirect(url_for('dashboard'))
    else:
        return "Email already existed"

@app.route('/perform_login', methods=['POST'])
def perform_login():
    email = request.form.get('email')
    password = request.form.get('password')

    user_name = dbo.validate(email, password)
    if user_name:
        session['name'] = user_name
        session['email'] = email
        return redirect(url_for('dashboard'))
    else:
        return "Invalid email or password"

app.run(debug=True)