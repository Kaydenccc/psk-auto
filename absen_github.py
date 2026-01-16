import os
import requests
import random
import math
import pytz
import json
import shutil
import time
from pathlib import Path
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, Dict, Any

# ================= FILE CACHE =================
CACHE_FILE = Path(".absen_cache.json")
BACKUP_FILE = Path(".absen_cache.backup.json")

# ================= CACHE =================
def load_cache():
    if not CACHE_FILE.exists() or CACHE_FILE.stat().st_size == 0:
        return {}
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError
            return data
    except Exception:
        if CACHE_FILE.exists():
            shutil.copy(CACHE_FILE, BACKUP_FILE)
        return {"__CORRUPTED__": True}

def save_cache(cache: dict):
    if CACHE_FILE.exists():
        shutil.copy(CACHE_FILE, BACKUP_FILE)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    tmp.replace(CACHE_FILE)

# ================= TELEGRAM =================
def send_telegram(msg):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# ================= MODE =================
def mode_off():
    return os.getenv("ABSEN_MODE", "ON").upper() == "OFF"

# ================= LOGIN PUSAKA =================
class PusakaAuth:
    def __init__(self):
        self.base_url = "https://pusaka-v3.kemenag.go.id"
        self.auth_url = "https://pusaka-auth.kemenag.go.id"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://pusaka-v3.kemenag.go.id",
            "Referer": "https://pusaka-v3.kemenag.go.id/login",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=4",
            "Te": "trailers"
        })
        
    def get_csrf_token(self) -> Optional[str]:
        """Get CSRF token and cookies"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/auth/csrf",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("csrfToken")
            return None
        except Exception as e:
            print(f"Error getting CSRF token: {e}")
            return None
    
    def login(self, email: str, password: str) -> bool:
        """Login to Pusaka system"""
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            print("Failed to get CSRF token")
            return False
        
        login_data = {
            "email": email,
            "password": password,
            "redirect": "false",
            "csrfToken": csrf_token,
            "callbackUrl": "https://pusaka-v3.kemenag.go.id/login",
            "json": "true"
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/callback/credentials",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30
            )
            
            if response.status_code == 200:
                print("Login successful")
                return True
            else:
                print(f"Login failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"Error during login: {e}")
            return False
    
    def get_session_token(self) -> Optional[str]:
        """Get session token from auth session"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/auth/session",
                timeout=30
            )
            
            if response.status_code == 200:
                session_data = response.json()
                token = session_data.get("token")
                if token:
                    print("Session token obtained")
                    return token
                else:
                    print("No token in session data")
                    return None
            else:
                print(f"Failed to get session: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error getting session: {e}")
            return None
    
    def perform_attendance(self, token: str, presence_action: str, 
                          user_latitude: float, user_longitude: float) -> bool:
        """Perform attendance action"""
        # Get client IP
        try:
            ip_response = requests.get("https://api.ipify.org?format=json", timeout=10)
            client_ip = ip_response.json().get("ip", "127.0.0.1")
        except:
            client_ip = "127.0.0.1"
        
        attendance_data = {
            "client_ip": client_ip,
            "user_latitude": str(user_latitude),
            "user_longitude": str(user_longitude),
            "presence_action": presence_action,
            "status": True
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Dalvik/2.1.0"
        }
        
        try:
            response = requests.post(
                f"{self.auth_url}/presensi/api/post-presensi",
                json=attendance_data,
                headers=headers,
                timeout=30
            )
            
            print(f"Attendance response: {response.status_code}")
            print(f"Response text: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success") or result.get("message"):
                    return True
            return False
        except Exception as e:
            print(f"Error performing attendance: {e}")
            return False

# ================= JENIS ABSEN =================
def tentukan_jenis_absen(now):
    hari = now.weekday()
    jam = now.time()

    if hari >= 5:
        return None

    # in: 06:00 – 07:30
    if dt_time(6, 0) <= jam <= dt_time(7, 30):
        return "in"

    # out SENIN–KAMIS
    if hari <= 3 and dt_time(16, 0) <= jam <= dt_time(17, 30):
        return "out"

    # out JUMAT
    if hari == 4 and dt_time(16, 30) <= jam <= dt_time(18, 0):
        return "out"

    return None

# ================= OFFSET MENIT =================
def generate_offset(jenis, hari):
    if jenis == "in":
        return random.randint(5, 75)   # maksimal 07:15
    if hari == 4:  # Jumat
        return random.randint(5, 45)
    return random.randint(5, 60)

# ================= MAIN =================
def main():
    if mode_off():
        print("⛔ MODE OFF")
        return

    if not CACHE_FILE.exists():
        save_cache({})

    # DATA ABSEN - HARUS DISIMPAN DI GITHUB SECRETS
    NIP = os.getenv("PUSAKA_NIP", "199909262025051003")
    PASSWORD = os.getenv("PUSAKA_PASSWORD", "ASN003260999")
    BASE_LAT = float(os.getenv("BASE_LAT", "-3.2795460218952925"))
    BASE_LON = float(os.getenv("BASE_LON", "119.85262806281504"))

    wita = pytz.timezone("Asia/Makassar")
    now = datetime.now(wita)
    today = now.strftime("%Y-%m-%d")

    print("=" * 50)
    print("🚀 SISTEM ABSEN OTOMATIS PUSAKA")
    print(now.strftime("📅 %d/%m/%Y"))
    print(now.strftime("🕒 %H:%M:%S WITA"))
    print("=" * 50)

    jenis = tentukan_jenis_absen(now)
    if jenis not in ("in", "out"):
        print("⏸️ Di luar jam absen")
        return

    cache = load_cache()
    if "__CORRUPTED__" in cache:
        send_telegram("⚠️ CACHE RUSAK – workflow dihentikan")
        return

    # ===== NORMALISASI CACHE =====
    if today not in cache:
        cache[today] = {}

    if jenis not in cache[today] or isinstance(cache[today][jenis], bool):
        cache[today][jenis] = {"done": False, "offset": None}

    if cache[today][jenis]["done"]:
        print("⛔ Sudah absen hari ini")
        return

    # ===== OFFSET SEKALI PER HARI =====
    if cache[today][jenis]["offset"] is None:
        offset = generate_offset(jenis, now.weekday())
        cache[today][jenis]["offset"] = offset
        save_cache(cache)
    else:
        offset = cache[today][jenis]["offset"]

    # ===== JAM DASAR =====
    if jenis == "in":
        base_time = dt_time(6, 0)
    elif now.weekday() == 4:
        base_time = dt_time(16, 30)
    else:
        base_time = dt_time(16, 0)

    target_time = (
        datetime.combine(now.date(), base_time) + timedelta(minutes=offset)
    ).time()

    # BATAS in 07:30
    if jenis == "in" and target_time > dt_time(7, 30):
        target_time = dt_time(7, 30)

    if now.time() < target_time:
        print(f"⏳ Menunggu jam manusiawi {target_time}")
        return

    # ===== LOKASI ±20m =====
    r = (20 / 111111) * math.sqrt(random.random())
    t = random.random() * 2 * math.pi
    lat = BASE_LAT + r * math.cos(t)
    lon = BASE_LON + r * math.sin(t) / math.cos(math.radians(BASE_LAT))
    lokasi = f"{round(lat,7)},{round(lon,7)}"

    print(f"📍 Lokasi: {lokasi}")
    print(f"📝 Jenis: {jenis}")

    try:
        # ===== LOGIN KE PUSAKA =====
        pusaka = PusakaAuth()
        
        if not pusaka.login(email=NIP, password=PASSWORD):
            send_telegram("❌ GAGAL LOGIN KE PUSAKA")
            return
        
        # ===== AMBIL TOKEN SESSION =====
        token = pusaka.get_session_token()
        if not token:
            send_telegram("❌ GAGAL MENDAPATKAN TOKEN SESSION")
            return
        
        # ===== LAKUKAN ABSENSI =====
        success = pusaka.perform_attendance(
            token=token,
            presence_action="in" if jenis == "in" else "out",
            user_latitude=lat,
            user_longitude=lon
        )
        
        if success:
            cache[today][jenis]["done"] = True
            save_cache(cache)

            send_telegram(
                f"✅ <b>ABSEN {jenis.upper()} BERHASIL</b>\n"
                f"📅 {now.strftime('%d/%m/%Y %H:%M:%S')} WITA\n"
                f"📍 {lokasi}\n"
                f"📝 Sistem Pusaka v3"
            )
            print("✅ Absen berhasil")
        else:
            send_telegram(f"❌ ABSEN PUSAKA GAGAL - Silakan coba manual")
            print("❌ Absen gagal")

    except Exception as e:
        error_msg = f"🚨 ERROR ABSEN PUSAKA\n{str(e)}"
        send_telegram(error_msg)
        print(f"Error: {e}")

if __name__ == "__main__":
    main()