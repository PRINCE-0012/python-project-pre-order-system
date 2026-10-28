from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB_PATH = Path(__file__).with_name("campus_food.db")

MENU = {
    1: ("Burger", 60),
    2: ("Pizza", 100),
    3: ("Sandwich", 50),
    4: ("Samosa", 20),
    5: ("Chole Bhature", 80),
    6: ("Cold Drink", 40),
    7: ("Coffee", 30),
    8: ("Tea", 20),
}


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                token INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                roll_no TEXT NOT NULL,
                subtotal REAL NOT NULL,
                discount REAL NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Preparing',
                created_at TEXT NOT NULL,
                pickup TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token INTEGER NOT NULL,
                food_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY(token) REFERENCES orders(token) ON DELETE CASCADE
            );
        """)


def get_order_items(db, token):
    rows = db.execute(
        "SELECT food_name, price, quantity FROM order_items WHERE token = ? ORDER BY id",
        (token,)
    ).fetchall()
    return [dict(row) for row in rows]


def active_orders(db):
    return db.execute(
        "SELECT token FROM orders WHERE status != 'Cancelled' ORDER BY token"
    ).fetchall()


@app.route("/")
def index():
    return render_template("index.html", menu=MENU)


@app.route("/place-order", methods=["POST"])
def place_order():
    name = request.form.get("student_name", "").strip()
    roll_no = request.form.get("roll_no", "").strip()

    if not name or not roll_no:
        flash("Please enter both your name and roll number.", "error")
        return redirect(url_for("index"))

    cart = []
    for number, (food_name, price) in MENU.items():
        try:
            quantity = int(request.form.get(f"quantity_{number}", "0") or 0)
        except ValueError:
            flash("Please enter valid whole-number quantities.", "error")
            return redirect(url_for("index"))

        if quantity < 0:
            flash("Quantity cannot be negative.", "error")
            return redirect(url_for("index"))
        if quantity > 0:
            cart.append({
                "name": food_name,
                "price": price,
                "quantity": quantity
            })

    if not cart:
        flash("Please select at least one food item.", "error")
        return redirect(url_for("index"))

    subtotal = sum(item["price"] * item["quantity"] for item in cart)
    discount = round(subtotal * 0.10, 2) if subtotal >= 300 else 0
    total = round(subtotal - discount, 2)
    now = datetime.now()

    with get_db() as db:
        position = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status != 'Cancelled'"
        ).fetchone()[0] + 1
        waiting_time = position * 5
        pickup = (now + timedelta(minutes=waiting_time)).strftime("%I:%M %p")
        cursor = db.execute(
            """INSERT INTO orders
               (student_name, roll_no, subtotal, discount, total, status, created_at, pickup)
               VALUES (?, ?, ?, ?, ?, 'Preparing', ?, ?)""",
            (name, roll_no, subtotal, discount, total, now.isoformat(timespec="seconds"), pickup)
        )
        token = cursor.lastrowid
        for item in cart:
            db.execute(
                """INSERT INTO order_items (token, food_name, price, quantity)
                   VALUES (?, ?, ?, ?)""",
                (token, item["name"], item["price"], item["quantity"])
            )

    return redirect(url_for("receipt", token=token))


@app.route("/receipt/<int:token>")
def receipt(token):
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE token = ?", (token,)).fetchone()
        if not order:
            flash("Order not found.", "error")
            return redirect(url_for("index"))
        order = dict(order)
        order["items"] = get_order_items(db, token)
        order["position"] = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status != 'Cancelled' AND token <= ?",
            (token,)
        ).fetchone()[0] if order["status"] != "Cancelled" else None
    return render_template("receipt.html", order=order)


@app.route("/check-order", methods=["GET", "POST"])
def check_order():
    order = None
    if request.method == "POST":
        raw_token = request.form.get("token", "").strip()
        if not raw_token.isdigit():
            flash("Enter a valid numeric token number.", "error")
        else:
            token = int(raw_token)
            with get_db() as db:
                row = db.execute("SELECT * FROM orders WHERE token = ?", (token,)).fetchone()
                if row:
                    order = dict(row)
                    order["items"] = get_order_items(db, token)
                    if order["status"] != "Cancelled":
                        order["position"] = db.execute(
                            "SELECT COUNT(*) FROM orders WHERE status != 'Cancelled' AND token <= ?",
                            (token,)
                        ).fetchone()[0]
                        order["people_ahead"] = max(0, order["position"] - 1)
                    else:
                        order["position"] = None
                        order["people_ahead"] = None
                else:
                    flash("No order was found with that token number.", "error")
    return render_template("check_order.html", order=order)


@app.route("/cancel-order", methods=["GET", "POST"])
def cancel_order():
    if request.method == "POST":
        raw_token = request.form.get("token", "").strip()
        if not raw_token.isdigit():
            flash("Enter a valid numeric token number.", "error")
        else:
            token = int(raw_token)
            with get_db() as db:
                row = db.execute("SELECT status FROM orders WHERE token = ?", (token,)).fetchone()
                if not row:
                    flash("No order was found with that token number.", "error")
                elif row["status"] == "Cancelled":
                    flash("This order has already been cancelled.", "error")
                else:
                    db.execute("UPDATE orders SET status = 'Cancelled' WHERE token = ?", (token,))
                    flash(f"Order #{token} cancelled successfully.", "success")
                    return redirect(url_for("cancel_order"))
    return render_template("cancel_order.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
