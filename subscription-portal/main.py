import os
import secrets
import string
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException, Depends, Form, Cookie, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("subscription-portal")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://webui_user:password@postgres:5432/openwebui")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "gcat_admin_2026!")
COOKIE_NAME = "sub_admin_token"
ADMIN_SESSION_TOKEN = secrets.token_hex(32)

# Protected admin emails that should NEVER be reverted to pending
PROTECTED_ADMIN_EMAILS = {
    "abulfadl.ahmadi@gmail.com",
    "reza@gmail.com",
    "pouriadrd@gmail.com"
}

# Plan definitions
PLANS = {
    "1m": {"name": "اشتراک ۱ ماهه (۳۰ روز)", "days": 30, "price": 399000, "prefix": "1M"},
    "3m": {"name": "اشتراک ۳ ماهه (۹۰ روز)", "days": 90, "price": 999000, "prefix": "3M"},
    "1y": {"name": "اشتراک ۱ ساله (۳۶۵ روز)", "days": 365, "price": 3999000, "prefix": "1Y"},
}

db_pool: Optional[pool.SimpleConnectionPool] = None

def get_db_conn():
    if db_pool is None:
        raise RuntimeError("Database connection pool is not initialized.")
    return db_pool.getconn()

def put_db_conn(conn):
    if db_pool is not None:
        db_pool.putconn(conn)

def init_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS redeem_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(64) UNIQUE NOT NULL,
            plan_name VARCHAR(64) NOT NULL,
            duration_days INT NOT NULL,
            price_tomans INT DEFAULT 0,
            is_used BOOLEAN DEFAULT FALSE,
            used_by_email VARCHAR(255),
            used_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR REFERENCES "user"(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            redeem_code VARCHAR(64),
            plan_name VARCHAR(64) NOT NULL,
            duration_days INT NOT NULL,
            starts_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            status VARCHAR(32) DEFAULT 'active',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_subscriptions_email ON subscriptions(email);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_at ON subscriptions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_redeem_codes_code ON redeem_codes(code);
        """)
        conn.commit()
    logger.info("Database schema verified.")

def generate_secure_code(prefix: str = "SUB") -> str:
    # Character set without confusing characters (0, O, I, 1, L)
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    rand_part = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"GCAT-{prefix}-{rand_part[:4]}-{rand_part[4:]}"

async def check_expirations():
    """Background worker to check and expire finished subscriptions"""
    while True:
        try:
            conn = get_db_conn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    now = datetime.now(timezone.utc)
                    # Find all active subscriptions that passed expires_at
                    cur.execute("""
                        SELECT id, user_id, email, expires_at 
                        FROM subscriptions 
                        WHERE status = 'active' AND expires_at <= %s
                    """, (now,))
                    expired_subs = cur.fetchall()

                    for sub in expired_subs:
                        email = sub["email"].lower().strip()
                        sub_id = sub["id"]

                        # Check if user has any OTHER active subscription that is still valid
                        cur.execute("""
                            SELECT id FROM subscriptions 
                            WHERE lower(email) = %s AND status = 'active' AND expires_at > %s AND id != %s
                        """, (email, now, sub_id))
                        has_other_active = cur.fetchone()

                        # Mark this subscription as expired
                        cur.execute("UPDATE subscriptions SET status = 'expired', updated_at = %s WHERE id = %s", (now, sub_id))

                        if not has_other_active and email not in PROTECTED_ADMIN_EMAILS:
                            # Revert Open WebUI user to pending
                            cur.execute("""
                                UPDATE "user" 
                                SET role = 'pending' 
                                WHERE lower(email) = %s AND role = 'user'
                            """, (email,))
                            logger.info(f"Subscription expired for {email}. Role reverted to 'pending'.")

                    conn.commit()
            finally:
                put_db_conn(conn)
        except Exception as e:
            logger.error(f"Error in expiry worker: {e}")

        await asyncio.sleep(60)  # Check every 60 seconds

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    logger.info("Connecting to PostgreSQL pool...")
    db_pool = pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
    conn = db_pool.getconn()
    try:
        init_db(conn)
    finally:
        put_db_conn(conn)

    # Start background expiry task
    expiry_task = asyncio.create_task(check_expirations())
    yield
    expiry_task.cancel()
    if db_pool:
        db_pool.closeall()

app = FastAPI(title="Academic Chat Assistant - Subscription Portal", lifespan=lifespan)

templates = Jinja2Templates(directory="/app/templates")

def verify_admin(sub_admin_token: Optional[str] = Cookie(None)):
    if not sub_admin_token or sub_admin_token != ADMIN_SESSION_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return True

# ------------------------------------------------------------------------------
# Frontend Views
# ------------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, sub_admin_token: Optional[str] = Cookie(None)):
    is_authenticated = sub_admin_token == ADMIN_SESSION_TOKEN
    return templates.TemplateResponse(
        request=request, 
        name="admin.html", 
        context={
            "authenticated": is_authenticated,
            "plans": PLANS
        }
    )

# ------------------------------------------------------------------------------
# Public API: Redeem & Status
# ------------------------------------------------------------------------------

class RedeemRequest(BaseModel):
    email: str
    code: str

@app.post("/api/redeem")
async def redeem_code(req: RedeemRequest):
    email = req.email.strip().lower()
    code = req.code.strip().upper()

    if not email or not code:
        return JSONResponse(status_code=400, content={"success": False, "message": "ایمیل و کد فعالسازی الزامی است."})

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Check if user exists in Open WebUI
            cur.execute('SELECT id, name, role FROM "user" WHERE lower(email) = %s', (email,))
            user = cur.fetchone()
            if not user:
                return JSONResponse(status_code=404, content={
                    "success": False, 
                    "message": "کاربری با این ایمیل یافت نشد. لطفاً ابتدا در سامانه (chat.gcat.ir) ثبتنام کنید، سپس کد را وارد نمایید."
                })

            user_id = user["id"]

            # 2. Check redeem code
            cur.execute("""
                SELECT id, code, plan_name, duration_days, price_tomans, is_used 
                FROM redeem_codes 
                WHERE code = %s
            """, (code,))
            code_row = cur.fetchone()

            if not code_row:
                return JSONResponse(status_code=400, content={"success": False, "message": "کد وارد شده معتبر نیست یا اشتباه تایپ شده است."})

            if code_row["is_used"]:
                return JSONResponse(status_code=400, content={"success": False, "message": "این کد قبلاً استفاده و فعال شده است."})

            now = datetime.now(timezone.utc)
            duration_days = code_row["duration_days"]

            # 3. Check existing active subscription to stack time
            cur.execute("""
                SELECT expires_at FROM subscriptions 
                WHERE lower(email) = %s AND status = 'active' AND expires_at > %s 
                ORDER BY expires_at DESC LIMIT 1
            """, (email, now))
            active_sub = cur.fetchone()

            if active_sub and active_sub["expires_at"]:
                starts_at = active_sub["expires_at"]
                expires_at = starts_at + timedelta(days=duration_days)
            else:
                starts_at = now
                expires_at = now + timedelta(days=duration_days)

            # 4. Mark code as used
            cur.execute("""
                UPDATE redeem_codes 
                SET is_used = TRUE, used_by_email = %s, used_at = %s 
                WHERE id = %s
            """, (email, now, code_row["id"]))

            # 5. Insert subscription record
            cur.execute("""
                INSERT INTO subscriptions 
                (user_id, email, redeem_code, plan_name, duration_days, starts_at, expires_at, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
            """, (user_id, email, code, code_row["plan_name"], duration_days, starts_at, expires_at))

            # 6. Activate user in Open WebUI if not already admin
            if user["role"] != "admin":
                cur.execute('UPDATE "user" SET role = \'user\' WHERE id = %s', (user_id,))

            conn.commit()

            remaining_days = max(0, (expires_at - now).days)

            return {
                "success": True,
                "message": f"اشتراک «{code_row['plan_name']}» با موفقیت فعال شد!",
                "plan_name": code_row["plan_name"],
                "expires_at": expires_at.strftime("%Y-%m-%d %H:%M UTC"),
                "remaining_days": remaining_days
            }
    except Exception as e:
        conn.rollback()
        logger.error(f"Error redeeming code: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": "خطای سیستمی رخ داد. لطفاً با پشتیبانی تلگرام تماس بگیرید."})
    finally:
        put_db_conn(conn)

@app.get("/api/status")
async def check_status(email: str):
    clean_email = email.strip().lower()
    if not clean_email:
        return JSONResponse(status_code=400, content={"success": False, "message": "ایمیل الزامی است."})

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT id, name, role FROM "user" WHERE lower(email) = %s', (clean_email,))
            user = cur.fetchone()
            if not user:
                return JSONResponse(status_code=404, content={"success": False, "message": "کاربری با این ایمیل یافت نشد."})

            now = datetime.now(timezone.utc)
            cur.execute("""
                SELECT plan_name, duration_days, starts_at, expires_at, status 
                FROM subscriptions 
                WHERE lower(email) = %s AND status = 'active' AND expires_at > %s 
                ORDER BY expires_at DESC LIMIT 1
            """, (clean_email, now))
            sub = cur.fetchone()

            if user["role"] == "admin":
                return {
                    "success": True,
                    "registered": True,
                    "name": user["name"],
                    "is_admin": True,
                    "status_label": "مدیر سیستم (دسترسی نامحدود دائمی)",
                    "active": True
                }

            if sub:
                remaining_days = max(0, (sub["expires_at"] - now).days)
                return {
                    "success": True,
                    "registered": True,
                    "name": user["name"],
                    "active": True,
                    "plan_name": sub["plan_name"],
                    "expires_at": sub["expires_at"].strftime("%Y-%m-%d %H:%M UTC"),
                    "remaining_days": remaining_days
                }
            else:
                return {
                    "success": True,
                    "registered": True,
                    "name": user["name"],
                    "active": False,
                    "status_label": "اشتراک فعال یافت نشد یا منقضی شده است."
                }
    finally:
        put_db_conn(conn)

# ------------------------------------------------------------------------------
# Admin API
# ------------------------------------------------------------------------------

class AdminLoginRequest(BaseModel):
    password: str

@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    if req.password == ADMIN_PASSWORD:
        response = JSONResponse(content={"success": True})
        response.set_cookie(
            key=COOKIE_NAME,
            value=ADMIN_SESSION_TOKEN,
            httponly=True,
            samesite="lax",
            max_age=86400 * 30
        )
        return response
    return JSONResponse(status_code=401, content={"success": False, "message": "رمز عبور اشتباه است."})

@app.post("/api/admin/logout")
async def admin_logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie(COOKIE_NAME)
    return response

class GenerateCodeRequest(BaseModel):
    plan_key: str
    custom_days: Optional[int] = None
    custom_name: Optional[str] = None
    custom_price: Optional[int] = None
    notes: Optional[str] = None
    count: int = 1

@app.post("/api/admin/generate-code")
async def admin_generate_code(req: GenerateCodeRequest, _: bool = Depends(verify_admin)):
    if req.plan_key in PLANS:
        plan = PLANS[req.plan_key]
        plan_name = plan["name"]
        duration_days = plan["days"]
        price = plan["price"]
        prefix = plan["prefix"]
    elif req.plan_key == "custom":
        if not req.custom_days or req.custom_days <= 0:
            raise HTTPException(status_code=400, detail="مدت روزهای پلن سفارشی باید بزرگتر از صفر باشد.")
        duration_days = req.custom_days
        plan_name = req.custom_name or f"اشتراک سفارشی ({duration_days} روز)"
        price = req.custom_price or 0
        prefix = f"{duration_days}D"
    else:
        raise HTTPException(status_code=400, detail="پلن انتخابی معتبر نیست.")

    conn = get_db_conn()
    generated = []
    try:
        with conn.cursor() as cur:
            for _ in range(max(1, min(req.count, 50))):
                code = generate_secure_code(prefix)
                cur.execute("""
                    INSERT INTO redeem_codes 
                    (code, plan_name, duration_days, price_tomans, notes) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (code, plan_name, duration_days, price, req.notes or ""))
                generated.append(code)
            conn.commit()
        return {"success": True, "codes": generated, "plan_name": plan_name, "duration_days": duration_days}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error generating code: {e}")
        raise HTTPException(status_code=500, detail="خطا در ساخت کد اشتراک")
    finally:
        put_db_conn(conn)

@app.get("/api/admin/codes")
async def admin_list_codes(_: bool = Depends(verify_admin)):
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, code, plan_name, duration_days, price_tomans, is_used, 
                       used_by_email, used_at, created_at, notes 
                FROM redeem_codes 
                ORDER BY created_at DESC LIMIT 150
            """)
            rows = cur.fetchall()
            for r in rows:
                if r["created_at"]:
                    r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M")
                if r["used_at"]:
                    r["used_at"] = r["used_at"].strftime("%Y-%m-%d %H:%M")
            return {"success": True, "codes": rows}
    finally:
        put_db_conn(conn)

@app.get("/api/admin/subscribers")
async def admin_list_subscribers(_: bool = Depends(verify_admin)):
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            now = datetime.now(timezone.utc)
            cur.execute("""
                SELECT s.id, s.email, u.name, u.role, s.plan_name, s.redeem_code,
                       s.starts_at, s.expires_at, s.status
                FROM subscriptions s
                LEFT JOIN "user" u ON lower(s.email) = lower(u.email)
                ORDER BY s.expires_at DESC LIMIT 150
            """)
            rows = cur.fetchall()
            for r in rows:
                if r["starts_at"]:
                    r["starts_at"] = r["starts_at"].strftime("%Y-%m-%d %H:%M")
                if r["expires_at"]:
                    exp = r["expires_at"]
                    r["is_active"] = exp > now and r["status"] == "active"
                    r["remaining_days"] = max(0, (exp - now).days) if exp > now else 0
                    r["expires_at"] = exp.strftime("%Y-%m-%d %H:%M")
            return {"success": True, "subscribers": rows}
    finally:
        put_db_conn(conn)

class ExtendSubscriptionRequest(BaseModel):
    email: str
    days: int = 30

@app.post("/api/admin/extend")
async def admin_extend_user(req: ExtendSubscriptionRequest, _: bool = Depends(verify_admin)):
    email = req.email.strip().lower()
    days = max(1, req.days)
    now = datetime.now(timezone.utc)

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT id, role FROM "user" WHERE lower(email) = %s', (email,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="کاربر یافت نشد.")

            cur.execute("""
                SELECT id, expires_at FROM subscriptions 
                WHERE lower(email) = %s AND status = 'active' AND expires_at > %s 
                ORDER BY expires_at DESC LIMIT 1
            """, (email, now))
            sub = cur.fetchone()

            if sub and sub["expires_at"]:
                new_exp = sub["expires_at"] + timedelta(days=days)
                cur.execute("UPDATE subscriptions SET expires_at = %s, updated_at = %s WHERE id = %s", (new_exp, now, sub["id"]))
            else:
                new_exp = now + timedelta(days=days)
                cur.execute("""
                    INSERT INTO subscriptions 
                    (user_id, email, redeem_code, plan_name, duration_days, starts_at, expires_at, status) 
                    VALUES (%s, %s, 'ADMIN-EXTEND', 'تمدید مستقیم مدیریت', %s, %s, %s, 'active')
                """, (user["id"], email, days, now, new_exp))

            if user["role"] != "admin":
                cur.execute('UPDATE "user" SET role = \'user\' WHERE id = %s', (user["id"],))

            conn.commit()
            return {"success": True, "message": f"اشتراک {email} با موفقیت {days} روز تمدید شد.", "new_expires_at": new_exp.strftime("%Y-%m-%d")}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error extending sub: {e}")
        raise HTTPException(status_code=500, detail="خطا در تمدید اشتراک")
    finally:
        put_db_conn(conn)

class RevokeSubscriptionRequest(BaseModel):
    email: str

@app.post("/api/admin/revoke")
async def admin_revoke_user(req: RevokeSubscriptionRequest, _: bool = Depends(verify_admin)):
    email = req.email.strip().lower()
    if email in PROTECTED_ADMIN_EMAILS:
        raise HTTPException(status_code=400, detail="امکان غیرفعالسازی حساب مدیران سیستم وجود ندارد.")

    now = datetime.now(timezone.utc)
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE subscriptions SET status = 'revoked', updated_at = %s WHERE lower(email) = %s AND status = 'active'", (now, email))
            cur.execute('UPDATE "user" SET role = \'pending\' WHERE lower(email) = %s AND role = \'user\'', (email,))
            conn.commit()
        return {"success": True, "message": f"دسترسی {email} لغو و به حالت در انتظار (Pending) تغییر یافت."}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error revoking sub: {e}")
        raise HTTPException(status_code=500, detail="خطا در لغو اشتراک")
    finally:
        put_db_conn(conn)
