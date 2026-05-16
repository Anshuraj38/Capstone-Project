from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
import numpy as np
try:
    import google.generativeai as genai
except ImportError:
    genai = None
import os
import io
import json
from datetime import datetime
from functools import wraps

# ─── App Configuration ────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'ilios-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ilios.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# ─── Gemini Client ─────────────────────────────────────────────────────────
# Set GOOGLE_API_KEY in your environment variables before running.
# e.g.  $env:GOOGLE_API_KEY="YOUR_API_KEY"   (PowerShell)
#        export GOOGLE_API_KEY="YOUR_API_KEY"  (Bash)
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY') or app.config.get('GOOGLE_API_KEY')
if genai is not None and GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-flash-latest')
    except Exception:
        gemini_model = None
else:
    gemini_model = None

# ─── Database Models ──────────────────────────────────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.email}>'
    
# ─── Helpers ──────────────────────────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def load_dataframe(filepath):
    ext = filepath.rsplit('.', 1)[1].lower()
    if ext == 'csv':
        return pd.read_csv(filepath)
    else:
        return pd.read_excel(filepath)

def _save_df(df, filepath):
    """DRY helper – saves df back to original format."""
    ext = filepath.rsplit('.', 1)[1].lower()
    if ext == 'csv':
        df.to_csv(filepath, index=False)
    else:
        df.to_excel(filepath, index=False)

def profile_dataframe(df):
    total_rows, total_cols = df.shape

    missing = int(df.isnull().sum().sum())
    missing_pct = round((missing / (total_rows * total_cols)) * 100, 1) if total_rows * total_cols > 0 else 0

    duplicates = int(df.duplicated().sum())

    schema_issues = 0
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col].dropna().astype(float)
                schema_issues += 1
            except (ValueError, TypeError):
                pass

    quality = max(0, 100 - (missing_pct * 2) - (duplicates / max(total_rows, 1) * 30) - (schema_issues * 5))
    quality = round(quality)

    col_missing = df.isnull().sum()
    col_info = []
    for col in df.columns:
        col_info.append({
            'name': col,
            'dtype': str(df[col].dtype),
            'missing': int(col_missing[col]),
            'missing_pct': round(col_missing[col] / total_rows * 100, 1) if total_rows > 0 else 0,
            'unique': int(df[col].nunique())
        })

    return {
        'rows': total_rows,
        'cols': total_cols,
        'missing': missing,
        'missing_pct': missing_pct,
        'duplicates': duplicates,
        'schema_issues': schema_issues,
        'quality_score': quality,
        'columns': col_info,
        'sample': df.head(5).fillna('').to_dict(orient='records')
    }

def generate_suggestions(df):
    """Rule-based suggestions (fast, no API call needed)."""
    suggestions = []

    for col in df.columns:
        missing = df[col].isnull().sum()
        if missing > 0:
            pct = round(missing / len(df) * 100, 1)
            if pd.api.types.is_numeric_dtype(df[col]):
                suggestions.append({
                    'type': 'missing',
                    'column': col,
                    'title': f"Handle missing values in '{col}'",
                    'description': f'{missing} missing ({pct}%). Suggested: Fill with Median',
                    'action': 'fill_median'
                })
            else:
                suggestions.append({
                    'type': 'missing',
                    'column': col,
                    'title': f"Handle missing values in '{col}'",
                    'description': f'{missing} missing ({pct}%). Suggested: Fill with Mode',
                    'action': 'fill_mode'
                })

    dups = df.duplicated().sum()
    if dups > 0:
        suggestions.append({
            'type': 'duplicate',
            'column': None,
            'title': f'Remove {dups} duplicate rows',
            'description': f'Found {dups} exact duplicate rows in the dataset.',
            'action': 'drop_duplicates'
        })

    for col in df.select_dtypes(include='object').columns:
        unique_vals = df[col].dropna().unique()
        if len(unique_vals) <= 20:
            lower_vals = [v.strip().lower() for v in unique_vals if isinstance(v, str)]
            if len(lower_vals) != len(set(lower_vals)):
                suggestions.append({
                    'type': 'normalize',
                    'column': col,
                    'title': f"Normalize '{col}' column entries",
                    'description': 'Inconsistent casing or whitespace detected.',
                    'action': 'normalize_text'
                })

    for col in df.select_dtypes(include=[np.number]).columns:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        outliers = ((df[col] < (Q1 - 1.5 * IQR)) | (df[col] > (Q3 + 1.5 * IQR))).sum()
        if outliers > 0:
            suggestions.append({
                'type': 'outlier',
                'column': col,
                'title': f"Remove outliers in '{col}'",
                'description': f'{int(outliers)} outliers detected via IQR method.',
                'action': 'remove_outliers'
            })

    return suggestions[:8]

def build_schema_summary(df):
    """Build a concise schema string for Gemini's context."""
    lines = [f"Dataset: {df.shape[0]} rows × {df.shape[1]} columns", "Columns:"]
    for col in df.columns:
        missing = int(df[col].isnull().sum())
        sample_vals = df[col].dropna().head(3).tolist()
        lines.append(f"  - {col} ({df[col].dtype}): {missing} missing, sample={sample_vals}")
    return "\n".join(lines)

# ─── Auth Routes ──────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid email or password.'
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not name or not email or not password:
            error = 'All fields are required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif User.query.filter_by(email=email).first():
            error = 'An account with this email already exists.'
        else:
            hashed = generate_password_hash(password)
            new_user = User(name=name, email=email, password=hashed)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── Dashboard ────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user_name=session.get('user_name', 'User'))

# ─── File Upload ──────────────────────────────────────────────────────────────
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only CSV and Excel files are supported'}), 400

    # ── Per-user storage to avoid filename collisions ──────────────────────────
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(session['user_id']))
    os.makedirs(user_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    filepath = os.path.join(user_folder, filename)
    file.save(filepath)

    session['current_file'] = filepath
    session['current_filename'] = filename

    try:
        df = load_dataframe(filepath)
        profile = profile_dataframe(df)
        suggestions = generate_suggestions(df)
        return jsonify({'success': True, 'filename': filename,
                        'profile': profile, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'error': f'Could not parse file: {str(e)}'}), 500

# ─── Profile Endpoint ─────────────────────────────────────────────────────────
@app.route('/profile', methods=['GET'])
@login_required
def get_profile():
    filepath = session.get('current_file')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'No file loaded'}), 400
    try:
        df = load_dataframe(filepath)
        profile = profile_dataframe(df)
        suggestions = generate_suggestions(df)
        return jsonify({'profile': profile, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Apply Cleaning (rule-based) ──────────────────────────────────────────────
@app.route('/clean', methods=['POST'])
@login_required
def apply_cleaning():
    filepath = session.get('current_file')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'No file loaded'}), 400

    data = request.get_json()
    action = data.get('action')
    column = data.get('column')

    try:
        df = load_dataframe(filepath)

        if action == 'fill_median' and column:
            df[column] = df[column].fillna(df[column].median())
        elif action == 'fill_mode' and column:
            df[column] = df[column].fillna(df[column].mode()[0])
        elif action == 'drop_duplicates':
            df = df.drop_duplicates()
        elif action == 'normalize_text' and column:
            df[column] = df[column].str.strip().str.lower().str.title()
        elif action == 'remove_outliers' and column:
            Q1 = df[column].quantile(0.25)
            Q3 = df[column].quantile(0.75)
            IQR = Q3 - Q1
            df = df[~((df[column] < (Q1 - 1.5 * IQR)) | (df[column] > (Q3 + 1.5 * IQR)))]
        elif action == 'drop_missing' and column:
            df = df.dropna(subset=[column])
        else:
            return jsonify({'error': 'Unknown action'}), 400

        _save_df(df, filepath)
        profile = profile_dataframe(df)
        suggestions = generate_suggestions(df)
        return jsonify({'success': True, 'profile': profile, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── NEW: Natural Language Cleaning via Gemini ────────────────────────────────
@app.route('/ai_clean', methods=['POST'])
@login_required
def ai_clean():
    """
    Accepts a plain-English instruction from the user.
    Gemini interprets it, returns safe pandas code, which we execute on the df.

    Request JSON: { "instruction": "remove rows where age is negative" }
    Response JSON: { "success": True, "message": "...", "rows_affected": N,
                     "profile": {...}, "suggestions": [...] }
    """
    filepath = session.get('current_file')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'No file loaded'}), 400

    data = request.get_json()
    instruction = (data.get('instruction') or '').strip()
    if not instruction:
        return jsonify({'error': 'No instruction provided'}), 400

    if gemini_model is None:
        return jsonify({'error': 'AI features are unavailable. Install google-generativeai and set GOOGLE_API_KEY.'}), 503

    try:
        df = load_dataframe(filepath)
        schema = build_schema_summary(df)

        system_prompt = """You are a data cleaning assistant.
IMPORTANT: You must ALWAYS return a code block and a short explanation, even if you are unsure.
If a requested column does not exist, handle it gracefully or create it.

Return ONLY this format:
```python
# your code here
```
EXPLANATION: <one sentence>

The user will give you a plain-English instruction to clean a pandas DataFrame called `df`.
Your code must:
1. Modify `df` in-place or reassign it.
2. Use ONLY pandas / numpy operations.
3. Assign the final DataFrame back to `df`.
4. Not import any modules.

IMPORTANT SAFETY RULES:
- Never use os, sys, subprocess, open(), exec(), eval() or any file I/O.
- Only read/write the `df` variable.
- If the instruction is unclear or unsafe, return: CANNOT_DO: <reason>
"""

        user_msg = f"""Dataset schema:
{schema}

User instruction: "{instruction}"
"""

        full_prompt = system_prompt + "\n\n" + user_msg

        response = gemini_model.generate_content(full_prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=512))

        reply = response.text.strip()
        app.logger.debug('Gemini reply: %s', reply)

        # ── Handle refusal ────────────────────────────────────────────────────
        if reply.startswith("CANNOT_DO:"):
            reason = reply.replace("CANNOT_DO:", "").strip()
            return jsonify({'error': f'Gemini could not process this: {reason}'}), 422

        # ── Extract code block ─────────────────────────────────────────────────────
        if "```python" in reply:
            code_part = reply.split("```python")[1].split("```")[0].strip()
        elif "```" in reply:
            code_part = reply.split("```")[1].split("```")[0].strip()
        else:
            app.logger.debug('Gemini unexpected response without code fence: %s', reply)
            return jsonify({
                'error': 'Gemini returned an unexpected response. Please rephrase your instruction.',
                'gemini_reply': reply[:800]
            }), 422

        # ── Safety: block dangerous keywords ─────────────────────────────────
        banned = ['import ', 'os.', 'sys.', 'subprocess', 'open(', 'exec(', 'eval(', '__']
        for b in banned:
            if b in code_part:
                return jsonify({'error': 'Instruction contains unsafe operations.'}), 422

        # ── Extract explanation ───────────────────────────────────────────────
        explanation = "Cleaning applied successfully."
        if "EXPLANATION:" in reply:
            explanation = reply.split("EXPLANATION:")[1].strip()

        # ── Execute the code ──────────────────────────────────────────────────
        rows_before = len(df)
        local_vars = {'df': df, 'pd': pd, 'np': np}
        exec(code_part, {"__builtins__": {}}, local_vars)
        df = local_vars['df']
        rows_after = len(df)

        _save_df(df, filepath)
        profile = profile_dataframe(df)
        suggestions = generate_suggestions(df)

        return jsonify({
            'success': True,
            'message': explanation,
            'rows_affected': rows_before - rows_after,
            'code_applied': code_part,
            'profile': profile,
            'suggestions': suggestions
        })

    except SyntaxError as e:
        return jsonify({'error': f'Generated code had a syntax error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── NEW: Ask Gemini About Your Data ─────────────────────────────────────────
@app.route('/ask', methods=['POST'])
@login_required
def ask_about_data():
    """
    Let users ask free-form questions about their dataset.
    e.g. "Which column has the most missing values?"
         "What does the Age column look like?"
         "Should I remove outliers from Salary?"

    Request JSON : { "question": "..." }
    Response JSON: { "answer": "..." }
    """
    filepath = session.get('current_file')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'No file loaded'}), 400

    data = request.get_json()
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    try:
        df = load_dataframe(filepath)
        schema = build_schema_summary(df)

        # Compute basic stats for numeric columns to give Gemini richer context
        stats_lines = []
        for col in df.select_dtypes(include=[np.number]).columns:
            stats_lines.append(
                f"  {col}: min={df[col].min():.2f}, max={df[col].max():.2f}, "
                f"mean={df[col].mean():.2f}, std={df[col].std():.2f}"
            )
        stats_summary = "\n".join(stats_lines) if stats_lines else "  (no numeric columns)"

        system_prompt = """You are a friendly data analyst assistant helping a non-technical user 
understand and clean their dataset. Answer questions in plain English — no jargon, 
no code blocks unless specifically asked. Keep responses concise (2-4 sentences max). 
Be encouraging and helpful."""

        user_msg = f"""Dataset schema:
{schema}

Numeric column statistics:
{stats_summary}

User question: "{question}"
"""

        full_prompt = system_prompt + "\n\n" + user_msg

        response = gemini_model.generate_content(full_prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=400))

        answer = response.text.strip()
        return jsonify({'answer': answer})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── NEW: AI-Powered Summary of the Dataset ───────────────────────────────────
@app.route('/ai_summary', methods=['GET'])
@login_required
def ai_summary():
    """
    Returns a plain-English summary of the dataset's quality issues
    and recommended next steps — generated by Gemini.
    """
    filepath = session.get('current_file')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'No file loaded'}), 400

    try:
        df = load_dataframe(filepath)
        profile = profile_dataframe(df)
        schema = build_schema_summary(df)

        system_prompt = """You are a friendly data quality analyst. 
Write a short, plain-English paragraph (4-6 sentences) summarising the health of 
this dataset for a non-technical user. Mention the biggest problems and give 2-3 
concrete, prioritised next steps. No bullet points — write in natural prose."""

        user_msg = f"""Dataset profile:
{schema}

Quality score: {profile['quality_score']}/100
Missing values: {profile['missing']} ({profile['missing_pct']}%)
Duplicate rows: {profile['duplicates']}
Schema issues: {profile['schema_issues']}
"""

        full_prompt = system_prompt + "\n\n" + user_msg

        if gemini_model is None:
            return jsonify({'error': 'AI features are unavailable. Install google-generativeai and set GOOGLE_API_KEY.'}), 503

        response = gemini_model.generate_content(full_prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=300))

        summary = response.text.strip()
        return jsonify({'summary': summary})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Export Cleaned File ──────────────────────────────────────────────────────
@app.route('/export')
@login_required
def export_file():
    filepath = session.get('current_file')
    filename = session.get('current_filename', 'cleaned_data.csv')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'No file to export'}), 400
    try:
        df = load_dataframe(filepath)
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        clean_name = 'cleaned_' + filename.rsplit('.', 1)[0] + '.csv'
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=clean_name
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5050)