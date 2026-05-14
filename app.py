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

