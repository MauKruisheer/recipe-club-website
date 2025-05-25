import os
import re
import json
import csv
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from models import db, User, Recipe, Rating

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))

# Build a dict mapping ingredient names → list of allowed units
INGREDIENTS_UNITS = {}
csv_path = os.path.join(basedir, 'data', 'ingredients_units.csv')
with open(csv_path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        INGREDIENTS_UNITS[row['ingredient']] = [
            u.strip() for u in row['units'].split(',')
        ]

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(
    basedir, 'instance/site.db'
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

# Extensions
mail = Mail(app)
db.init_app(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/")
def home():
    """Public landing: all public recipes."""
    public_recipes = Recipe.query.filter_by(is_public=True).all()
    return render_template("recipes.html", recipes=public_recipes)


@app.route("/profile")
@login_required
def profile():
    """Your dashboard / profile page."""
    user_recipes     = Recipe.query.filter_by(user_id=current_user.id).all()
    favorite_recipes = current_user.favorites.all()
    return render_template(
        "dashboard.html",
        recipes=user_recipes,
        favorites=favorite_recipes
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""
    if request.method == "POST":
        username = request.form["username"]
        email    = request.form["email"]
        password = request.form["password"]
        existing = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing:
            message = "Username or email already exists."
        else:
            hashed_pw = generate_password_hash(password)
            new_user  = User(
                username=username,
                email=email,
                password=hashed_pw,
                is_verified=False
            )
            db.session.add(new_user)
            db.session.commit()

            token = serializer.dumps(email, salt='email-confirm')
            link  = url_for('confirm_email', token=token, _external=True)
            msg   = Message(
                "Confirm your Recipe Club email",
                recipients=[email]
            )
            msg.body = f"Click the link to verify your account: {link}"
            mail.send(msg)

            return (
                "Please check your email to verify your account. "
                "<a href='/login'>Click here to log in</a> once verified."
            )

    return render_template("register.html", message=message)


@app.route("/confirm/<token>")
def confirm_email(token):
    try:
        email = serializer.loads(token, salt='email-confirm', max_age=3600)
    except (SignatureExpired, BadSignature):
        return "The confirmation link is invalid or/or has expired."

    user = User.query.filter_by(email=email).first_or_404()
    if user.is_verified:
        return "Account already verified."
    user.is_verified = True
    db.session.commit()
    return "Your account has been verified. You can now log in."


@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]
        user     = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            if not user.is_verified:
                message = "Please verify your email before logging in."
            else:
                login_user(user)
                return redirect(url_for("profile"))
        else:
            message = "Invalid email or password."

    return render_template("login.html", message=message)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        # Gather manual‐entry form data
        title        = request.form["title"]
        ingredients  = "\n".join(request.form.getlist("ingredient[]"))
        instructions = "\n".join(request.form.getlist("instruction[]"))
        is_public    = "is_public" in request.form

        # If this request came after an import, grab and clear the prefill
        pre = session.pop("prefill_data", None)
        image_url = None
        if pre and pre.get("image"):
            image_url = pre["image"]
        print("🔍 image_url:", image_url)

        # Create & save recipe, including image if present
        new_recipe = Recipe(
            title        = title,
            ingredients  = ingredients,
            instructions = instructions,
            is_public    = is_public,
            user_id      = current_user.id,
            image        = image_url          # ← new field
        )
        db.session.add(new_recipe)
        db.session.commit()

        flash("Recipe uploaded!", "success")
        return redirect(url_for('home'))

    # GET: render with any leftover prefill (title/ings/steps)  
    return render_template(
        "upload_recipe.html",
        ingredients_list = list(INGREDIENTS_UNITS.keys()),
        units_map        = INGREDIENTS_UNITS,
        prefill          = session.pop("prefill_data", None),
        message          = None
    )

    # GET: render with any leftover prefill (title/ings/steps)  
    return render_template(
        "upload_recipe.html",
        ingredients_list = list(INGREDIENTS_UNITS.keys()),
        units_map        = INGREDIENTS_UNITS,
        prefill          = session.pop("prefill_data", None),
        message          = None
    )

@app.route("/upload-from-url", methods=["POST"])
@login_required
def upload_from_url():
    url = request.form["recipe_url"].strip()
    session["prefill_url"] = url

    # Only Jamie Oliver for this demo
    if "jamieoliver.com" not in url:
        flash("Currently only JamieOliver.com recipes are supported.", "warning")
        return redirect(url_for("upload"))

    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    data = None

    # Grab JSON-LD <script> blocks
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            jd = json.loads(tag.string)
            if isinstance(jd, list):
                # sometimes it's an array
                jd = next((x for x in jd if x.get("@type") == "Recipe"), None)
            if jd and jd.get("@type") == "Recipe":
                data = jd
                break
        except Exception:
            continue

    if not data:
        flash("Couldn’t find recipe data on that page.", "danger")
        return redirect(url_for("upload"))

    # Title & image
    title = data.get("name", "")
    image = data.get("image")
    if isinstance(image, list):
        image = image[0]

    # Ingredients: just flat strings
    raw_ings = data.get("recipeIngredient", [])
    ingredients = [i.strip() for i in raw_ings]

    # Instructions: handle list-of-objects or single string
    raw_instr = data.get("recipeInstructions", [])
    instructions = []
    if isinstance(raw_instr, list):
        for step in raw_instr:
            if isinstance(step, dict) and step.get("text"):
                instructions.append(step["text"].strip())
            else:
                instructions.append(str(step).strip())
    else:
        # fallback: split single string on “. ”
        text = str(raw_instr)
        for sentence in text.split(". "):
            s = sentence.strip()
            if s:
                if not s.endswith("."):
                    s += "."
                instructions.append(s)

    prefill = {
        "title": title,
        "image": image,
        "ingredients": ingredients,
        "instructions": instructions
    }
    session["prefill_data"] = prefill
    flash("Imported from Jamie Oliver! Adjust below then hit Upload.", "success")
    return redirect(url_for("upload"))


@app.route("/recipes")
def recipes():
    public_recipes = Recipe.query.filter_by(is_public=True).all()
    return render_template("recipes.html", recipes=public_recipes)


@app.route("/favorite/<int:recipe_id>", methods=["POST"])
@login_required
def favorite(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe not in current_user.favorites:
        current_user.favorites.append(recipe)
        db.session.commit()
    return redirect(request.referrer or url_for("home"))


@app.route("/unfavorite/<int:recipe_id>", methods=["POST"])
@login_required
def unfavorite(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe in current_user.favorites:
        current_user.favorites.remove(recipe)
        db.session.commit()
    return redirect(request.referrer or url_for("home"))


@app.route("/rate/<int:recipe_id>", methods=["POST"])
@login_required
def rate_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id == current_user.id:
        return "You can't rate your own recipe.", 403

    score = int(request.form["score"])
    existing = Rating.query.filter_by(
        user_id=current_user.id,
        recipe_id=recipe_id
    ).first()
    if existing:
        existing.score = score
    else:
        new_rating = Rating(
            score=score,
            user_id=current_user.id,
            recipe_id=recipe_id
        )
        db.session.add(new_rating)
    db.session.commit()
    return redirect(request.referrer or url_for("recipes"))


@app.route("/recipe/<int:recipe_id>")
def view_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    return render_template("view_recipe.html", recipe=recipe, request=request)


@app.route("/delete/<int:recipe_id>", methods=["POST"])
@login_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        return "Unauthorized", 403
    db.session.delete(recipe)
    db.session.commit()
    return redirect(url_for("profile"))


@app.route("/edit/<int:recipe_id>", methods=["GET", "POST"])
@login_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        return "Unauthorized", 403

    if request.method == "POST":
        recipe.title        = request.form["title"]
        recipe.ingredients  = request.form["ingredients"]
        recipe.instructions = request.form["instructions"]
        recipe.is_public    = "is_public" in request.form
        db.session.commit()
        return redirect(url_for("profile"))

    return render_template("edit_recipe.html", recipe=recipe)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    message = ""
    if request.method == "POST":
        email = request.form["email"]
        user  = User.query.filter_by(email=email).first()
        if user:
            token = serializer.dumps(email, salt='password-reset')
            link  = url_for('reset_password', token=token, _external=True)
            msg   = Message("Password Reset for Recipe Club",
                            recipients=[email])
            msg.body = f"Click the link to reset your password: {link}"
            mail.send(msg)
            message = "Check your email for a password reset link."
        else:
            message = "No account found with that email."
    return render_template("forgot_password.html", message=message)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset', max_age=3600)
    except (SignatureExpired, BadSignature):
        return "The password reset link is invalid or has expired."

    user = User.query.filter_by(email=email).first_or_404()
    if request.method == "POST":
        new_pw        = request.form["password"]
        user.password = generate_password_hash(new_pw)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("reset_password.html", email=email)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
