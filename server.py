# Importing Flask + Required Modules
from flask import Flask, session, redirect, render_template, request, url_for
# Importing userManager
import userManager as UM
# Importing threading
import threading
# Creating an insteance of Flask
app = Flask(__name__)
# Creating a secret key for session management
app.secret_key = 'insecure_secret_key_for_session_management'
# Creating an instance of UserManager
userManager = UM.UserManager()
# Setting variables
userInfo = None
userName = None

# Home page
@app.route('/')
def index():
    return render_template('index.html')

# Login/Logout/Profiles
@app.route('/login')
@app.route('/auth/login')
def login():
    return render_template('login.html')
@app.route('/logout')
@app.route('/auth/logout')
def logout():
    userInfo=None
    session.pop('UserId', None)
    return render_template('logout.html')
@app.route('/service/auth', methods=['POST']) 
def auth_service():
    UserId = request.form['uname']
    Pwd = request.form['psw']
    print(UserId)
    res = userManager.Auth(UserId, Pwd)
    userInfo = res['user'] 
    if userInfo != None:    
        userName=UserId
        session['UserId'] = UserId
        userData = userManager.getDetails(UserId)
        session['role'] = userData[2]
        return redirect(url_for('index'))     
    else:   
        # On failed login, render the login page with an error message so the
        # user sees why authentication failed and can retry without losing
        # the entered username.
        return render_template('login.html', error=res.get('message', 'Login failed'), username=UserId)
@app.route('/service/auth/password',methods=['POST'])
def change_password():
    newpassword=request.form['psw']
    # Call the UserManager.changePassword method (camelCase in userManager)
    userManager.changePassword(session['UserId'], newpassword)
    return redirect('/')
@app.route('/profile')
def profile():
    return render_template('editPwd.html')

if __name__ == "__main__":
    app.run(debug=True)