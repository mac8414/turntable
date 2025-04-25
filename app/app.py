from flask import Flask, flash, render_template, jsonify, request, redirect, url_for
import os
import requests
from flask_mail import Mail, Message
import logging
from flask_compress import Compress

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
Compress(app)

# Configuring Flask-Mail with Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'turntablehelp@gmail.com' 
app.config['MAIL_PASSWORD'] = 'fnuj qfow rnlt yaym'  
app.config['MAIL_DEFAULT_SENDER'] = 'turntablehelp@gmail.com'

mail = Mail(app)

RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

@app.route('/')
def index():
    logger.info("Redirecting to /home")
    return redirect('/home')

@app.route('/about')
def about():
    logger.info("Rendering about page")
    return render_template('about.html')

@app.route('/contact')
def contact():
    logger.info("Rendering contact page")
    return render_template('contact.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/home')
def home():
    logger.info("Rendering home page")
    return render_template('home.html')

# Route for Success Page
@app.route('/success')
def success():
    logger.info("Rendering success page")
    return render_template('success.html')  

@app.route('/our-pick')
def our_pick():
    logger.info("Rendering our pick page")
    album = get_album("Songs in the Key of Life")
    artist = get_artist("Stevie Wonder")
    return render_template('our-pick.html', album=album, artist=artist)

@app.route("/contact-help", methods=["POST"])
def contact_help():
    name = request.form.get("name")
    email = request.form.get("email")
    message = request.form.get("message")
    recaptcha_response = request.form.get("g-recaptcha-response")

    if not name or not email or not message:
        flash("All fields are required.", "error")
        return redirect(url_for("contact"))

    if not recaptcha_response:
        flash("Please complete the CAPTCHA.", "error")
        return redirect(url_for("contact"))

    verify_url = "https://www.google.com/recaptcha/api/siteverify"
    payload = {
        "secret": RECAPTCHA_SECRET_KEY,
        "response": recaptcha_response
    }

    try:
        r = requests.post(verify_url, data=payload)
        result = r.json()
        if not result.get("success"):
            flash("CAPTCHA failed. Please try again.", "error")
            return redirect(url_for("contact"))
    except Exception:
        flash("CAPTCHA validation error.", "error")
        return redirect(url_for("contact"))

    try:
        msg = Message(
            subject="New Contact Message",
            sender=email,
            recipients=["turntablehelp@gmail.com"],
            body=f"From: {name}\nEmail: {email}\n\nMessage:\n{message}"
        )
        mail.send(msg)
        flash("Message sent successfully!", "success")
        return redirect(url_for("success"))
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        flash("There was an error sending your message. Please try again.", "error")
        return redirect(url_for("contact"))

# # Run the test    
if __name__ == "__main__":
     app.run(debug=True)
