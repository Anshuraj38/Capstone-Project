from flask import Flask , render_template , request
from db import Database
app = Flask(__name__)

dbo = Database()

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('signup.html')

@app.route('/perform_registration' , methods=['POST'])
def perform_registration():
    name = request.form.get('username')
    email = request.form.get('user_ka_email')
    password = request.form.get('user_ka_password')
    
    response = dbo.insert(name,email,password)

    if response:
        return "Registration Successful"
    else:
        return "Email already existed"
app.run(debug=True)