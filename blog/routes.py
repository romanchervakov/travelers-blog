import os
import secrets
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort
from blog import app, db, bcrypt, mail
from blog.forms import (RegistrationForm, LoginForm, UpdateAccountForm, PostForm, RequestResetForm, ResetPasswordForm)
from blog.models import User, Post, Favorites
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message
import nltk
import re


@app.route("/")
@app.route("/home")
def home():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    ids = None
    if current_user.is_authenticated:
        fav = Favorites.query.filter_by(user_id=current_user.id).all()
        ids = [i.post_id for i in fav]
        if not ids:
            ids = True
    return render_template('home.html', posts=posts, ids=ids)


@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password!', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)

    output_size = (1000, 1000)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data and not form.del_pic.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        if form.del_pic.data:
            current_user.image_file = 'default.jpg'
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account',
                           image_file=image_file, form=form)


def my_tokenizer(text):
    tokens = [w for w in nltk.word_tokenize(text)
              if not re.match('.*[!"#$%&\'()*+,./:;<=>?@[\\]^_`{|}~]', w)]
    tokens = ' '.join(tokens)
    return tokens


@app.route("/post/new", methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    post = None
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, author=current_user)
        post.fav = 0
        if form.picture1.data and not form.del_pic1.data:
            picture_file1 = save_picture(form.picture1.data)
            post.picture_1 = picture_file1
        if form.picture2.data and not form.del_pic2.data:
            picture_file2 = save_picture(form.picture2.data)
            post.picture_2 = picture_file2
        if form.picture3.data and not form.del_pic3.data:
            picture_file3 = save_picture(form.picture3.data)
            post.picture_3 = picture_file3
        if form.long and form.lat:
            try:
                float(form.long.data) and float(form.lat.data)
            except ValueError:
                post.long = None
                post.lat = None
            else:
                post.long = form.long.data
                post.lat = form.lat.data
        if form.place:
            post.place = my_tokenizer(form.place.data)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('home'))
    return render_template('create_post.html', title='New Post',
                           form=form, legend='New Post', post=post)


@app.route("/post/<int:post_id>")
def post(post_id):
    check = True
    post = Post.query.get_or_404(post_id)
    if current_user.is_authenticated:
        fav = Favorites.query.filter_by(user_id=current_user.id, post_id=post_id).all()
    else:
        fav = None
        check = False
    return render_template('post.html', title=post.title, post=post, fav=fav, check=check)


@app.route("/add_to_favorites/<int:post_id>", methods=['GET', 'POST'])
@login_required
def add_to_favorites(post_id):
    post = Post.query.get_or_404(post_id)
    post.fav += 1
    fav = Favorites()
    fav.post_id = post_id
    fav.user_id = current_user.id
    db.session.add(fav)
    db.session.commit()
    return redirect(request.referrer)


@app.route("/remove_from_favorites/<int:post_id>", methods=['GET', 'POST'])
@login_required
def remove_from_favorites(post_id):
    post = Post.query.get_or_404(post_id)
    post.fav -= 1
    Favorites.query.filter_by(user_id=current_user.id, post_id=post_id).delete()
    db.session.commit()
    return redirect(request.referrer)


@app.route("/post/<int:post_id>/update", methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.fav = 0
        post.title = form.title.data
        post.content = form.content.data
        if form.picture1.data and not form.del_pic1.data:
            picture_file1 = save_picture(form.picture1.data)
            post.picture_1 = picture_file1
        if form.picture2.data and not form.del_pic2.data:
            picture_file2 = save_picture(form.picture2.data)
            post.picture_2 = picture_file2
        if form.picture3.data and not form.del_pic3.data:
            picture_file3 = save_picture(form.picture3.data)
            post.picture_3 = picture_file3
        if form.del_pic1.data:
            post.picture_1 = None
        if form.del_pic2.data:
            post.picture_2 = None
        if form.del_pic3.data:
            post.picture_3 = None
        if form.long and form.lat:
            try:
                float(form.long.data) and float(form.lat.data)
            except ValueError:
                post.long = None
                post.lat = None
            else:
                post.long = form.long.data
                post.lat = form.lat.data
        if form.place:
            post.place = my_tokenizer(form.place.data)
        db.session.commit()
        return redirect(url_for('post', post_id=post.id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
        form.long.data = post.long
        form.lat.data = post.lat
        form.place.data = post.place
    return render_template('create_post.html', title='Update Post',
                           form=form, legend='Update Post', post=post)


@app.route("/post/<int:post_id>/delete", methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    Favorites.query.filter_by(user_id=current_user.id, post_id=post_id).delete()
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted!', 'success')
    return redirect(url_for('home'))


@app.route("/account/<int:user_id>/delete", methods=['POST'])
@login_required
def delete(user_id):
    acc = User.query.get_or_404(user_id)
    if acc.id != current_user.id:
        abort(403)
    User.query.filter(User.id == user_id).delete()
    Post.query.filter(Post.user_id == user_id).delete()
    Favorites.query.filter(Favorites.user_id == user_id).delete()
    db.session.commit()
    flash('Your Account Was Successfully Deleted!', 'success')
    return redirect(url_for('login'))


@app.route("/favorites")
@login_required
def favorites():
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(id=current_user.id).first_or_404()
    posts = Post.query.filter(Post.fav != 0) \
        .order_by(Post.date_posted.desc()) \
        .paginate(page=page, per_page=5)
    fav = Favorites.query.filter_by(user_id=current_user.id).all()
    ids = [i.post_id for i in fav]
    return render_template('favorites.html', title='Favorites', posts=posts, user=user, ids=ids)


@app.route("/user/<string:username>")
def user_posts(username):
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author=user) \
        .order_by(Post.date_posted.desc()) \
        .paginate(page=page, per_page=5)
    ids = None
    if current_user.is_authenticated:
        fav = Favorites.query.filter_by(user_id=current_user.id).all()
        ids = [i.post_id for i in fav]
        if not ids:
            ids = True
    return render_template('user_posts.html', posts=posts, user=user, ids=ids)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)


@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', form=form)


@app.route("/reset_password/demo", methods=['GET', 'POST'])
def reset_token():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)
