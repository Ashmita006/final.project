from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import csv
from io import StringIO
from fpdf import FPDF
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize Flask app and secret key
app = Flask(__name__)
app.secret_key = '3104'

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.create_all()'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False)
    section = db.Column(db.String(50), nullable=False)
    attendance = db.relationship('Attendance', backref='student', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(10), nullable=False) 

# Routes
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    students = Student.query.all()
    return render_template('dashboard.html', students=students)


@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        roll_number = request.form['roll_number']
        email = request.form['email']
        section = request.form['section']
        new_student = Student(name=name, roll_number=roll_number, email=email, section=section)
        
        try:
            db.session.add(new_student)
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            return f"Error occurred while adding student: {e}"

    return render_template('add_student.html')


@app.route('/edit_student/<int:id>', methods=['GET', 'POST'])
def edit_student(id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    student = Student.query.get(id)

    if request.method == 'POST':
        student.name = request.form['name']
        student.roll_number = request.form['roll_number']
        student.email = request.form['email']
        student.section = request.form['section']
        
        try:
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            return f"Error occurred while updating student: {e}"

    return render_template('edit_student.html', student=student)


@app.route('/delete_student/<int:id>', methods=['GET', 'POST'])
def delete_student(id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    student = Student.query.get(id)

    try:
        db.session.delete(student)
        db.session.commit()
        return redirect(url_for('dashboard'))
    except Exception as e:
        db.session.rollback()
        return f"Error occurred while deleting student: {e}"

@app.route('/view_students')
def view_students():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    # Fetch all students from the database
    students = Student.query.all()

    # Render the 'view_students.html' template and pass the student data
    return render_template('view_students.html', students=students)



@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    students = []
    if request.method == 'POST':
        section = request.form.get('section')
        if section:
            students = Student.query.filter_by(section=section).all()

        student_id = request.form.get('student_id')
        status = request.form.get('status')
        if student_id and status:
            date = datetime.now().strftime("%Y-%m-%d")
            attendance = Attendance(student_id=student_id, date=date, status=status)
            db.session.add(attendance)
            db.session.commit()

    sections = db.session.query(Student.section).distinct().all()
    return render_template('mark_attendance.html', sections=[s[0] for s in sections], students=students)


@app.route('/attendance_report')
def attendance_report():
    # Get attendance counts for Present, Absent, and Late statuses
    present_count = Attendance.query.filter_by(status="Present").count()
    absent_count = Attendance.query.filter_by(status="Absent").count()
    late_count = Attendance.query.filter_by(status="Late").count()

    labels = ['Present', 'Absent', 'Late']
    counts = [present_count, absent_count, late_count]

    # Get distinct sections
    sections = db.session.query(Student.section).distinct().all()

    # Calculate attendance percentage for each student
    students = Student.query.all()
    student_performance = []

    for student in students:
        total_classes = Attendance.query.filter_by(student_id=student.id).count()
        present_classes = Attendance.query.filter_by(student_id=student.id, status="Present").count()

        # Calculate attendance percentage
        attendance_percentage = (present_classes / total_classes) * 100 if total_classes else 0
        student_performance.append({
            'name': student.name,
            'roll_number': student.roll_number,
            'section': student.section,
            'attendance_percentage': attendance_percentage
        })

    # Generate Bar Graph for student attendance percentage
    attendance_data = [item['attendance_percentage'] for item in student_performance]
    student_names = [item['roll_number'] for item in student_performance]
    
    fig, ax = plt.subplots()
    ax.bar(student_names, attendance_data, color='skyblue')
    ax.set_xlabel('Students Roll')
    ax.set_ylabel('Attendance Percentage')
    ax.set_title('Student Attendance Percentage')

    # Convert the bar chart to an image URL
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)
    bar_chart_url = base64.b64encode(img.getvalue()).decode()

    # Generate Bar Graph for overall attendance status
    fig, ax = plt.subplots()
    ax.bar(labels, counts, color=['green', 'red', 'orange'])
    ax.set_title('Attendance Overview - Bar Graph')

    img_bar = io.BytesIO()
    fig.savefig(img_bar, format='png')
    img_bar.seek(0)
    bar_chart_url_overview = base64.b64encode(img_bar.getvalue()).decode()

    # Generate Line Graph for attendance trend
    fig, ax = plt.subplots()
    ax.plot(labels, counts, marker='o', linestyle='-', color='blue')
    ax.set_title('Attendance Trend - Line Graph')

    img_line = io.BytesIO()
    fig.savefig(img_line, format='png')
    img_line.seek(0)
    line_chart_url = base64.b64encode(img_line.getvalue()).decode()

    # Render the attendance_report.html template with the required data
    return render_template('attendance_report.html',
                           sections=[s[0] for s in sections],
                           student_performance=student_performance,
                           bar_chart_url=bar_chart_url,
                           bar_chart_url_overview=bar_chart_url_overview,
                           line_chart_url=line_chart_url)


@app.route('/download_attendance_pdf')
def download_attendance_pdf():
    attendance_data = Attendance.query.all()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, "Attendance Report", ln=True, align="C")
    
    pdf.set_font("Arial", size=12)
    pdf.ln(10)  # Line break
    
    pdf.cell(50, 10, "Student ID", 1)
    pdf.cell(50, 10, "Date", 1)
    pdf.cell(50, 10, "Status", 1)
    pdf.ln()

    for record in attendance_data:
        pdf.cell(50, 10, str(record.student_id), 1)
        pdf.cell(50, 10, record.date, 1)
        pdf.cell(50, 10, record.status, 1)
        pdf.ln()

    response = Response(pdf.output(dest='S').encode('latin1'))
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=attendance_report.pdf"
    return response


@app.route('/download_attendance_csv')
def download_attendance_csv():
    attendance_data = Attendance.query.all()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['Student ID', 'Date', 'Status'])  # Header row

    for record in attendance_data:
        writer.writerow([record.student_id, record.date, record.status])
    
    output = si.getvalue()
    
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=attendance_report.csv"
    return response


@app.route('/send_late_email')
def send_late_email():
    late_students = Student.query.join(Attendance, Student.id == Attendance.student_id) \
        .filter(Attendance.status == 'Late').all()

    for student in late_students:
        send_email(student.email, student.name)

    return render_template('send_late_email.html')

def send_email(to_email, student_name):
    from_email = "ashmitashrestha613@gmail.com"
    password = "wtkq mfjc giyo vhwh"
    subject = "Attendance Notice: Late Arrival"
    body = f"Dear {student_name},\n\nYou were marked as late today. Please ensure timely attendance.\n\nBest regards,\nAttendance Team"

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Error: {e}"
              )

@app.route('/low_attendance_email')
def low_attendance_email():
  
    low_attendance_students = get_students_with_low_attendance()

    for student in low_attendance_students:
        send_email(student.email, student.name)

    return render_template('low_attendance_email.html')


def get_students_with_low_attendance():
    students_with_low_attendance = []

    students = Student.query.all()
    for student in students:
        total_classes = Attendance.query.filter_by(student_id=student.id).count()
        attended_classes = Attendance.query.filter_by(student_id=student.id, status='Present').count()

        if total_classes > 0:
            attendance_percentage = (attended_classes / total_classes) * 100
            if attendance_percentage < 50:
                student.attendance_percentage = round(attendance_percentage, 2)
                students_with_low_attendance.append(student)

    return students_with_low_attendance


def send_email(to_email, student_name):
    from_email = "ashmitashrestha613@gmail.com"
    password = "wtkq mfjc giyo vhwh"
    subject = "Attendance Notice: Low Attendance"
    body = f"Dear {student_name},\n\nYou have been marked with low attendance. Please make sure to attend classes regularly.\n\nBest regards,\nAttendance Team"

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")


# APScheduler background job for sending low attendance emails daily
scheduler = BackgroundScheduler()

def send_automatic_emails_for_low_attendance():
    low_attendance_students = get_students_with_low_attendance()
    for student in low_attendance_students:
        send_email(student.email, student.name)

# Add job to scheduler to send emails every day
scheduler.add_job(func=send_automatic_emails_for_low_attendance, trigger="interval", hours=24)
scheduler.start()


# Initialize Database and Start the Application
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create database tables if not exist
    app.run(debug=True)
