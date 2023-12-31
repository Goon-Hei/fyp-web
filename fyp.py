from cgi import FieldStorage
import io
from flask import Flask, flash, render_template, jsonify, request, redirect, url_for, session
import firebase_admin
from firebase_admin import credentials, db, storage, auth, firestore
import secrets
from datetime import datetime
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
import requests
import json
import re
from datetime import datetime
import base64
import json
from PIL import Image
from io import BytesIO
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired



ALLOWED_EXTENSIONS = {'jpeg', 'jpg', 'png'}

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['SECRET_KEY'] = app.secret_key
app.config['MAIL_SERVER']="smtp.gmail.com"
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = "goonhei123@gmail.com"
app.config['MAIL_PASSWORD'] = "baej tmjj ukgi jlne"
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

s = URLSafeTimedSerializer('Thisisasecret!')

cred = credentials.Certificate("ocr-fyp-beea5-firebase-adminsdk-lik81-e109b66cf1.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ocr-fyp-beea5-default-rtdb.asia-southeast1.firebasedatabase.app',
    'storageBucket': 'ocr-fyp-beea5.appspot.com'
})

storage_client = storage.bucket(app=firebase_admin.get_app(), name='ocr-fyp-beea5.appspot.com')

# Create a reference to the default Firebase Storage bucket
storage_client = firebase_admin.storage.bucket()
storage_ref = storage.bucket()

bcrypt = Bcrypt()

# Application Default credentials are automatically created.
db = firestore.client()

# Main
@app.route("/")
def index():
    if session:
        session.clear()
    return render_template('index.html')

def hashPassword(password):
    # Create a new SHA-512 hash object
    sha512 = hashlib.sha512()

    # Update the hash object with the UTF-8 encoded password
    sha512.update(password.encode('utf-8'))

    # Get the hexadecimal representation of the digest
    hashed_password = sha512.hexdigest()

    return hashed_password

def verify_password(stored_hashed_password, entered_password):
    return stored_hashed_password == hashPassword(entered_password)

@app.route("/user/login", methods=['GET', 'POST'])
def userLogin():
    error_message = None

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Create a reference to the "users" collection in Firestore
        users_ref = db.collection('users')

        # Query to find a user with the matching email
        user_query = users_ref.where('email', '==', email).stream()

        for user_doc in user_query:
            user_data = user_doc.to_dict()
            stored_hashed_password = user_data.get('password')

            # Check if the entered password matches the stored hashed password
            if verify_password(stored_hashed_password, password):
                # Authentication successful; store user's data in the session
                session['userEmail'] = email
                session['userID'] = user_doc.id

                return redirect(url_for('documentHome'))

        error_message = 'Login failed. Please check your email and password.'

    return render_template('user/login.html', error_message=error_message)

@app.route("/user/resetPasswordRequest", methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        
        email = request.form['email']

        users_ref = db.collection('users')
        query = users_ref.where('email', '==', email)
        documents = query.get()
    

        if documents:
            for document in documents:
                # User with the specified email exists
                user_doc = document.reference

                return render_template('user/resetPassword.html', email=email)
        else:
            error_message = 'No such email. Please enter a valid email'

        return render_template('user/resetPasswordRequest.html', error_message=error_message)
    
    return render_template('user/resetPasswordRequest.html')

    

# Assuming you have initialized your Flask app and Firebase Admin SDK

@app.route('/user/resetPassword', methods=['GET', 'POST'])
def reset_password():

    if request.method == 'POST':
        password = request.form.get('password')
        email = request.form.get('email')
        

        if email:
            # Query Firestore to find the user with the specified email
            users_ref = db.collection('users')
            query = users_ref.where('email', '==', email).limit(1)
            user_docs = query.stream()

            # Check if a user with the specified email exists
            for user_doc in user_docs:
                user_ref = user_doc.reference

                # Validate password length
                if len(password) < 6:
                    
                    error_message = 'Password must be at least 6 characters long.'
                    return render_template('user/resetPassword.html', error_message=error_message,email=email)

                # Update the password in Firestore
                user_ref.update({'password': hashPassword(password)})

                return redirect(url_for('userLogin'))
    
        else:

            error_message = 'No such user'

            return render_template('user/resetPassword.html',error_message=error_message)


    return render_template('user/resetPassword.html')



@app.route("/user/register", methods=['GET', 'POST'])
def userRegister():
    if request.method == 'POST':
        name = request.form['userName']
        email = request.form['email']
        password = request.form['password']

        # Use the custom SHA-512 hashing method
        hashed_password = hashPassword(password)

        user_data = {"name": name, "email": email, "password": hashed_password}

        try:
            # Try to create the user in Firebase Authentication
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )

            # Use the Firebase Authentication UID as the unique identifier
            user_id = user.uid

            # Add user data to 'users' collection with the Firebase UID
            new_user_ref = db.collection('users').document(user_id)
            new_user_ref.set(user_data)

            session['userEmail'] = email
            session['userID'] = user_id

            return redirect(url_for('userLogin'))

        except auth.EmailAlreadyExistsError as e:
            # Handle the case where the email already exists

            error_message = f'Registration failed. Email already exists'

            return render_template('user/register.html', error_message=error_message)
        
        except ValueError as e:
            # Handle the case where the password is invalid
            error_message = 'Registration failed. Invalid password. Password must be at least 6 characters long.'
            return render_template('user/register.html', error_message=error_message)

    return render_template('user/register.html')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/document/home", methods=['GET', 'POST'])
def documentHome():

    if 'userID' not in session:
        return redirect(url_for('userLogin'))

    user_id = session['userID']
    user_ref = db.collection('users').document(user_id)

    # Retrieve the user's data from Firestore
    user_data = user_ref.get().to_dict()

    # Initialize an empty list to store image links
    links = []
    image_data_list = []
    unique_links = set()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'uploadFile':
            file = request.files['file']
            if file and allowed_file(file.filename):

                if file.filename.lower().endswith('.png'):
                    image = Image.open(file.stream)

                    jpg_image_buffer = io.BytesIO()
                    image.convert('RGB').save(jpg_image_buffer, format="JPEG")
                    jpg_image_buffer.seek(0)

                    byte_data = jpg_image_buffer.read()

                    filename = secure_filename(file.filename.rsplit('.', 1)[0] + '.jpg')
                    blob = storage_client.blob(filename)
                    
                    # Set content type explicitly based on the file extension
                    blob.upload_from_string(
                        byte_data,
                        content_type='image/jpeg'
                    )

                    # Update Firestore with the new image link
                    images_ref = db.collection('images')

                    new_link = f'https://firebasestorage.googleapis.com/v0/b/ocr-fyp-beea5.appspot.com/o/{filename.strip()}?alt=media'

                    # Create a new entry for each image
                    images_ref.add({'link': new_link, 'fileName': filename, 'dateCreated': datetime.utcnow(), 'userID': user_id})

                    return redirect(url_for('documentHome'))
                else:

                    filename = secure_filename(file.filename)

                    blob = storage_client.blob(filename)
                
                    # Set content type explicitly based on the file extension
                    blob.upload_from_file(file, content_type=f'image/{filename.rsplit(".", 1)[1].lower()}')

                    # Update Firestore with the new image link
                    images_ref = db.collection('images')

                    new_link = f'https://firebasestorage.googleapis.com/v0/b/ocr-fyp-beea5.appspot.com/o/{filename.strip()}?alt=media'

                    # Create a new entry for each image
                    images_ref.add({'link': new_link, 'fileName': filename, 'dateCreated': datetime.utcnow(), 'userID': user_id})

                    return redirect(url_for('documentHome'))
                
            else:
                error_message=('Only JPG, JPEG, and PNG files are allowed.')

                return render_template('document/home.html', error_message=error_message, user_data=user_data)


        elif action == 'searchFiles':
            search_query = request.form.get('search').strip()

            # Query Firestore for user's images
            images_ref = db.collection('images')
            query = images_ref.where('userID', '==', user_id).where('fileName', '>=', search_query).where('fileName', '<=', search_query + '\uf8ff')
            images_query = query.stream()

            if images_query is not None:
                for image_doc in images_query:
                    image_data = image_doc.to_dict()
                    if 'link' in image_data:
                        links = image_data['link'].split(',')
                
                        # Add image data to the list for each unique link
                        for link in links:
                            clean_link = link.strip()
                            if clean_link not in unique_links:
                                unique_links.add(clean_link)
                                image_data_list.append({
                                    'link': clean_link,
                                    'date_created': image_data.get('dateCreated', 'N/A'),
                                    'file_name': image_data.get('fileName', 'N/A')
                                })

                return render_template('document/home.html', image_data_list=image_data_list, user_data=user_data)

        elif action == 'deleteImage':
            image_to_delete = request.form.get('imageToDelete')
            print("dlt",image_to_delete)

            if image_to_delete:
                # Delete logic here
                images_ref = db.collection('images')
                query = images_ref.where('userID', '==', user_id)
                images_query = query.stream()

                for image_doc in images_query:
                    image_data = image_doc.to_dict()
                    print("imageDATA", image_data)

                    if 'link' in image_data:
                        links = image_data['link'].split(',')
                        print("link",links)
                        if image_to_delete in links:
                            links.remove(image_to_delete)
                            new_links = ','.join(links)
                            if new_links:
                                images_ref.document(image_doc.id).update({'link': new_links})
                            else:
                                # If no more links, delete the image document
                                images_ref.document(image_doc.id).delete()

                                # Add the image to the trash
                                trash_data = {
                                    'link': image_to_delete,
                                    'fileName': image_data.get('fileName', 'N/A'),
                                    'userID': user_id,
                                    'createdDate': image_data.get('dateCreated', 'N/A'),
                                    'deletedDate': datetime.utcnow()
                                }

                                trash_ref = db.collection('trash').add(trash_data)

                                # Check if 'dateCreated' key is not present
                                if 'dateCreated' not in image_data:
                                    print("Warning: 'dateCreated' not present in image_data")

                                    trash_ref = db.collection('trash').add(trash_data)

                return redirect(url_for('documentHome'))

        elif action == 'logout':
            # Logout logic
            session.pop('userID', None)
            flash('You have been successfully logged out.', 'success')  # Optional: Display a flash message
            return redirect(url_for('userLogin'))

    # Query Firestore for user's images
    images_ref = db.collection('images')
    user_images = images_ref.where('userID', '==', user_id).stream()

    for image_doc in user_images:
        image_data = image_doc.to_dict()
        if 'link' in image_data:
            if ',' in image_data['link']:
                links.append(image_data['link'].split(','))
            else:
                links.append(image_data['link'])

                for link in links:
                    clean_link = link.strip()
                    if clean_link not in unique_links:
                        unique_links.add(clean_link)
                        image_data_list.append({
                            'link': clean_link,
                            'date_created': image_data.get('dateCreated', 'N/A'),
                            'file_name': image_data.get('fileName', 'N/A')
                        })

    # Rest of the code remains the same as previously provided
    print(image_data_list)
    return render_template('document/home.html', image_data_list=image_data_list, user_data=user_data)


@app.route("/document/profile", methods=['GET', 'POST'])
def documentProfile():
    user_id = session.get('userID')

    if 'userID' not in session:
        # Redirect to the login page if the user is not logged in or has no images
        return redirect(url_for('userLogin'))


    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'editUser':
            # Get the updated values from the form
            name = request.form.get('name')

            # Update the user data in Firestore
            user_ref = db.collection('users').document(user_id)

            updates = {
                'name': name,
            }

            user_ref.update(updates)

        elif action == 'logout':
            # Logout logic
            session.pop('userID', None)
            flash('You have been successfully logged out.', 'success')  # Optional: Display a flash message
            return redirect(url_for('userLogin'))

    # Retrieve user data from Firestore
    user_ref = db.collection('users').document(user_id)
    user_data = user_ref.get().to_dict()
    print("userdata",  user_data)

    # Pass the user data to the template
    return render_template('document/profile.html', user_id=user_id, user_data=user_data)



@app.route("/document/imageDetail", methods=['GET', 'POST'])
def documentImageDetail():
    if request.method == 'POST':
        action = request.form.get('action')
        print("ACtion", action)
        if action == 'OCR':
            # Get the image URL from the form data
            image_url = request.form['imageUrl']

            query_ref = db.collection("template")

            docs = query_ref.stream()
            templates = []
            for doc in docs:
                if doc.exists:
                    document_data = doc.to_dict()
                    print("docData", document_data)
                    template_name = document_data.get('tempName')
                    template_data = {
                            "tempName": template_name,
                    }
                    templates.append(template_data)

            # Define the data for the POST request
            data = {
                "imageUrl": image_url,
                "ocrMethod": "directToString",
                "tempName": "",
                "config": "",
            }

            # Define the API endpoint URL
            API_ENDPOINT_URL = "https://c5df-103-52-192-245.ngrok-free.app/ocrrequest/"

            # Send the POST request to the API endpoint
            response = requests.post(API_ENDPOINT_URL, json=data)

            # Handle the response as needed
            if response.status_code == 200:
                # Request was successful
                result = response.json()
                print("API Response:")
                print(result)
                ocr_response = result['text']
                # Replace double newlines with a single <br>
                ocr_response = re.sub(r'\n\n', '<br>', ocr_response)
                # Then replace any remaining single newlines with <br>
                ocr_response = re.sub(r'(?<!<br>)\n', '<br>', ocr_response)

                return render_template('document/imageDetail.html', image_link=image_url, ocr_response=ocr_response, templates=templates)

            else:
                image_url = request.form['imageUrl']
                print("Testing2:", image_url)
                print('Error uploading image:', response.text)

                return render_template('document/imageDetail.html', image_link=image_url, templates=templates)
        else:
            templateName = request.form['tempName']
            image_url = request.form['imageUrl']
            print("Testing:", image_url)

            templates_ref = db.collection("template")

            docs = templates_ref.stream()
            templates = []
            for doc in docs:
                if doc.exists:
                    document_data = doc.to_dict()
                    template_name = document_data.get('tempName')
                    template_data = {
                        "tempName": template_name,
                    }
                    templates.append(template_data)

            query_ref = db.collection("template").where("tempName", "==", templateName)
            try:
                docs = query_ref.stream()
                for doc in docs:
                    if doc.exists:
                        document_data = doc.to_dict()
                        config = document_data.get('config')
                        preConfig = document_data.get('preProcessingConfig')
                        psm= document_data.get('psm')

                data = {
                        "imageUrl": image_url,      
                        "ocrMethod": "template",
                        "config": config,
                        "preProcessingConfig": preConfig,
                        "psm": psm
                        }

                print("Json data:",data)

                # Define the API endpoint URL
                API_ENDPOINT_URL = "https://c5df-103-52-192-245.ngrok-free.app/ocrrequest/"

                # Send the POST request to the API endpoint
                response = requests.post(API_ENDPOINT_URL, json=data)

                # Handle the response as needed
                if response.status_code == 200:
                    # Request was successful
                    result = response.json()
                    print("API Response:")
                    print(result)
                    api_response = result['text']
                    # # Replace double newlines with a single <br>
                    # api_response = re.sub(r'\n\n', '<br>', api_response)
                    # # Then replace any remaining single newlines with <br>
                    # api_response = re.sub(r'(?<!<br>)\n', '<br>', api_response)
                    # print("testing123",image_url)

                    return render_template('document/imageDetail.html', image_link=image_url, api_response=api_response, templates=templates)

                else:
                    image_url = request.form['imageUrl']
                    print("Before setting image_url:", image_url)
                    print('Error uploading image:', response.text)

                    return render_template('document/imageDetail.html', image_link=image_url, templates=templates)
            except Exception as e:
                # Handle exceptions, log, or return an error page
                print(f"Error retrieving documents: {e}")

    # For GET requests, retrieve the image link from the query parameters

    image_link = request.args.get('imageLink')
    query_ref = db.collection("template")

    docs = query_ref.stream()
    templates = []
    for doc in docs:
        if doc.exists:
            document_data = doc.to_dict()
            print("docData", document_data)
            template_name = document_data.get('tempName')
            template_data = {
                    "tempName": template_name,
            }
            templates.append(template_data)
            print("tempDAta", templates)

    return render_template('document/imageDetail.html', image_link=image_link, templates=templates)



@app.route("/document/templates", methods=['GET', 'POST'])
def documentTemplates():

    if 'userID' not in session:
        return redirect(url_for('userLogin'))
    
    if request.method == 'POST':
        # Assuming the form has a name attribute, change it accordingly
        if request.form['action'] == 'CreateTemplate':
            # Redirect to templateDetail route
            return redirect(url_for('uploadImage'))
        elif request.form['action'] == 'editTemplate':
            # Assuming you have a template ID available in the form
            temp_name = request.form.get('tempName')

            query_ref = db.collection("template").where('tempName' , "==", temp_name)
            docs = query_ref.stream()
            if docs:
                # Retrieve data from the first (and only) document
                template_data = next(docs).to_dict()

                print("testingTemplatesss", template_data)
                template = json.dumps(template_data, ensure_ascii=False)
                print("testin23esss", template)

            return render_template('document/editTemplatePreProcessingConfig.html', temp_name=temp_name, template_data=template_data,template=template)


        elif request.form['action'] == 'searchTemplate':
            search_query = request.form.get('search')
            templates = []
            # Search for templates based on tempName
            template_ref = db.collection("template").where('tempName', '>=', search_query).where('tempName', '<=', search_query + '\uf8ff')
            template_docs = template_ref.stream()

            for doc in template_docs:
                templates.append(doc.to_dict())
            
            return render_template('document/templates.html', templates=templates)
        
        elif request.form['action'] == 'deleteTemplate':
            temp_name = request.form.get('tempName')

            # Delete the template based on tempName
            query_ref = db.collection("template").where('tempName', '==', temp_name)
            docs = query_ref.stream()
            for doc in docs:
                doc.reference.delete()
            # Redirect back to the templates page or any other appropriate page
            return redirect(url_for('documentTemplates'))
            
        

    query_ref = db.collection("template")

    docs = query_ref.stream()
    templates = []
    for doc in docs:
        if doc.exists:
            document_data = doc.to_dict()
            print("docData", document_data)
            template_name = document_data.get('tempName')
            config = document_data.get('config')
            template_data = {
                    "tempName": template_name,
                    "config": config,
            }
            templates.append(template_data)
            print("tempDAta", templates)

    return render_template('document/templates.html', templates=templates)

@app.route("/document/editTemplatePreProcessingConfig", methods=['GET', 'POST'])
def documentEditTemplatePreProcessingConfig():

    if 'userID' not in session:
        return redirect(url_for('userLogin'))
    
    if request.method == 'POST':
        # Assuming the form has a name attribute, change it accordingly
        if request.form['action'] == 'editTemplatePreProcessingConfig':
            # Assuming you have a template ID available in the form
            temp_name = request.form.get('tempName')
            template_data = request.form.get('template')
            print("templates_json:", template_data)

            template = json.loads(template_data)

            print("testingTemplateEdit", template)

            psm_value = template["psm"]

            print("psm_value:", psm_value)

            # config_data = templates[0]['config']
            # print("616136116713", config_data)

            psm = int(request.form.get('psm'))
            dilated_iterations = int(request.form.get('dilated_iterations'))
            eroded_iterations = int(request.form.get('eroded_iterations'))
            threshold = convertToBool(request.form.get('threshold'))
            kernel_size = int(request.form.get('kernelSize'))
            equalize_hist = convertToBool(request.form.get('equalizeHist'))
            morphologyEx_iterations = int(request.form.get('morphologyEx_iterations'))
            dilated = convertToBool(request.form.get('dilated'))
            morphologyEx = convertToBool(request.form.get('morphologyEx'))
            eroded = convertToBool(request.form.get('eroded'))
            denoised = convertToBool(request.form.get('denoised'))

            passingData = {
                    "psm": psm,
                    "preProcessingConfig": {
                        "dilated_iterations": dilated_iterations,
                        "eroded_iterations": eroded_iterations,
                        "threshold": threshold,
                        "kernelSize": kernel_size,
                        "equalizeHist": equalize_hist,
                        "morphologyEx_iterations": morphologyEx_iterations,
                        "dilated": dilated,
                        "morphologyEx": morphologyEx,
                        "eroded": eroded,
                        "denoised": denoised
                    }
                }
            
            passData = json.dumps(passingData, ensure_ascii=False)

            return render_template('document/editTemplateConfig.html', temp_name=temp_name, passData=passData,template=template)


    return render_template('document/templates.html')

@app.route("/document/editTemplateConfig", methods=['GET', 'POST'])
def documentEditTemplateConfig():

    if 'userID' not in session:
        return redirect(url_for('userLogin'))
    
    if request.method == 'POST':
        if request.form['action'] == 'editTemplatePreProcessingConfig':
            
            old_tempName = request.form.get('old_tempName')
            temp_name = request.form.get('tempName')
            print("testinng122333",temp_name)
            field_names = request.form.getlist('fieldName[]')
            extract_methods = request.form.getlist('extract_method[]')
            values = request.form.getlist('value[]')

            input_data = [{'fieldName': fn, 'extractMethod': em, 'value': v}
                        for fn, em, v in zip(field_names, extract_methods, values)]

            data_dict = json.loads(request.form.get('preconfig'))
            psm = data_dict.get('psm')
            pre_processing_config = data_dict.get('preProcessingConfig')

            data_to_update = {
                'tempName': temp_name,
                'psm': psm,
                'preProcessingConfig': pre_processing_config,
                'config': input_data
            }
            print("teassgasaga",data_to_update)

            # Query Firestore to find the document to update
            query = db.collection('template').where('tempName', '==', old_tempName).stream()

            # Assuming there's only one document with the specified temp_name
            for doc in query:
                # Update the existing document
                doc.reference.update(data_to_update)

            # Fetch updated data from Firestore to display
            query = db.collection('template').stream()
            templates = [doc.to_dict() for doc in query]

            return render_template('document/templates.html', templates=templates)
    
    return render_template('document/editTemplateConfig.html')

def convertToBool(value):
  if value == "True":
    return True
  else:
     return False

@app.route("/document/uploadImage", methods=['GET', 'POST'])
def uploadImage():

    if 'userID' not in session:
        return redirect(url_for('userLogin'))
    
    if request.method == 'POST':
        if request.form.get('action') == 'uploadFile':
            uploaded_file = request.files['file']
            print("testingFile456", uploaded_file.filename)
            if uploaded_file and allowed_file(uploaded_file.filename):
                # Convert PNG to JPG
                if uploaded_file.filename.lower().endswith('.png'):
                    image = Image.open(uploaded_file.stream)
                    print("testingFile733", image)
                    jpg_image_buffer = io.BytesIO()
                    image.convert('RGB').save(jpg_image_buffer, format="JPEG")
                    jpg_image_buffer.seek(0)

                    byte_data = jpg_image_buffer.read()

                    encoded_string = base64.b64encode(byte_data).decode('utf-8')

                    return render_template('document/uploadImage.html', image_data=encoded_string,image=uploaded_file.filename)
                
                else:
                
                    image_data = uploaded_file.read()
                    print("testingFile733", image_data)

                    encoded_string = base64.b64encode(image_data).decode('utf-8')
                    
                    return render_template('document/uploadImage.html', image_data=encoded_string,image=uploaded_file.filename)
            else:
                error_message=('Only JPG, JPEG, and PNG files are allowed.')

                return render_template('document/uploadImage.html', error_message=error_message, image=uploaded_file.filename)

        elif request.form.get('action') == 'confirm':

                image_data = request.form.get('imageUrl')
                psm = int(request.form.get('psm'))
                dilated_iterations = int(request.form.get('dilated_iterations'))
                eroded_iterations = int(request.form.get('eroded_iterations'))
                threshold = convertToBool(request.form.get('threshold'))
                kernel_size = int(request.form.get('kernelSize'))
                equalize_hist = convertToBool(request.form.get('equalizeHist'))
                morphologyEx_iterations = int(request.form.get('morphologyEx_iterations'))
                dilated = convertToBool(request.form.get('dilated'))
                morphologyEx = convertToBool(request.form.get('morphologyEx'))
                eroded = convertToBool(request.form.get('eroded'))
                denoised = convertToBool(request.form.get('denoised'))


                data = {
                    "image": image_data,
                    "psm": psm,
                    "preProcessingConfig": {
                        "dilated_iterations": dilated_iterations,
                        "eroded_iterations": eroded_iterations,
                        "threshold": threshold,
                        "kernelSize": kernel_size,
                        "equalizeHist": equalize_hist,
                        "morphologyEx_iterations": morphologyEx_iterations,
                        "dilated": dilated,
                        "morphologyEx": morphologyEx,
                        "eroded": eroded,
                        "denoised": denoised
                    }
                }
                
                passingData = {
                    "psm": psm,
                    "preProcessingConfig": {
                        "dilated_iterations": dilated_iterations,
                        "eroded_iterations": eroded_iterations,
                        "threshold": threshold,
                        "kernelSize": kernel_size,
                        "equalizeHist": equalize_hist,
                        "morphologyEx_iterations": morphologyEx_iterations,
                        "dilated": dilated,
                        "morphologyEx": morphologyEx,
                        "eroded": eroded,
                        "denoised": denoised
                    }
                }
                print("passingData", passingData)

                # Convert the dictionary to a JSON string with double quotes
                passData = json.dumps(passingData, ensure_ascii=False)

                print("passData", passData)

                API_ENDPOINT_URL = "https://c5df-103-52-192-245.ngrok-free.app/newtemplate/"


                response = requests.post(API_ENDPOINT_URL, json=data)

                if response.status_code == 200:
                #     Request was successful
                    result = response.json()
                    passResult = result['data']
                    passresult = json.dumps(passResult, ensure_ascii=False)
                    pass_result = json.loads(passresult)
                    print("testingresult", pass_result)

                return render_template('document/templateDetail.html', image_data=image_data, pass_result=pass_result, passData=passData)
    
    # Add a default return statement for cases when the request method is not 'POST'
    return render_template('document/uploadImage.html')
    
@app.route("/document/templateDetail", methods=['GET', 'POST'])
def templateDetail():

    if request.method == 'POST':
        if request.form.get('action') == 'next':

            passData = request.form.get('passData')
            pass_result_str = request.form.get('result')
            pass_result_str = pass_result_str.replace("'", "\"")
            print("pass_result_str:", pass_result_str)
            
            # Parse the JSON string into a Python list
            pass_result = json.loads(pass_result_str)
            
            print("passingData", passData)
            print("passingResult", pass_result)
    

            return render_template('document/customTemplate.html', passData=passData,pass_result=pass_result)

@app.route("/document/customTemplate", methods=['GET', 'POST'])
def customTemplate():

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'confirm':
            temp_name = request.form.get('tempName')
            field_names = request.form.getlist('fieldName[]')
            extract_methods = request.form.getlist('extract_method[]')
            values = request.form.getlist('value[]')

            input_data = [{'fieldName': fn, 'extractMethod': em, 'value': v}
                          for fn, em, v in zip(field_names, extract_methods, values)]

            # Assuming 'config' is a JSON string containing 'psm' and 'preProcessingConfig'
            data_dict = json.loads(request.form.get('config'))
            psm = data_dict.get('psm')
            pre_processing_config = data_dict.get('preProcessingConfig')

            data_to_store = {
                'tempName': temp_name,
                'psm': psm,
                'preProcessingConfig': pre_processing_config,
                'config': input_data
            }

            # Add data to Firestore
            db.collection('template').document().set(data_to_store)

            # Fetch updated data from Firestore to display
            query = db.collection('template').stream()
            templates = [doc.to_dict() for doc in query]

            return render_template('document/templates.html', templates=templates)

    # Retrieve the 'result' data from the form submission
    result_json = request.form.get('result')

    try:
        # Parse the JSON string to a Python object
        result = json.loads(result_json)
        print("Testing Result:", result)
        # Do something with the 'result' data in the customTemplate route
        # You can pass 'result' to the customTemplate.html template or process it as needed
        return render_template('document/customTemplate.html', result=result)
    except json.JSONDecodeError as e:
        print("Error decoding JSON:", e)

        return render_template('document/customTemplate.html')

@app.route("/document/trash", methods=['GET', 'POST'])
def documentTrash():
    if 'userID' not in session:
        return redirect(url_for('userLogin'))

    user_id = session['userID']
    # Initialize an empty list to store image links
    links = []
    trash_data_list = []
    unique_links = set()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'deleteTrash':
            # Retrieve the user's trash data from Firestore
            trash_ref = db.collection('trash')
            image_to_delete = request.form.get('imageToDelete')
            print(image_to_delete)

            if image_to_delete:
                # Delete the specific image from the trash
                trash_query = trash_ref.where('userID', '==', user_id).where('link', '==', image_to_delete).stream()
                
                for trash_doc in trash_query:
                    trash_doc.reference.delete()

                # Optionally, delete the corresponding image from Firebase Storage
                try:
                    file_name = image_to_delete.split('/')[-1].split('?')[0]  # Extract the file name from the URL
                    bucket_name = 'ocr-fyp-beea5.appspot.com'
                    storage_client = storage.bucket(bucket_name)
                    blob = storage_client.blob(file_name)
                    blob.delete()

                except Exception as e:
                    # Handle any errors that occur during deletion
                    print(f"Error deleting file {image_to_delete}: {str(e)}")
        


        elif action == 'searchFiles':
            search_query = request.form.get('search').strip().lower()

            # Retrieve trash data from Firestore based on the search query
            trash_ref = db.collection('trash')
            query = trash_ref.where('userID', '==', user_id).where('fileName', '>=', search_query).where('fileName', '<=', search_query + '\uf8ff')
            trash_query = query.stream()

            # Initialize an empty list to store search results
            trash_data_list = []

            if trash_query is not None:
                for trash_doc in trash_query:
                    trash_data = trash_doc.to_dict()

                    if 'link' in trash_data:
                        links = trash_data['link'].split(',')
                        for link in links:
                            clean_link = link.strip()
                            # Check if the search query matches the filename
                            if search_query in trash_data.get('fileName', '').lower():
                                trash_data_list.append({
                                    'link': clean_link,
                                    'file_name': trash_data.get('fileName', 'N/A'),
                                    'date_created': trash_data.get('createdDate', 'N/A'),
                                    'date_deleted': trash_data.get('deletedDate', 'N/A')
                                })
                                break  # Break out of the loop after finding a matching link

            return render_template('document/trash.html', trash_data_list=trash_data_list)

        elif action == 'restoreTrash':
            # Retrieve the user's trash data from Firestore
            trash_ref = db.collection('trash')
            image_to_restore = request.form.get('imageToRestore')
            print(image_to_restore)

            if image_to_restore:
                # Delete the specific image from the trash
                trash_query = trash_ref.where('userID', '==', user_id).where('link', '==', image_to_restore).stream()

                for trash_doc in trash_query:
                    trash_data = trash_doc.to_dict()
                    # Delete from trash collection
                    trash_doc.reference.delete()

                    # Add the image back to the images collection
                    images_ref = db.collection('images')
                    images_ref.add({
                        'userID': user_id,
                        'link': trash_data['link'],
                        'dateCreated': trash_data['createdDate'],
                        'fileName': trash_data['fileName'],  # Add other fields if needed
                        # Add more fields if needed
                    })
        
        elif action == 'logout':
            # Logout logic
            session.pop('userID', None)
            flash('You have been successfully logged out.', 'success')  # Optional: Display a flash message
            return redirect(url_for('userLogin'))


    # Retrieve trash data from Firestore
    trash_ref = db.collection('trash')
    trash_query = trash_ref.where('userID', '==', user_id).stream()

    for trash_doc in trash_query:
        trash_data = trash_doc.to_dict()
        print(trash_data)
        if 'link' in trash_data:
            links = trash_data['link'].split(',')
            for link in links:
                clean_link = link.strip()
                trash_data_list.append({
                    'link': clean_link,
                    'file_name': trash_data.get('fileName', 'N/A'),  # Extract the file name from the URL
                    'date_created': trash_data.get('createdDate', 'N/A'),
                    'date_deleted': trash_data.get('deletedDate', 'N/A')
                })

    return render_template('document/trash.html', trash_data_list=trash_data_list)
