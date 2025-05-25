from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# Association table for favorites (if you still need it)
favorites = db.Table(
    'favorites',
    db.Column('user_id',   db.Integer, db.ForeignKey('user.id'),   primary_key=True),
    db.Column('recipe_id', db.Integer, db.ForeignKey('recipe.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id           = db.Column(db.Integer,   primary_key=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    email        = db.Column(db.String(120),unique=True, nullable=False)
    password     = db.Column(db.String(200), nullable=False)
    is_verified  = db.Column(db.Boolean,    default=False)

    # one‐to‐many: User → Recipe
    recipes      = db.relationship(lambda: Recipe, back_populates="user", lazy=True)

    # many‐to‐many: favorites
    favorites    = db.relationship(
        lambda: Recipe,
        secondary=favorites,
        back_populates="favorited_by",
        lazy='dynamic'
    )

    # one‐to‐many: User → Rating
    ratings      = db.relationship(lambda: Rating, back_populates="user", lazy=True)


class Recipe(db.Model):
    __tablename__ = 'recipe'

    id           = db.Column(db.Integer,   primary_key=True)
    title        = db.Column(db.String(120), nullable=False)
    ingredients  = db.Column(db.Text,      nullable=False)
    instructions = db.Column(db.Text,      nullable=False)
    is_public    = db.Column(db.Boolean,   default=True)
    user_id      = db.Column(db.Integer,   db.ForeignKey("user.id"), nullable=False)
    image        = db.Column(db.String(512), nullable=True)

    # back to its author
    user         = db.relationship(lambda: User, back_populates="recipes")

    # who favorited it?
    favorited_by = db.relationship(
        lambda: User,
        secondary=favorites,
        back_populates="favorites",
        lazy='dynamic'
    )

    # ratings coming in
    ratings      = db.relationship(lambda: Rating, back_populates="recipe", lazy=True)

    @property
    def average_rating(self):
        if not self.ratings:
            return None
        return round(sum(r.score for r in self.ratings) / len(self.ratings), 1)


class Rating(db.Model):
    __tablename__ = 'rating'

    id        = db.Column(db.Integer, primary_key=True)
    score     = db.Column(db.Integer, nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

    user      = db.relationship(lambda: User,   back_populates="ratings")
    recipe    = db.relationship(lambda: Recipe, back_populates="ratings")