from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
from dotenv import load_dotenv
from passlib.context import CryptContext
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

app = FastAPI()

# Allow your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database connection
def get_db():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )
    return conn


@app.get("/")
def home():
    return {"status": "running", "owner": "Rishabh"}


# ---------------------------
# USER REGISTRATION
# ---------------------------
@app.post("/register")
def register(username: str, password: str):
    conn = get_db()
    cur = conn.cursor()

    hashed = pwd_context.hash(password)

    cur.execute("SELECT * FROM users WHERE username=%s", (username,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="User already exists")

    cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, hashed))
    conn.commit()

    return {"message": "Account created"}


# ---------------------------
# LOGIN
# ---------------------------
@app.post("/login")
def login(username: str, password: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid username")

    if not pwd_context.verify(password, user['password']):
        raise HTTPException(status_code=400, detail="Invalid password")

    return {"message": "Login success", "user_id": user["id"]}


# ---------------------------
# PAYMENT CREATE
# ---------------------------
@app.post("/create-payment")
def create_payment(user_id: int):
    key = os.getenv("UPI_API_KEY")
    secret = os.getenv("UPI_SECRET_KEY")

    amount = 29  # fixed monthly subscription

    payload = {
        "key": key,
        "client_txn_id": f"txn_{user_id}",
        "amount": amount,
        "p_info": "OSINT Monthly Subscription",
        "customer_name": f"user_{user_id}",
        "customer_email": "noemail@example.com",
        "customer_mobile": "9999999999",
        "redirect_url": "https://osint-zevk.onrender.com/payment-success"
    }

    r = requests.post("https://merchant.upigateway.com/api/create_order", data=payload)
    return r.json()


# ---------------------------
# PAYMENT WEBHOOK
# ---------------------------
@app.post("/payment-webhook")
def webhook(data: dict):
    try:
        user_id = int(data["client_txn_id"].replace("txn_", ""))
    except:
        raise HTTPException(status_code=400, detail="Invalid transaction")

    if data.get("status") != "success":
        return {"msg": "Payment not successful"}

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users SET paid_until = NOW() + INTERVAL '30 days' WHERE id=%s
    """, (user_id,))
    conn.commit()

    return {"msg": "Subscription activated"}


# ---------------------------
# PROTECTED LOOKUP
# ---------------------------
@app.get("/lookup")
def lookup(user_id: int, type: str, query: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT paid_until FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user["paid_until"] is None:
        raise HTTPException(status_code=403, detail="Subscription required")

    if user["paid_until"] < datetime.datetime.now():
        raise HTTPException(status_code=403, detail="Subscription expired")

    api_url = f"https://osint-zevk.onrender.com/{type}?{query}"

    r = requests.get(api_url)
    return r.json()