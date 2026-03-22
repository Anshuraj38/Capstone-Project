from flask import Flask , render_template , request
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('signup.html')

@app.route('/perform_registration' , methods=['POST'])
def perform_registration():
    name=request.form.get('username')
    name=request.form.get('email')
    name=request.form.get('password')
    name=request.form.get('confirm_password')
    return "registration successful"
app.run(debug=True)