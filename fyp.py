from flask import Flask, flash, render_template, jsonify, request, redirect, url_for, session
import firebase_admin
import pyrebase
from firebase_admin import credentials, db, storage
import secrets
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt


app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# config = {
#   'apiKey': "AIzaSyB5Dy853MrTopAYvSqIdNiB2PRxJN7KqpE",
#   'authDomain': "ocr-fyp-beea5.firebaseapp.com",
#   'databaseURL': "https://ocr-fyp-beea5-default-rtdb.asia-southeast1.firebasedatabase.app",
#   'projectId': "ocr-fyp-beea5",
#   'storageBucket': "ocr-fyp-beea5.appspot.com",
#   'messagingSenderId': "906762493319",
#   'appId': "1:906762493319:web:a3418f94dde2f4e3d60722",
#   'measurementId': "G-MKT2TS8EPQ",
#   'databaseURL' : ''
# }

# firebase = pyrebase.initialize_app(config)
# auth = firebase.auth()

cred = credentials.Certificate("ocr-fyp-beea5-firebase-adminsdk-lik81-e109b66cf1.json")
# Initialize the app with a service account, granting admin privileges
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ocr-fyp-beea5-default-rtdb.asia-southeast1.firebasedatabase.app',
    'storageBucket': 'ocr-fyp-beea5.appspot.com'
})

# The app only has access to public data as defined in the Security Rules
ref = db.reference("")
ref.get()

storage_client = storage.bucket(app=firebase_admin.get_app(), name='ocr-fyp-beea5.appspot.com')

bcrypt = Bcrypt()

# Main
@app.route("/")
def index():
    if session:
        session.clear()
    return render_template('index.html')

@app.route("/user/login", methods=['GET', 'POST'])
def userLogin():
    error_message = None  # Define error_message with a default value

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Create a reference to the root of your Firebase Realtime Database
        ref = db.reference()
        users_ref = ref.child('users')

        # Query to find a user with the matching email
        user_query = users_ref.order_by_child('email').equal_to(email).get()

        if user_query:
            for user_id, user_data in user_query.items():
                stored_hashed_password = user_data.get('password')

                # Check if the entered password matches the stored hashed password
                if bcrypt.check_password_hash(stored_hashed_password, password):
                    # Authentication successful; store user's data in the session
                    session['userEmail'] = email
                    session['userID'] = user_id
                    print(session['userID'])

                    return redirect(url_for('documentHome'))

        error_message = 'Login failed. Please check your email and password.'

    return render_template('user/login.html', error_message=error_message)

@app.route("/user/register", methods=['GET', 'POST'])
def userRegister():

    if request.method == 'POST':
        name = request.form['userName']
        email = request.form['email']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        user_data = {"name": name, "email": email, "password": hashed_password, "images": ""}

        ref = db.reference('users')

        new_user_ref = ref.push()

        new_user_ref.set(user_data)

        return redirect(url_for('userLogin'))
    
    return render_template('user/register.html')

@app.route("/document/home", methods=['GET', 'POST'])
def documentHome():

    if 'userID' not in session:
        return redirect(url_for('userLogin'))

    user_id = session['userID']
    user_ref = db.reference('users').child(user_id)

    # Retrieve the images associated with the user from the Realtime Database
    user_data = user_ref.get()
    print(user_data)
    if user_data and 'images' in user_data:
        image_filenames = user_data['images'].split(', ')
    else:
        image_filenames = []
    print(image_filenames)

    # Download the images from Firebase Storage
    image_urls = []
    for filename in image_filenames:
        blob = storage.bucket().blob(f"{user_id}/{filename}")

        expiration_time = datetime.utcnow() + timedelta(hours=1)

        signed_url = blob.generate_signed_url(expiration=expiration_time, method='GET')
        image_urls.append(signed_url)

    print(image_urls)
    return render_template('document/home.html', user_data=user_data, image_urls=image_urls)

@app.route("/document/profile", methods=['GET', 'POST'])
def documentProfile():

    if 'userID' not in session:
        # Redirect to the login page if the user is not logged in or has no images
        return redirect(url_for('userLogin'))
    
    if request.method == 'POST':

        action = request.form.get('action')

        if action == 'editUser':
            # Get the user ID from the session
            user_id = session.get('userID')

            # Get the updated values from the form
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')  # Assuming the password field is named 'cgpa'

            # Update the user data in the Firebase Realtime Database
            users_ref = db.reference('users')
            user_ref = users_ref.child(user_id)

            user_ref.update({
                'name': name,
                'email': email,
                'password': password
                # Add more fields as needed
            })

    user_id = session.get('userID')

    # Retrieve user data from Firebase Realtime Database
    user_ref = db.reference('users').child(user_id)
    user_data = user_ref.get()


    # Pass the image URLs to the template
    return render_template('document/profile.html', user_id=user_id, user_data=user_data)


@app.route("/document/settings", methods=['GET', 'POST'])
def documentSettings():

    return render_template('document/settings.html')

@app.route("/document/templates", methods=['GET', 'POST'])
def documentTemplates():

    return render_template('document/templates.html')

@app.route("/document/trash", methods=['GET', 'POST'])
def documentTrash():

    return render_template('document/trash.html')