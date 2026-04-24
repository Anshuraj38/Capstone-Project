from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from db import Database
import os
import io
import pandas as pd
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

@app.route('/history')
def history():
    if 'logged_in' not in session:
        return redirect(url_for('index'))
    name = session.get('name', 'User')
    return render_template('history.html', user_name=name)

@app.route('/perform_registration' , methods=['POST'])
def perform_registration():
    name = request.form.get('username', '').strip()
    email = request.form.get('user_ka_email', '').strip()
    password = request.form.get('user_ka_password', '').strip()

    if not name or not email or not password:
        return render_template('signup.html', error='Please enter email, password and name')

    response = dbo.insert(name, email, password)
    if response:
        session['name'] = name
        session['email'] = email
        session['logged_in'] = True
        return redirect(url_for('dashboard'))

    return render_template('signup.html', error='Email already existed')

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
    # Simple data info algorithm:
    # 1) save uploaded file to uploads folder
    # 2) load it with pandas as DataFrame
    # 3) use df.info() to capture column types and non-null counts
    # 4) compute row/column counts, missing values, duplicates, and sample rows
    # 5) return this info to the dashboard as JSON
    if 'logged_in' not in session:
        return jsonify({"error": "Login required"}), 401

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"})

    filename = secure_filename(file.filename)
    lower_filename = filename.lower()
    if file and lower_filename.endswith(('.csv', '.xlsx', '.xls')):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            if lower_filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
        except Exception as e:
            return jsonify({"error": f"Unable to read file: {str(e)}"}), 400

        buffer = io.StringIO()
        df.info(buf=buffer)
        info_text = buffer.getvalue()

        profile = {
            "quality_score": 100,
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "missing": int(df.isnull().sum().sum()),
            "missing_pct": round(float(df.isnull().mean().mean() * 100), 2),
            "duplicates": int(df.duplicated().sum()),
            "schema_issues": 0,
            "columns": list(df.columns.astype(str)),
            "sample": df.head(5).to_dict(orient='records'),
            "info": info_text
        }

        return jsonify({
            "filename": filename,
            "profile": profile,
            "suggestions": []
        })

    return jsonify({"error": "Invalid file type. Please upload a .csv or .xlsx file."})

if __name__ == '__main__':
    app.run(debug=True)