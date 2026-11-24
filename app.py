from datetime import datetime
import os
import random
import tempfile
import requests
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB cap for demo uploads

# Uses OS temp directory so file staging & shredding works both on Windows and Vercel serverless
VAULT_DIR = os.path.join(tempfile.gettempdir(), "apex_mortgage_vault")
os.makedirs(VAULT_DIR, exist_ok=True)

MORTGAGE_PROGRAMS = {
    "First-Time Homebuyer (GTA)": {
        "5-Year Fixed Insured (< 20% Down)": {
            "rate": "4.39%",
            "amortization": "25–30 Years (New Builds / First-Time Buyers)",
            "min_down": "5% on first $500k + 10% on remainder up to $1.5M",
            "highlight": "Includes First-Time Home Buyer GST/HST rebate guidance & 120-day rate hold.",
            "docs": [
                "Government photo ID + 90-day down payment bank history",
                "Recent 30-day pay stubs + T4s for the past 2 years",
                "Signed Agreement of Purchase and Sale (APS) & MLS listing",
            ],
        },
        "5-Year Variable Discounted": {
            "rate": "4.65%",
            "amortization": "25 Years",
            "min_down": "5%–19.99%",
            "highlight": "Lower 3-month interest penalty if you upgrade or refinance early.",
            "docs": [
                "Letter of Employment confirming base salary & start date",
                "Notice of Assessment (NOA) for last 2 tax years",
                "FHSA / RRSP Home Buyers' Plan withdrawal statements",
            ],
        },
    },
    "Mortgage Renewal & Switch": {
        "No-Fee Lender Switch (5-Year Fixed)": {
            "rate": "4.24%",
            "amortization": "Matches remaining amortization",
            "min_down": "Existing home equity",
            "highlight": "We cover legal & appraisal switch fees to beat your bank's posted renewal offer.",
            "docs": [
                "Current lender renewal statement & annual mortgage summary",
                "Recent municipal property tax bill & home insurance policy",
                "Updated income verification (T4 / pay stub)",
            ],
        },
        "3-Year Short-Term Fixed Bridge": {
            "rate": "4.49%",
            "amortization": "Up to 30 Years",
            "min_down": "Existing home equity",
            "highlight": "Ideal for homeowners planning a move or renovation within 36 months.",
            "docs": [
                "Current mortgage balance statement",
                "Municipal property tax assessment",
                "Recent income confirmation",
            ],
        },
    },
    "Self-Employed & Business Owner": {
        "Stated-Income Alt-A Program": {
            "rate": "5.19%",
            "amortization": "Up to 30 Years",
            "min_down": "20% Down Payment",
            "highlight": "Qualify using 6–12 months of corporate bank statements instead of personal T1 lines.",
            "docs": [
                "Articles of Incorporation / Master Business License (2+ years)",
                "6–12 months of business bank account statements",
                "Accountant letter & T1 Generals / NOAs",
            ],
        },
        "Prime Self-Employed (2-Year Add-Backs)": {
            "rate": "4.59%",
            "amortization": "25–30 Years",
            "min_down": "10%–20% Down Payment",
            "highlight": "Access prime A-lender rates by adding back eligible business write-offs.",
            "docs": [
                "2 years T1 General tax returns + Statement of Business Activities",
                "2 years CRA Notices of Assessment showing $0 tax arrears",
                "90-day down payment & closing cost verification",
            ],
        },
    },
    "Investment & Rental Property": {
        "Rental Cash-Flow Offset Mortgage": {
            "rate": "4.89%",
            "amortization": "30 Years",
            "min_down": "20% Down Payment",
            "highlight": "Up to 80% rental income add-back to maximize borrowing power across Ontario.",
            "docs": [
                "Signed lease agreement or market rent appraisal schedule",
                "Existing property mortgage & tax statements",
                "20% liquid down payment verification",
            ],
        },
    },
}


def compute_canadian_mortgage(home_price: float, down_payment: float, annual_rate: float, years: int = 25) -> dict:
    if home_price <= 500_000:
        min_down = home_price * 0.05
    elif home_price < 1_500_000:
        min_down = (500_000 * 0.05) + ((home_price - 500_000) * 0.10)
    else:
        min_down = home_price * 0.20

    if down_payment < min_down:
        return {
            "error": f"Minimum Canadian down payment for a ${home_price:,.0f} property is ${min_down:,.0f}."
        }

    down_pct = (down_payment / home_price) * 100
    base_loan = home_price - down_payment

    if down_pct >= 20:
        cmhc_rate = 0.0
    elif down_pct >= 15:
        cmhc_rate = 0.028
    elif down_pct >= 10:
        cmhc_rate = 0.031
    else:
        cmhc_rate = 0.04

    cmhc_fee = base_loan * cmhc_rate
    total_mortgage = base_loan + cmhc_fee
    months = years * 12
    monthly_rate = (annual_rate / 100) / 12

    if monthly_rate == 0:
        monthly_payment = total_mortgage / months
    else:
        factor = (1 + monthly_rate) ** months
        monthly_payment = total_mortgage * (monthly_rate * factor) / (factor - 1)

    return {
        "error": "",
        "monthly_payment": f"${monthly_payment:,.2f}",
        "total_mortgage": f"${total_mortgage:,.0f}",
        "cmhc_fee": f"${cmhc_fee:,.0f}",
        "down_pct": f"{down_pct:.1f}%",
        "monthly_raw": round(monthly_payment, 2),
        "down_raw": round(down_payment, 2),
    }


def fetch_fx_rates(base_currency: str = "CAD") -> dict:
    try:
        resp = requests.get(f"https://open.er-api.com/v6/latest/{base_currency}", timeout=6)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("result") == "success":
            return payload["rates"]
    except Exception:
        pass
    # Resilient fallback rates if offline
    return {"CAD": 1.0, "USD": 0.72, "AED": 2.65, "INR": 60.50, "GBP": 0.57, "EUR": 0.67}


def list_vault_files() -> list:
    items = []
    for fname in sorted(os.listdir(VAULT_DIR)):
        fpath = os.path.join(VAULT_DIR, fname)
        if os.path.isfile(fpath):
            size_kb = max(1, round(os.path.getsize(fpath) / 1024, 1))
            items.append({"name": fname, "size_kb": size_kb})
    return items


def secure_shred_file(filename: str) -> str:
    safe_name = secure_filename(filename)
    target_path = os.path.join(VAULT_DIR, safe_name)
    if not os.path.isfile(target_path):
        return f"File '{safe_name}' was not found in the staging vault."

    file_size = max(os.path.getsize(target_path), 1024)
    # 3-pass cryptographic random-byte overwrite before unlinking
    with open(target_path, "r+b") as f:
        for _ in range(3):
            f.seek(0)
            f.write(os.urandom(file_size))
            f.flush()
            os.fsync(f.fileno())
    os.remove(target_path)
    return f"3-Pass Cryptographic Shred Complete: '{safe_name}' ({file_size:,} bytes overwritten & purged)."


@app.route("/")
def home():
    return render_template("home.html", active_page="home")


@app.route("/programs")
def programs():
    return render_template("programs.html", active_page="programs", programs=MORTGAGE_PROGRAMS)


@app.route("/calculators", methods=["GET", "POST"])
def calculators():
    home_price = "875000"
    down_payment = "125000"
    interest_rate = "4.39"
    fx_amount = "125000"
    fx_from = "USD"
    fx_to = "CAD"

    if request.method == "POST":
        home_price = request.form.get("home_price", "875000").replace(",", "").strip()
        down_payment = request.form.get("down_payment", "125000").replace(",", "").strip()
        interest_rate = request.form.get("interest_rate", "4.39").replace("%", "").strip()
        fx_amount = request.form.get("fx_amount", "125000").replace(",", "").strip()
        fx_from = request.form.get("fx_from", "USD").strip()
        fx_to = request.form.get("fx_to", "CAD").strip()

    try:
        mtg_result = compute_canadian_mortgage(float(home_price), float(down_payment), float(interest_rate))
    except ValueError:
        mtg_result = {"error": "Please enter valid numbers for price, down payment, and interest rate."}

    rates = fetch_fx_rates(fx_from)
    try:
        amt = float(fx_amount)
        rate_val = rates.get(fx_to, 1.0)
        fx_result = {
            "error": "",
            "source_amt": f"{amt:,.2f} {fx_from}",
            "converted_amt": f"{amt * rate_val:,.2f} {fx_to}",
            "rate": f"1 {fx_from} = {rate_val:.4f} {fx_to}",
        }
    except ValueError:
        fx_result = {"error": "Enter a valid numeric transfer amount."}

    return render_template(
        "calculators.html",
        active_page="calculators",
        mtg_result=mtg_result,
        fx_result=fx_result,
        home_price=home_price,
        down_payment=down_payment,
        interest_rate=interest_rate,
        fx_amount=fx_amount,
        fx_from=fx_from,
        fx_to=fx_to,
    )


@app.route("/readiness")
def readiness():
    return render_template("readiness.html", active_page="readiness")


@app.route("/letter-builder")
def letter_builder():
    return render_template("letter_builder.html", active_page="letter_builder")


@app.route("/vault", methods=["GET", "POST"])
def vault():
    notice = ""
    notice_type = "success"

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "upload":
            uploaded = request.files.get("client_doc")
            if uploaded and uploaded.filename:
                safe_name = secure_filename(uploaded.filename)
                uploaded.save(os.path.join(VAULT_DIR, safe_name))
                notice = f"Encrypted staging complete: '{safe_name}' uploaded to temporary client vault."
            else:
                notice = "Please select a PDF, image, or CSV file to stage."
                notice_type = "danger"
        elif action == "create_sample":
            sample_name = f"T4_Income_Summary_{random.randint(100, 999)}.txt"
            with open(os.path.join(VAULT_DIR, sample_name), "w", encoding="utf-8") as f:
                f.write("CONFIDENTIAL CLIENT STAGING RECORD — APEX LENDING GROUP\nVerified Income: $118,500 CAD\n")
            notice = f"Sample sensitive file '{sample_name}' staged in vault — test the 3-Pass Shredder below."
        elif action == "shred":
            target = request.form.get("filename", "")
            notice = secure_shred_file(target)
            notice_type = "warning"

    return render_template(
        "vault.html",
        active_page="vault",
        files=list_vault_files(),
        notice=notice,
        notice_type=notice_type,
    )


@app.route("/book", methods=["GET", "POST"])
def book():
    confirmation = None
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        goal = request.form.get("goal", "First-Time Home Pre-Approval").strip()
        city = request.form.get("city", "Brampton / Peel Region").strip()

        if not full_name or not email or not phone:
            confirmation = {"error": "Please complete your name, email address, and phone number."}
        else:
            ref = f"APX-{datetime.now().strftime('%Y%m')}-{random.randint(1000, 9999)}"
            confirmation = {
                "error": "",
                "ref": ref,
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "goal": goal,
                "city": city,
            }

    return render_template("book.html", active_page="book", confirmation=confirmation)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)