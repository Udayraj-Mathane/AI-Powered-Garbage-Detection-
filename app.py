from flask import Flask, render_template, Response, send_file, request, redirect, url_for, session, flash
import cv2
import numpy as np
import supervision as sv
from roboflow import Roboflow
from datetime import datetime
import csv
import io
import mysql.connector

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

# Constants
PROJECT_NAME = "everestv2"

# Initialize Roboflow API
rf = Roboflow(api_key="saWylCfiQ28ZO6vMXUiW")
project = rf.workspace().project(PROJECT_NAME)
model = project.version(1).model

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',  # Replace with your MySQL username
    'password': 'Pass@123',  # Replace with your MySQL password
    'database': 'garbage_management'
}

# Function to get database connection
def get_db_connection():
    return mysql.connector.connect(**db_config)

# Hardcoded location
LOCATION = "Sipna College of Engineering and Technology, Amravati"

# Annotators
box_annotator = sv.BoundingBoxAnnotator(thickness=2)
label_annotator = sv.LabelAnnotator(text_scale=1.2, text_thickness=2)
tracker = sv.ByteTrack()

# Function to log detected garbage
def log_garbage(labels: list, task_id=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()

    for label in labels:
        try:
            cursor.execute('''
                INSERT INTO detection_data (garbage_type, location, coordinates, timestamp, task_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (label, LOCATION, "20.9346° N, 77.7641° E", timestamp, task_id))
            conn.commit()
            print(f"Logged: {label} at {LOCATION} on {timestamp} with task_id={task_id}")
        except mysql.connector.Error as err:
            print(f"Error: {err}")

    cursor.close()
    conn.close()

# Function to generate video frames
def generate_frames():
    cap = cv2.VideoCapture(0)  # Use 0 for the default camera
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    # Set a smaller frame size for faster processing
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture frame.")
            break

        # Debug: Print frame dimensions
        print(f"Frame dimensions: {frame.shape}")

        # Perform inference with the model
        results = model.predict(frame, confidence=70, overlap=30).json()
        print("Inference Results:", results)  # Debugging

        roboflow_format = {
            "predictions": results["predictions"],
            "image": {"width": frame.shape[1], "height": frame.shape[0]}
        }
        detections = sv.Detections.from_inference(roboflow_format)
        detections = tracker.update_with_detections(detections)

        # Extract labels
        labels = [pred['class'] for pred in results['predictions'][:len(detections)]]
        print("Labels:", labels)  # Debugging

        # Log detected garbage
        if labels:
            log_garbage(labels)

        # Annotate frame
        annotated_frame = box_annotator.annotate(frame, detections=detections)
        annotated_frame = label_annotator.annotate(annotated_frame, detections=detections, labels=labels)

        # Convert frame to JPEG
        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        if not ret:
            print("Error: Failed to encode frame.")
            continue

        # Debug: Print frame size
        print(f"Frame size: {len(buffer)} bytes")

        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form['role']
        username = request.form['username']
        password = request.form['password']

        if role == 'admin':
            # Admin login logic
            if username == 'admin' and password == 'admin123':  # Replace with database check
                session['logged_in'] = True
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error="Invalid admin credentials")
        elif role == 'cleaner':
            # Cleaner login logic
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cleaners WHERE username = %s AND password = %s', (username, password))
            cleaner = cursor.fetchone()
            cursor.close()
            conn.close()

            if cleaner:
                session['cleaner_logged_in'] = True
                session['cleaner_id'] = cleaner[0]  # Access the first column (id) by index
                return redirect(url_for('cleaner_dashboard'))
            else:
                return render_template('login.html', error="Invalid cleaner credentials")
        else:
            return render_template('login.html', error="Invalid role")

    return render_template('login.html')

# Logout route for admin
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Logout route for cleaner
@app.route('/cleaner_logout')
def cleaner_logout():
    session.pop('cleaner_logged_in', None)
    session.pop('cleaner_id', None)
    return redirect(url_for('login'))

# Route for the home page (Dashboard)
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch detection data grouped by location and date
    cursor.execute('''
        SELECT 
    MIN(id) AS id, 
    MIN(garbage_type) AS garbage_type, 
    location, 
    MIN(coordinates) AS coordinates, 
    DATE(timestamp) AS date
FROM detection_data
GROUP BY location, DATE(timestamp)
    ''')
    detection_data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('index.html', detection_data=detection_data)


# Route to add a new cleaner
@app.route('/add_cleaner', methods=['GET', 'POST'])
def add_cleaner():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Insert the new cleaner
            cursor.execute('INSERT INTO cleaners (name, contact, username, password) VALUES (%s, %s, %s, %s)',
                          (name, contact, username, password))
            conn.commit()
            flash('Cleaner added successfully!', 'success')  # Flash success message
        except mysql.connector.Error as err:
            flash(f'Error: {err}', 'error')  # Flash error message
        finally:
            cursor.close()
            conn.close()

        # Stay on the same page after form submission
        return redirect(url_for('add_cleaner'))

    return render_template('add_cleaner.html')

# Cleaner dashboard route
@app.route('/cleaner_dashboard')
def cleaner_dashboard():
    if not session.get('cleaner_logged_in'):
        return redirect(url_for('login'))

    cleaner_id = session['cleaner_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE cleaner_id = %s', (cleaner_id,))
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('cleaner_dashboard.html', tasks=tasks)

# Route to mark a task as completed
@app.route('/complete_task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    if not session.get('cleaner_logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Mark the task as completed
    cursor.execute('UPDATE tasks SET completed = TRUE WHERE id = %s', (task_id,))

    # Delete detection data associated with this task
    cursor.execute('DELETE FROM detection_data WHERE task_id = %s', (task_id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('cleaner_dashboard'))

# Route to assign a task
@app.route('/assign_task', methods=['GET', 'POST'])
def assign_task():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        cleaner_id = request.form['cleaner']
        location = request.form['location']
        due_date = datetime.now().strftime('%Y-%m-%d')  # Set due date as the current date

        try:
            # Insert the task and get the task ID
            cursor.execute('INSERT INTO tasks (cleaner_id, location, due_date) VALUES (%s, %s, %s)',
                          (cleaner_id, location, due_date))
            task_id = cursor.lastrowid  # Get the ID of the newly inserted task
            conn.commit()

            # Log garbage for this task
            log_garbage(labels=["dump"], task_id=task_id)  # Replace "dump" with actual garbage types

            flash('Task assigned successfully!', 'success')  # Flash success message
        except mysql.connector.Error as err:
            flash(f'Error: {err}', 'error')  # Flash error message
        finally:
            cursor.close()
            conn.close()

        # Stay on the same page after form submission
        return redirect(url_for('assign_task'))

    # Fetch cleaners and locations for the form
    cursor.execute('SELECT * FROM cleaners')
    cleaners = cursor.fetchall()

    cursor.execute('SELECT DISTINCT location FROM detection_data')
    locations = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('assign_task.html', cleaners=cleaners, locations=locations, datetime=datetime)

@app.route('/map_view')
def map_view():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all detected locations from the detection_data table
    cursor.execute('SELECT DISTINCT location, coordinates FROM detection_data')
    locations = cursor.fetchall()

    cursor.close()
    conn.close()

    # Pass the locations to the template
    return render_template('map_view.html', locations=locations)

@app.route('/cleaner_map_view')
def cleaner_map_view():
    if not session.get('cleaner_logged_in'):
        return redirect(url_for('login'))

    cleaner_id = session['cleaner_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch locations assigned to the cleaner
    cursor.execute('''
        SELECT DISTINCT location 
        FROM tasks 
        WHERE cleaner_id = %s
    ''', (cleaner_id,))
    locations = cursor.fetchall()

    cursor.close()
    conn.close()

    # Pass the locations to the template
    return render_template('cleaner_map_view.html', locations=locations)

# Route for the video feed
@app.route('/video_feed')
def video_feed():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

# Route to export the report as a CSV file
@app.route('/export_report')
def export_report():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch detection data grouped by location and date
    cursor.execute('''
        SELECT 
            MIN(id) AS id, 
            MIN(garbage_type) AS garbage_type, 
            location, 
            MIN(coordinates) AS coordinates, 
            DATE(timestamp) AS date
        FROM detection_data
        GROUP BY location, DATE(timestamp)
    ''')
    detection_data = cursor.fetchall()

    cursor.close()
    conn.close()

    # Create a CSV file in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Garbage Type", "Location", "Coordinates", "Date"])  # Add header

    for entry in detection_data:
        writer.writerow([entry[1], entry[2], entry[3], entry[4]])  # Skip the ID column

    # Send the CSV file to the user
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name="garbage_report.csv"
    )
    
if __name__ == '__main__':
    app.run(debug=True)