from radiology_assistant import app, bcrypt, db
from flask import render_template, redirect, url_for, flash, request, session, g
from flask_login import current_user, login_user, logout_user
from radiology_assistant.models import User, Case, Disease
from radiology_assistant.forms import RegistrationForm, LoginForm, ImageUploadForm, MedicalReportForm, SearchForm, UpdateAccountForm
from radiology_assistant.utils import save_temp_image, image_in_temp, model, UserSession

@app.route("/", methods=['GET', 'POST'])
def home():
    form = ImageUploadForm()
    if form.is_submitted():
        if form.validate():
            # save_temp_image(form.image.data, 600)
            UserSession.set_uploaded_image(form.image.data)
            return redirect(url_for("confirm"))
        else:
            flash("Something went wrong. Please make sure you uploaded either a .png or .jpg image.", "danger")
    return render_template("home.html", form=form)

@app.route("/confirm", methods=['GET', 'POST'])
def confirm():
    user_image_name = UserSession.get_uploaded_image()
    if user_image_name is None:
        flash("You can't confirm an image until you upload an image!", "danger")
        return redirect(url_for("home"))
    else:
        return render_template("confirmation.html", img_name=user_image_name)

@app.before_request
def before_request():
    g.search_form = SearchForm()
    
@app.route("/search")
def search():
    if g.search_form.validate():
        page = request.args.get('page', 1, type=int)
        diseases = Disease.query.filter(Disease.name.like(f"%{g.search_form.query.data}%")).paginate(page=page, per_page=60)
        return render_template("search.html", diseases=diseases)
    else:
        return redirect(url_for("home"))

@app.route("/results", methods=['GET', 'POST'])
def results():
    user_image_name = UserSession.get_uploaded_image()
    if user_image_name is None:
        flash("Session timed out. Please upload another image.", "danger")
        return redirect(url_for("home"))

    form = MedicalReportForm()
    if request.method == "POST":
        if form.validate_on_submit():
            UserSession.finalize_image()
            results = UserSession.get_detected_results()
            case = Case(image=user_image_name, patient=form.patient_name.data, details=form.additional_details.data, user=current_user)
            db.session.add(case)
            for disease, percentage in results:
                d = Disease(case=case, name=disease, percentage=percentage)
                db.session.add(d)

            for disease in form.additional_diseases.data.split(","):
                d = Disease(case=case, name=disease.strip(" "))
                db.session.add(d)

            db.session.commit()
            return redirect(url_for("report", report_id=case.id))

    elif request.method == "GET":
        results = model(user_image_name)
        UserSession.set_detected_results(results)
        results = [(disease, int(pct*100)) for disease, pct in results]
        summary = ""
        for x in range(len(results)):
            if (x == (len(results)-1) and x != 0):
                summary += "and "
            if results[x][1] < 15:
                summary += str("Atypical showing signs of " + results[x][0])
            elif results[x][1] < 25:
                summary += str("Acute symptoms of " + results[x][0])
            elif results[x][1] < 65:
                summary += str("Moderate symptoms of " + results[x][0])
            else:
                summary += str("Severe symptoms of " + results[x][0])
            if x < (len(results)-1):
                summary += ", "
        return render_template("results.html", image=user_image_name, results=results, user_auth=current_user.is_authenticated, form=form, summary= summary)

@app.route("/report/<int:report_id>")
def report(report_id):
    case = Case.query.filter_by(id=report_id).first_or_404()
    detected = []
    additional = []
    for disease in case.diseases:
        if disease.percentage is None:
            additional.append(disease)
        else:
            detected.append(disease)
    return render_template("report.html", case=case, detected=detected, additional=additional)

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(firstname=form.firstname.data, lastname=form.lastname.data, username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You may now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check username and password and try again.', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route("/account/admin")
def admin():
    return render_template("admin.html")

@app.route("/account/cases")
def user_cases():
    return render_template("user_cases.html", cases=current_user.cases)

@app.route("/account/settings", methods=['GET', 'POST'])
def account_settings():
    form = UpdateAccountForm()

    if form.validate_on_submit():
        current_user.firstname = form.firstname.data
        current_user.lastname = form.lastname.data
        current_user.username = form.username.data
        current_user.email = form.email.data
        if len(form.password.data) > 0:
            current_user.password = bcrypt.generate_password_hash(form.password.data).decode('utf-8') 
        db.session.commit()
        flash("Your account settings have been updated.", "success")
        return redirect(url_for("home"))
    elif request.method == "GET":
        form.firstname.data = current_user.firstname
        form.lastname.data = current_user.lastname
        form.username.data = current_user.username
        form.email.data = current_user.email

    return render_template("settings.html", form=form)
