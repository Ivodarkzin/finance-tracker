from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'troque-esta-chave-em-producao'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar essa página.'


# ---------------------- MODELOS ----------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    expenses = db.relationship('Expense', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    expenses = db.relationship('Expense', backref='category', lazy=True)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------- AUTENTICAÇÃO ----------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        if not username or not password:
            flash('Preencha todos os campos.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Esse usuário já existe.', 'danger')
            return redirect(url_for('register'))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Conta criada com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))

        flash('Usuário ou senha inválidos.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------------- DASHBOARD ----------------------

@app.route('/')
@login_required
def dashboard():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    total = sum(e.amount for e in expenses)

    # Totais agrupados por categoria (para o gráfico)
    by_category = (
        db.session.query(Category.name, func.sum(Expense.amount))
        .join(Expense)
        .filter(Expense.user_id == current_user.id)
        .group_by(Category.name)
        .all()
    )

    chart_labels = [c[0] for c in by_category]
    chart_values = [round(c[1], 2) for c in by_category]

    return render_template(
        'dashboard.html',
        expenses=expenses,
        total=total,
        chart_labels=chart_labels,
        chart_values=chart_values
    )


# ---------------------- CRUD DE GASTOS ----------------------

@app.route('/expense/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    categories = Category.query.all()

    if request.method == 'POST':
        description = request.form['description'].strip()
        amount = request.form['amount']
        date_str = request.form['date']
        category_id = request.form['category_id']

        try:
            amount = float(amount)
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Valor ou data inválidos.', 'danger')
            return redirect(url_for('add_expense'))

        expense = Expense(
            description=description,
            amount=amount,
            date=date,
            user_id=current_user.id,
            category_id=category_id
        )
        db.session.add(expense)
        db.session.commit()
        flash('Gasto adicionado com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_expense.html', categories=categories)


@app.route('/expense/edit/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)

    if expense.user_id != current_user.id:
        flash('Você não tem permissão para editar esse gasto.', 'danger')
        return redirect(url_for('dashboard'))

    categories = Category.query.all()

    if request.method == 'POST':
        expense.description = request.form['description'].strip()
        expense.amount = float(request.form['amount'])
        expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        expense.category_id = request.form['category_id']

        db.session.commit()
        flash('Gasto atualizado com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('edit_expense.html', expense=expense, categories=categories)


@app.route('/expense/delete/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)

    if expense.user_id != current_user.id:
        flash('Você não tem permissão para excluir esse gasto.', 'danger')
        return redirect(url_for('dashboard'))

    db.session.delete(expense)
    db.session.commit()
    flash('Gasto removido.', 'success')
    return redirect(url_for('dashboard'))


# ---------------------- INICIALIZAÇÃO ----------------------

def seed_categories():
    """Cria categorias padrão caso ainda não existam."""
    default_categories = ['Alimentação', 'Transporte', 'Moradia', 'Lazer', 'Saúde', 'Educação', 'Outros']
    for name in default_categories:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
    db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_categories()
    app.run(debug=True)
