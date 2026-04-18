from flask import Flask, render_template, request, session, redirect, url_for, jsonify, make_response
from flask_login import logout_user
from db import Database
import os
from werkzeug.utils import secure_filename
app = Flask(__name__)

app.secret_key = 'some_random_secret_key'

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

dbo = Database()

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect(url_for('index'))
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
        session['logged_in'] = True
        return redirect(url_for('dashboard'))
    else:
        return "Email already exists"

@app.route('/perform_login', methods=['POST'])
def perform_login():
    email = request.form.get('email')
    password = request.form.get('password')

    user_name = dbo.validate(email, password)
    if user_name:
        session['name'] = user_name
        session['email'] = email
        session['logged_in'] = True
        return redirect(url_for('dashboard'))
    else:
        return "Invalid email or password"

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"})
        
    if file and (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # Returning dummy profile data to satisfy the dashboard.js rendering requirements
        return jsonify({
            "filename": filename,
            "profile": {
                "quality_score": 100, "rows": 0, "cols": 0, "missing": 0,
                "missing_pct": 0, "duplicates": 0, "schema_issues": 0,
                "columns": [], "sample": []
            },
            "suggestions": []
        })
        
    return jsonify({"error": "Invalid file type. Please upload a .csv or .xlsx file."})

if __name__ == '__main__':
    app.run(debug=True)