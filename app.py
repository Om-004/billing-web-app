import os
import sqlite3
import qrcode
import smtplib

from flask import Flask, render_template, request, send_file, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---------------- BASIC SETUP ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

BILL_DIR = os.path.join(BASE_DIR, "bills")
os.makedirs(BILL_DIR, exist_ok=True)

w, h = A4

app = Flask(__name__)
app.secret_key = "anadi_secret_key"
#---------------------add database connection function-----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_no TEXT,
        username TEXT,
        customer TEXT,
        customer_email TEXT,
        customer_phone TEXT,
        total REAL,
        payment_mode TEXT,
        payment_status TEXT,
        status TEXT,
        date TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        item_name TEXT,
        qty INTEGER,
        rate REAL,
        amount REAL,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        )
    """)

    conn.commit()
    conn.close()
# ---------------- CREATE DEFAULT ADMIN ----------------
init_db()
# ---------------- TEST ----------------
@app.route("/test")
def test():
    return "Flask is working"

# ---------------- EMAIL ----------------
def send_invoice_email(to_email, pdf_path, customer):
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        return

    msg = EmailMessage()
    msg["Subject"] = "Your Invoice from Anadi Me Edsolutions"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg.set_content(
        f"Dear {customer},\n\nPlease find attached your invoice.\n\nRegards,\nAnadi Me Edsolutions"
    )

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path)
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT password, role FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        conn.close()

        if row and check_password_hash(row[0], password):
            session.clear()              # 🔥 FIX (Problem 3)
            session["user"] = username
            session["role"] = row[1]
            return redirect(url_for("index"))
        
        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, password, "user")
            )
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Username already exists")

    return render_template("register.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- INDEX / INVOICE ----------------
@app.route("/", methods=["GET", "POST"])
def index():

    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("index.html")

    customer = request.form["customer"]
    customer_email = request.form["customer_email"]
    customer_phone = request.form["customer_phone"] 
    payment_mode = request.form["payment_mode"]
    items = request.form.getlist("item[]")
    qtys = request.form.getlist("qty[]")
    rates = request.form.getlist("rate[]")
    if session.get("role") == "admin":
        payment_status = request.form.get("payment_status", "Pending")
    else:
        payment_status = "Pending"


    total = 0
    item_data = []

    for i in range(len(items)):
        amount = float(qtys[i]) * float(rates[i])
        total += amount
        item_data.append((items[i], qtys[i], rates[i], amount))

    # ---------- SAVE TO DB ----------
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO invoices (username, customer, customer_email, customer_phone, payment_mode, payment_status, total, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["user"],
        customer,
        customer_email,
        customer_phone,
        payment_mode,
        payment_status,  
        total,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    
    invoice_id = cur.lastrowid
    invoice_no = f"ANADI-INV-{invoice_id:06d}"
    cur.execute("UPDATE invoices SET invoice_no=? WHERE id=?",
    (invoice_no, invoice_id)
    )
    # -------- FETCH PAYMENT DETAILS (HERE!) --------
    cur.execute("""
        SELECT payment_mode, payment_status
        FROM invoices WHERE id=?
    """, (invoice_id,))
    pay = cur.fetchone()

    payment_mode = pay[0] if pay else "N/A"
    payment_status = pay[1] if pay else "Pending"

    for i in range(len(items)):
        amount = float(qtys[i]) * float(rates[i])

        cur.execute("""
            INSERT INTO invoice_items (
                invoice_id, item_name, qty, rate, amount
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            invoice_id,
            items[i],
            qtys[i],
            rates[i],
            amount
            )
    )
    conn.commit()
    conn.close()
    #------------- PDF GENERATION --------------
    pdf_path = os.path.join(BILL_DIR, f"{invoice_no}.pdf")
    qr_path = os.path.join(BILL_DIR, f"{invoice_no}_qr.png")

    # ---------- QR ----------
    upi = f"upi://pay?pa=bindu62013928@ybl&pn=Anadi&am={total}&cu=INR"
    qrcode.make(upi).save(qr_path)

    # ---------- PDF ----------
    pdf = canvas.Canvas(pdf_path, pagesize=A4)
    w, h = A4

    # ---------- LOGO ----------
    logo = os.path.join(app.root_path, "static", "logo.png")
    if os.path.exists(logo):
        pdf.drawImage(logo, 40, h - 80, 80, 50)

    # ---------- HEADER ----------
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(130, h - 50, "Anadi Me Edsolutions (OPC) Private Limited")

    pdf.setFont("Helvetica", 9)
    pdf.drawString(130, h - 65, "H No. 7, Guru Sahay Lal Nagar, Ashiana, Patna – 800025")
    pdf.drawString(130, h - 78, "Phone: +91 9861006924 | Email: anadimeedsolutions@gmail.com")

    pdf.line(40, h - 90, w - 40, h - 90)

    # ---------- INVOICE DETAILS ----------
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, h - 120, f"Invoice No: {invoice_no}")
    pdf.drawString(40, h - 135, f"Invoice To: {customer}")
    pdf.drawRightString(w - 40, h - 120, f"Date: {date.today()}")

    # ---------- ITEM TABLE ----------
    y = h - 170
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Item")
    pdf.drawString(260, y, "Qty")
    pdf.drawString(320, y, "Rate")
    pdf.drawString(400, y, "Amount")

    pdf.line(40, y - 5, w - 40, y - 5)

    y -= 25
    pdf.setFont("Helvetica", 11)

    for it in item_data:
        pdf.drawString(40, y, it[0])
        pdf.drawString(260, y, str(it[1]))
        pdf.drawString(320, y, str(it[2]))
        pdf.drawString(400, y, f"{it[3]:.2f}")
        y -= 20

    # ---------- TOTAL ----------
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(360, y - 10, "Total:")
    pdf.drawString(380, y - 10, f"₹ {total:.2f}")

    # ==================================================
    # FIXED PAYMENT SECTION (CLEAN PREVIEW)
    # ==================================================

    payment_base_y = 140  # fixed bottom section

    pdf.line(40, payment_base_y + 120, w - 40, payment_base_y + 120)

    # GST NOTE (ABOVE QR)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, payment_base_y + 105, "(Not registered under GST)")

    # QR CODE
    pdf.drawImage(qr_path, 40, payment_base_y, width=120, height=120)

    # SCAN TO PAY
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, payment_base_y - 15, "Scan to Pay")

    # PAYMENT STATUS (CENTER)
    pdf.setFont("Helvetica-Bold", 11)
    payment_text = (
        "Payment is done successfully. Thank you."
        if payment_status == "Done"
        else "You didn't give the payment."
    )
    pdf.drawCentredString(w / 2, payment_base_y - 40, payment_text)

    # AUTHORIZED SIGNATORY (RIGHT)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(w - 40, payment_base_y - 60, "Authorized Signatory")

    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(w - 40, payment_base_y - 75, "ANADI ME EDSOLUTIONS")

    # ---------- SAVE ----------
    pdf.save()

    session["last_invoice"] = {
    "invoice_no": invoice_no,
    "customer": customer,
    "items": item_data,
    "total": total
}   
    session["email_data"] = {
    "customer_email": customer_email,
    "customer": customer
}
    session["whatsapp_data"] = {
    "phone": customer_phone
}

    return redirect(url_for("preview_invoice", invoice_id=invoice_id))
#----------preview invoice ----------
@app.route("/preview/<int:invoice_id>")
def preview_invoice(invoice_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Invoice header
    cur.execute("""
        SELECT invoice_no, customer, customer_email, customer_phone, total
        FROM invoices WHERE id=?
    """, (invoice_id,))
    invoice_row = cur.fetchone()

    if not invoice_row:
        conn.close()
        return redirect(url_for("index"))

    # Invoice items
    cur.execute("""
        SELECT item_name, qty, rate, amount
        FROM invoice_items WHERE invoice_id=?
    """, (invoice_id,))
    items = cur.fetchall()

    conn.close()

    invoice = {
        "invoice_no": invoice_row[0],
        "customer": invoice_row[1],
        "total": invoice_row[4],
        "items": items
    }

    return render_template(
        "preview.html",
        invoice=invoice,
        invoice_id=invoice_id,
        email=invoice_row[2],
        phone=invoice_row[3]
    )


# ---------------- ADMIN ----------------
@app.route("/admin")
def admin_dashboard():

    if "user" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # -------- USERS --------
    cur.execute("SELECT username, role FROM users")
    users = cur.fetchall()

    # -------- INVOICES --------
    cur.execute("""
        SELECT id, invoice_no, username, customer,
               customer_email, customer_phone,
               total, date, status
        FROM invoices
        ORDER BY id DESC
    """)
    invoices = cur.fetchall()

    # -------- ANALYTICS --------
    cur.execute("SELECT COUNT(*) FROM invoices WHERE status='Pending'")
    pending_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM invoices WHERE status='Sent'")
    sent_count = cur.fetchone()[0]

    cur.execute("SELECT SUM(total) FROM invoices")
    revenue = cur.fetchone()[0] or 0

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        invoices=invoices,
        user_count=len(users),
        invoice_count=len(invoices),
        pending_count=pending_count,
        sent_count=sent_count,
        revenue=revenue
    )



# ---------------- HISTORY ----------------
@app.route("/history")
def history():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if session.get("role") == "admin":
        cur.execute("""
            SELECT id, invoice_no, username, customer, total, date
            FROM invoices
            ORDER BY id DESC
        """)
    else:
        cur.execute("""
            SELECT id, invoice_no, username, customer, total, date
            FROM invoices
            WHERE username=?
            ORDER BY id DESC
        """, (session["user"],))

    invoices = cur.fetchall()
    conn.close()

    return render_template("history.html", invoices=invoices)
# ---------------- DOWNLOAD ----------------
@app.route("/download/<int:invoice_id>")
def download_invoice(invoice_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT invoice_no FROM invoices WHERE id=?", (invoice_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return "Invoice not found", 404

    invoice_no = row[0]
    pdf_path = os.path.join(BILL_DIR, f"{invoice_no}.pdf")

    # 📧 SEND EMAIL ON CONFIRMATION
    email_data = session.get("email_data")
    if email_data:
        try:
            send_invoice_email(
                email_data["customer_email"],
                pdf_path,
                email_data["customer"]
            )
            session.pop("email_data")  # prevent re-sending
        except Exception as e:
            print("Email failed:", e)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET status='Sent' WHERE id=?",
        (invoice_id,)
    )
    conn.commit()
    conn.close()
    return send_file(pdf_path, as_attachment=True)
#----------------Resend whatsapp from admin dashboard----------------
@app.route("/resend_whatsapp/<int:invoice_id>")
def resend_whatsapp(invoice_id):

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT customer, customer_phone, invoice_no
        FROM invoices WHERE id=?
    """, (invoice_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return redirect(url_for("admin_dashboard"))

    customer, phone, invoice_no = row

    whatsapp_url = (
        f"https://wa.me/{phone}"
        f"?text=Hello%20{customer}%2C%0A"
        f"Your%20invoice%20({invoice_no})%20is%20ready.%0A"
        f"Thank%20you."
    )

    return redirect(whatsapp_url)
#----------------Resend email from admin dashboard----------------
@app.route("/resend_email/<int:invoice_id>")
def resend_email(invoice_id):

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT customer, customer_email, invoice_no
        FROM invoices WHERE id=?
    """, (invoice_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return redirect(url_for("admin_dashboard"))

    customer, email, invoice_no = row
    pdf_path = os.path.join(BILL_DIR, f"{invoice_no}.pdf")

    try:
        send_invoice_email(email, pdf_path, customer)
    except:
        pass

    return redirect(url_for("admin_dashboard"))

# ---------------- DELETE ----------------
@app.route("/delete/<int:invoice_id>")
def delete_invoice(invoice_id):

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT invoice_no FROM invoices WHERE id=?", (invoice_id,))
    row = cur.fetchone()

    if row:
        pdf = os.path.join(BILL_DIR, f"{row[0]}.pdf")
        if os.path.exists(pdf):
            os.remove(pdf)
        cur.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))

    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))
#---------------- Payment Done ----------------
@app.route("/payment_done/<int:invoice_id>")
def payment_done(invoice_id):

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET payment_status='Done' WHERE id=?",
        (invoice_id,)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/payment_not_done/<int:invoice_id>")
def payment_not_done(invoice_id):

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE invoices SET payment_status='Not Done' WHERE id=?",
        (invoice_id,)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))



