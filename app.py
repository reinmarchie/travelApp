"""TravelApp - portal tiket pesawat & cuti pegawai (Flask + SQLite).
Jalankan: pip install flask && python app.py  -> http://127.0.0.1:5000
Akun demo (password semua: 123):
  hendra@mail.com (HRD) | maya@mail.com (Manajer Travel) | andi@mail.com (Member) | rina@mail.com (Pengguna) | tamu@mail.com (Pengunjung)
"""
import os, re, sqlite3, uuid
from datetime import date, datetime
from functools import wraps
from flask import Flask, request, redirect, session, flash, get_flashed_messages, render_template_string, g, url_for
from flask_wtf.csrf import CSRFProtect, generate_csrf
from markupsafe import escape

app = Flask(__name__)
# Secret key diambil dari environment variable; jika tidak ada, dibuat acak setiap aplikasi dijalankan.
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
csrf = CSRFProtect(app)  # proteksi CSRF untuk semua form POST
DB = "travelapp.db"
STATUS = ["confirmed", "booked", "waiting for the payment"]

# ---------------- DATABASE (entity) ----------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS pengguna(id INTEGER PRIMARY KEY, nama TEXT, email TEXT UNIQUE, password TEXT, role TEXT, member INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS profil(pengguna_id INTEGER PRIMARY KEY, nama TEXT, no_identitas TEXT, tgl_lahir TEXT, no_telepon TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS pegawai(id INTEGER PRIMARY KEY, nama TEXT, jabatan TEXT);
CREATE TABLE IF NOT EXISTS pengajuan_cuti(id INTEGER PRIMARY KEY, pegawai_id INT, tgl_mulai TEXT, tgl_selesai TEXT, durasi INT);
CREATE TABLE IF NOT EXISTS saldo_cuti(pegawai_id INT, tahun INT, jatah INT, terpakai INT);
CREATE TABLE IF NOT EXISTS maskapai(id INTEGER PRIMARY KEY, nama TEXT);
CREATE TABLE IF NOT EXISTS penerbangan(id INTEGER PRIMARY KEY, maskapai_id INT, asal TEXT, tujuan TEXT, tgl TEXT, jam TEXT, harga INT);
CREATE TABLE IF NOT EXISTS pesanan(id INTEGER PRIMARY KEY, kode TEXT UNIQUE, pengguna_id INT, penerbangan_id INT, tgl_pesan TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS validasi_tiket(id INTEGER PRIMARY KEY, pesanan_id INT, waktu TEXT, hasil TEXT);
CREATE TABLE IF NOT EXISTS etiket(id INTEGER PRIMARY KEY, pesanan_id INT, nomor TEXT, tgl_terbit TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS otorisasi_tiket(id INTEGER PRIMARY KEY, kode_input TEXT, waktu TEXT, hasil TEXT);
"""
SEED = """
INSERT INTO pengguna VALUES(1,'Andi Pratama','andi@mail.com','123','user',1),(2,'Rina Wulandari','rina@mail.com','123','user',0),
 (3,'Tamu Pengunjung','tamu@mail.com','123','user',0),(4,'Hendra (HRD)','hendra@mail.com','123','hrd',0),(5,'Maya (Manajer Travel)','maya@mail.com','123','manajer',0);
INSERT INTO profil VALUES(1,'Andi Pratama','','','','andi@mail.com');
INSERT INTO pegawai VALUES(1,'Budi Santoso','Staff IT'),(2,'Sari Dewi','Akuntan'),(3,'Joko Widodo','Marketing');
INSERT INTO pengajuan_cuti VALUES(1,1,'2026-12-01','2026-12-03',3),(2,2,'2026-12-10','2026-12-14',5),(3,1,'2026-03-01','2026-03-02',2),(4,3,'2026-11-20','2026-11-22',3);
INSERT INTO saldo_cuti VALUES(1,2026,12,5),(2,2026,12,5),(3,2026,12,3);
INSERT INTO maskapai VALUES(1,'Garuda Indonesia'),(2,'Lion Air'),(3,'Citilink');
INSERT INTO penerbangan VALUES(1,1,'Malang','Jakarta','2026-12-01','08:00',1200000),(2,2,'Malang','Jakarta','2026-12-01','13:00',800000),
 (3,3,'Malang','Bali','2026-12-01','10:00',900000),(4,1,'Jakarta','Bali','2026-12-03','09:00',1100000),(5,2,'Jakarta','Surabaya','2026-12-02','15:00',700000),
 (6,3,'Jakarta','Bali','2026-12-03','17:00',850000);
INSERT INTO pesanan VALUES(1,'BK0001',1,1,'2026-11-16','confirmed'),(2,'BK0002',2,2,'2026-11-16','waiting for the payment'),(3,'BK0003',1,3,'2026-11-17','booked');
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def q(sql, args=(), one=False):
    cur = db().execute(sql, args); rows = cur.fetchall(); db().commit()
    return (rows[0] if rows else None) if one else rows

def init_db():
    c = sqlite3.connect(DB); c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM pengguna").fetchone(): c.executescript(SEED)
    c.commit(); c.close()

# ---------------- TAMPILAN (boundary) ----------------
NAV = {
    "hrd": [("Pengajuan Cuti", "cuti")],
    "manajer": [("Status Booking", "booking"), ("Pesan untuk Pengunjung", "booking_baru"), ("Otorisasi Tiket", "otorisasi")],
    "user": [("Cari Tiket", "cari"), ("Pesanan Saya", "pesanan")],
    "member": [("Cari Tiket", "cari"), ("Multi-Destinasi", "multi"), ("Bandingkan", "bandingkan"), ("Pesanan Saya", "pesanan"), ("Profil", "profil")],
}
LAYOUT = """<!doctype html><html lang=id><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{{t}} - TravelApp</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:system-ui,Segoe UI,sans-serif;background:#f3f6fb;color:#1f2937}
header{background:#0b5ed7;color:#fff;display:flex;align-items:center;gap:6px;padding:0 20px;flex-wrap:wrap}
header .brand{font-weight:700;font-size:20px;margin-right:18px;padding:14px 0;color:#fff;text-decoration:none}
header a.nav{color:#dbe7ff;text-decoration:none;padding:16px 12px}header a.nav:hover,header a.on{background:#0a4fb3;color:#fff}
header .who{margin-left:auto;font-size:14px}header .who a{color:#fff;margin-left:10px}
main{max-width:960px;margin:24px auto;padding:0 16px}h1{margin:0 0 16px;font-size:24px}
.card{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px #0001;margin-bottom:16px}
table{border-collapse:collapse;width:100%}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid #e5e7eb}th{background:#f8fafc;font-size:13px;color:#475569}
input,select{padding:8px;border:1px solid #cbd5e1;border-radius:6px;font-size:14px;margin:2px 4px 2px 0}
button,.btn{background:#0b5ed7;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block}
button.red{background:#dc2626}.btn.gray{background:#64748b}label{font-size:13px;color:#475569;display:block;margin-top:8px}
.msg{padding:10px 14px;border-radius:8px;margin-bottom:12px}.msg.ok{background:#dcfce7;color:#166534}.msg.err{background:#fee2e2;color:#991b1b}
.badge{padding:3px 9px;border-radius:12px;font-size:12px;background:#e2e8f0}.badge.confirmed{background:#dcfce7;color:#166534}
.badge.booked{background:#dbeafe;color:#1e40af}.badge.waiting{background:#fef9c3;color:#854d0e}.badge.dibatalkan{background:#fee2e2;color:#991b1b}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.grid a{text-decoration:none;color:inherit}
.grid .card:hover{box-shadow:0 3px 10px #0002}.muted{color:#64748b;font-size:14px}form.inline{display:inline}
</style></head><body>
<header><a class=brand href="{{url_for('dashboard') if user else url_for('login')}}">✈ TravelApp</a>
{% if user %}{% for label,ep in nav %}<a class="nav {{'on' if ep==cur}}" href="{{url_for(ep)}}">{{label}}</a>{% endfor %}
<span class=who>{{user.nama}} <a href="{{url_for('logout')}}">Keluar</a></span>{% endif %}</header>
<main>{% for c,m in msgs %}<div class="msg {{c}}">{{m}}</div>{% endfor %}<h1>{{t}}</h1>{{b|safe}}</main></body></html>"""

def me():
    return q("SELECT * FROM pengguna WHERE id=?", (session["uid"],), one=True) if "uid" in session else None

def role_key(u):
    return "member" if u and u["role"] == "user" and u["member"] else (u["role"] if u else None)

def page(title, body):
    u = me()
    token = f"<input type=hidden name=csrf_token value='{generate_csrf()}'>"
    body = re.sub(r"<form[^>]*>", lambda m: m.group(0) + token if "method=post" in m.group(0) else m.group(0), body)
    return render_template_string(LAYOUT, t=title, b=body, user=u, nav=NAV.get(role_key(u), []),
                                  cur=request.endpoint, msgs=get_flashed_messages(with_categories=True))

def need(*roles):
    """Wajib login & batasi akses per peran. 'user' = semua pengguna biasa (termasuk member)."""
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = me()
            if not u: return redirect(url_for("login"))
            ok = not roles or role_key(u) in roles or (u["role"] == "user" and "user" in roles)
            if not ok:
                flash("Anda tidak punya akses ke halaman itu.", "err"); return redirect(url_for("dashboard"))
            return f(*a, **k)
        return w
    return deco

def rp(n): return f"Rp{n:,}".replace(",", ".")
def badge(s): return f'<span class="badge {s.split()[0]}">{s}</span>'

def flight_table(rows, aksi=False):
    if not rows: return "<p class=muted>Tidak ada penerbangan yang cocok.</p>"
    out = "<table><tr><th>Rute</th><th>Tanggal</th><th>Jam</th><th>Maskapai</th><th>Harga</th><th></th></tr>"
    for r in rows:
        btn = f"<form class=inline method=post action='{url_for('pesan')}'><input type=hidden name=fid value={r['id']}><button>Pesan</button></form>" if aksi else ""
        out += f"<tr><td>{r['asal']} → {r['tujuan']}</td><td>{r['tgl']}</td><td>{r['jam']}</td><td>{r['maskapai']}</td><td>{rp(r['harga'])}</td><td>{btn}</td></tr>"
    return out + "</table>"

# ---------------- LOGIN & DASHBOARD ----------------
@app.route("/")
def index(): return redirect(url_for("dashboard" if "uid" in session else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q("SELECT * FROM pengguna WHERE email=? AND password=?", (request.form["email"].strip(), request.form["password"]), one=True)
        if u: session["uid"] = u["id"]; return redirect(url_for("dashboard"))
        flash("Email atau password salah.", "err")
    return page("Masuk", """<div class=card style="max-width:380px;margin:auto"><form method=post>
    <label>Email</label><input name=email style="width:100%" required><label>Password</label><input type=password name=password style="width:100%" required><br><br>
    <button style="width:100%">Masuk</button></form></div>
    <p class=muted style="text-align:center">Akun demo (password 123): hendra@mail.com · maya@mail.com · andi@mail.com · rina@mail.com · tamu@mail.com</p>""")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@need()
def dashboard():
    u = me(); rk = role_key(u)
    cards = "".join(f"<a href='{url_for(ep)}'><div class=card><b>{label}</b></div></a>" for label, ep in NAV[rk])
    info = ""
    if rk in ("user", "member"):
        n = q("SELECT COUNT(*) c FROM pesanan WHERE pengguna_id=? AND status!='dibatalkan'", (u["id"],), one=True)["c"]
        info = f"<div class=card>Anda punya <b>{n}</b> pesanan aktif.</div>"
    if rk == "manajer":
        info = "<div class=card>" + " ".join(f"{badge(r['status'])} {r['c']}" for r in q("SELECT status, COUNT(*) c FROM pesanan GROUP BY status")) + "</div>"
    if rk == "hrd":
        info = f"<div class=card>Total pengajuan cuti tercatat: <b>{q('SELECT COUNT(*) c FROM pengajuan_cuti', one=True)['c']}</b></div>"
    return page(f"Halo, {u['nama']}", info + f"<div class=grid>{cards}</div>")

# ---------------- HRD: pengajuan cuti ----------------
def ctrl_cari_pengajuan(mulai, selesai):
    return q("""SELECT p.id pid, p.nama, c.tgl_mulai, c.tgl_selesai, c.durasi FROM pengajuan_cuti c JOIN pegawai p ON p.id=c.pegawai_id
                WHERE c.tgl_mulai<=? AND c.tgl_selesai>=? ORDER BY c.tgl_mulai""", (selesai, mulai))

@app.route("/cuti")
@need("hrd")
def cuti():
    m, s = request.args.get("mulai", "2026-01-01"), request.args.get("selesai", "2026-12-31")
    rows = ctrl_cari_pengajuan(m, s)
    body = f"<div class=card><form>Periode: <input type=date name=mulai value={m}> s/d <input type=date name=selesai value={s}> <button>Tampilkan</button></form></div>"
    t = "<div class=card><table><tr><th>Pegawai</th><th>Mulai</th><th>Selesai</th><th>Lama</th><th></th></tr>"
    for r in rows:
        t += f"<tr><td>{r['nama']}</td><td>{r['tgl_mulai']}</td><td>{r['tgl_selesai']}</td><td>{r['durasi']} hari</td><td><a class=btn href='{url_for('cuti_pegawai', pid=r['pid'])}'>Riwayat</a></td></tr>"
    return page("Pengajuan Cuti Pegawai", body + t + "</table>" + ("" if rows else "<p class=muted>Tidak ada pengajuan pada periode ini.</p>") + "</div>")

@app.route("/cuti/<int:pid>")
@need("hrd")
def cuti_pegawai(pid):
    p = q("SELECT * FROM pegawai WHERE id=?", (pid,), one=True)
    if not p: flash("Pegawai tidak ditemukan.", "err"); return redirect(url_for("cuti"))
    riw = q("SELECT * FROM pengajuan_cuti WHERE pegawai_id=? ORDER BY tgl_mulai", (pid,))
    s = q("SELECT * FROM saldo_cuti WHERE pegawai_id=? AND tahun=?", (pid, date.today().year), one=True)
    sisa = f"<div class=card>Sisa cuti {s['tahun']}: <b>{s['jatah']-s['terpakai']} hari</b> <span class=muted>(jatah {s['jatah']}, terpakai {s['terpakai']})</span></div>" if s else ""
    t = "<div class=card><table><tr><th>Mulai</th><th>Selesai</th><th>Lama</th></tr>" + "".join(f"<tr><td>{r['tgl_mulai']}</td><td>{r['tgl_selesai']}</td><td>{r['durasi']} hari</td></tr>" for r in riw) + "</table></div>"
    return page(f"Riwayat Cuti: {p['nama']}", sisa + t + f"<a class='btn gray' href='{url_for('cuti')}'>← Kembali</a>")

# ---------------- Pengguna: cari, pesan, pesanan ----------------
def ctrl_cari_penerbangan(tujuan_list=(), tgl="", asal=""):
    sql, args = "SELECT f.*, m.nama maskapai FROM penerbangan f JOIN maskapai m ON m.id=f.maskapai_id WHERE 1=1", []
    if tujuan_list: sql += " AND f.tujuan IN (%s)" % ",".join("?" * len(tujuan_list)); args += list(tujuan_list)
    if tgl: sql += " AND f.tgl=?"; args.append(tgl)
    if asal: sql += " AND f.asal=?"; args.append(asal)
    return q(sql + " ORDER BY f.tgl, f.jam", args)

@app.route("/cari")
@need("user")
def cari():
    raw, tgl = request.args.get("tujuan", ""), request.args.get("tgl", "")
    form = f"""<div class=card><form>Tujuan <input name=tujuan value="{escape(raw)}" placeholder="Jakarta, Bali"> Tanggal <input type=date name=tgl value="{tgl}"> <button>Cari</button>
    <div class=muted>Boleh isi beberapa tujuan, pisahkan dengan koma.</div></form></div>"""
    rows = ctrl_cari_penerbangan([t.strip() for t in raw.split(",") if t.strip()], tgl)
    return page("Cari Penerbangan", form + f"<div class=card>{flight_table(rows, aksi=True)}</div>")

def ctrl_buat_pesanan(uid, fid, status="waiting for the payment"):
    kode = "BK" + uuid.uuid4().hex[:6].upper()
    q("INSERT INTO pesanan(kode,pengguna_id,penerbangan_id,tgl_pesan,status) VALUES(?,?,?,?,?)", (kode, uid, fid, date.today().isoformat(), status))
    return q("SELECT * FROM pesanan WHERE kode=?", (kode,), one=True)

@app.route("/pesan", methods=["POST"])
@need("user")
def pesan():
    p = ctrl_buat_pesanan(session["uid"], request.form["fid"])
    flash(f"Pesanan berhasil dibuat. Kode booking: {p['kode']} (menunggu pembayaran).", "ok")
    return redirect(url_for("pesanan"))

@app.route("/pesanan")
@need("user")
def pesanan():
    rows = q("""SELECT s.id, s.kode, s.status, f.asal||' → '||f.tujuan rute, f.tgl, m.nama maskapai, e.nomor etiket FROM pesanan s
                JOIN penerbangan f ON f.id=s.penerbangan_id JOIN maskapai m ON m.id=f.maskapai_id LEFT JOIN etiket e ON e.pesanan_id=s.id
                WHERE s.pengguna_id=? ORDER BY s.id DESC""", (session["uid"],))
    t = "<div class=card><table><tr><th>Kode</th><th>Rute</th><th>Tanggal</th><th>Maskapai</th><th>Status</th><th>E-tiket</th><th></th></tr>"
    for r in rows:
        btn = "" if r["status"] == "dibatalkan" else f"<form class=inline method=post action='{url_for('batal', pid=r['id'])}' onsubmit=\"return confirm('Batalkan pesanan ini?')\"><button class=red>Batalkan</button></form>"
        t += f"<tr><td>{r['kode']}</td><td>{r['rute']}</td><td>{r['tgl']}</td><td>{r['maskapai']}</td><td>{badge(r['status'])}</td><td>{r['etiket'] or '-'}</td><td>{btn}</td></tr>"
    return page("Pesanan Saya", t + "</table>" + ("" if rows else "<p class=muted>Belum ada pesanan.</p>") + "</div>")

@app.route("/pesanan/<int:pid>/batal", methods=["POST"])
@need("user")
def batal(pid):
    q("UPDATE pesanan SET status='dibatalkan' WHERE id=? AND pengguna_id=?", (pid, session["uid"]))
    flash("Pesanan dibatalkan.", "ok"); return redirect(url_for("pesanan"))

# ---------------- Member: multi-destinasi, bandingkan, profil ----------------
def ctrl_cari_multi(asal, tgl, tujuan_list):
    legs, cur, total, cur_tgl = [], asal, 0, tgl
    for t in tujuan_list:
        f = q("""SELECT f.*, m.nama maskapai FROM penerbangan f JOIN maskapai m ON m.id=f.maskapai_id
                 WHERE f.asal=? AND f.tujuan=? AND f.tgl>=? ORDER BY f.tgl, f.harga LIMIT 1""", (cur, t, cur_tgl), one=True)
        if not f: return None, f"Tidak ada penerbangan {cur} → {t} pada/setelah {cur_tgl}."
        legs.append(f); total += f["harga"]; cur, cur_tgl = t, f["tgl"]
    return {"legs": legs, "total": total}, None

@app.route("/multi")
@need("member")
def multi():
    a = request.args
    form = f"""<div class=card><form>Dari <input name=asal value="{a.get('asal','Malang')}"> Tanggal <input type=date name=tgl value="{a.get('tgl','2026-12-01')}">
    Tujuan berurutan <input name=tujuan value="{a.get('tujuan','Jakarta, Bali')}"> <button>Cari</button></form></div>"""
    body = form
    if "asal" in a:
        it, err = ctrl_cari_multi(a["asal"], a["tgl"], [t.strip() for t in a["tujuan"].split(",") if t.strip()])
        body += f"<div class='msg err'>{err}</div>" if err else f"<div class=card><b>{len(it['legs'])} penerbangan</b> · total <b>{rp(it['total'])}</b>{flight_table(it['legs'])}</div>"
    return page("Penerbangan Multi-Destinasi", body)

@app.route("/bandingkan")
@need("member")
def bandingkan():
    a = request.args
    form = f"""<div class=card><form>Tujuan <input name=tujuan value="{a.get('tujuan','')}"> Tanggal <input type=date name=tgl value="{a.get('tgl','')}">
    Berangkat setelah jam <input type=time name=jam value="{a.get('jam','')}"> <button>Bandingkan</button></form></div>"""
    rows = ctrl_cari_penerbangan([a["tujuan"]] if a.get("tujuan") else [], a.get("tgl", ""))
    if a.get("jam"): rows = [r for r in rows if r["jam"] >= a["jam"]]
    rows = sorted(rows, key=lambda r: r["harga"])
    return page("Bandingkan Penerbangan", form + f"<div class=card><p class=muted>Diurutkan dari harga termurah.</p>{flight_table(rows, aksi=True)}</div>")

FIELDS = [("nama", "Nama lengkap"), ("no_identitas", "No. identitas (KTP/Paspor)"), ("tgl_lahir", "Tanggal lahir"), ("no_telepon", "No. telepon"), ("email", "Email")]

def ctrl_profil_lengkap(uid):
    p = q("SELECT * FROM profil WHERE pengguna_id=?", (uid,), one=True)
    return bool(p and all((p[f] or "").strip() for f, _ in FIELDS))

@app.route("/profil", methods=["GET", "POST"])
@need("member")
def profil():
    uid = session["uid"]
    if request.method == "POST":
        q("INSERT OR REPLACE INTO profil VALUES(?,?,?,?,?,?)", (uid, *[request.form.get(f, "") for f, _ in FIELDS]))
        flash("Profil berhasil disimpan.", "ok"); return redirect(url_for("profil"))
    p = q("SELECT * FROM profil WHERE pengguna_id=?", (uid,), one=True)
    inputs = "".join(f"<label>{lab}</label><input style='width:100%' name={f} value=\"{escape(p[f] if p else '')}\">" for f, lab in FIELDS)
    status = "<span class='badge confirmed'>Lengkap</span>" if ctrl_profil_lengkap(uid) else "<span class='badge waiting'>Belum lengkap</span>"
    tk = q("SELECT id,kode,status FROM pesanan WHERE pengguna_id=? AND status!='dibatalkan'", (uid,))
    val = "".join(f"<tr><td>{t['kode']}</td><td>{badge(t['status'])}</td><td><form class=inline method=post action='{url_for('validasi', pid=t['id'])}'><button>Validasi</button></form></td></tr>" for t in tk)
    return page("Profil Member", f"<div class=card>Status data profil: {status}<form method=post>{inputs}<br><br><button>Simpan profil</button></form></div>"
                f"<div class=card><b>Validasi tiket</b><p class=muted>Validasi hanya bisa dilakukan jika profil sudah lengkap.</p><table>{val}</table></div>")

@app.route("/validasi/<int:pid>", methods=["POST"])
@need("member")
def validasi(pid):
    if not ctrl_profil_lengkap(session["uid"]):
        flash("Data profil tidak lengkap. Validasi tiket ditolak.", "err"); return redirect(url_for("profil"))
    q("INSERT INTO validasi_tiket(pesanan_id,waktu,hasil) VALUES(?,?,?)", (pid, datetime.now().isoformat(timespec="seconds"), "valid"))
    flash("Tiket berhasil divalidasi.", "ok"); return redirect(url_for("profil"))

# ---------------- Manajer travel ----------------
@app.route("/booking")
@need("manajer")
def booking():
    st = request.args.get("status", "")
    opts = "<option value=''>Semua status</option>" + "".join(f"<option {'selected' if s==st else ''}>{s}</option>" for s in STATUS)
    sql = """SELECT s.kode, p.nama pengguna, f.asal||' → '||f.tujuan rute, f.tgl, s.status FROM pesanan s JOIN pengguna p ON p.id=s.pengguna_id
             JOIN penerbangan f ON f.id=s.penerbangan_id"""
    rows = q(sql + (" WHERE s.status=?" if st else "") + " ORDER BY s.id DESC", (st,) if st else ())
    t = "<div class=card><table><tr><th>Kode</th><th>Pemesan</th><th>Rute</th><th>Tanggal</th><th>Status</th></tr>" + \
        "".join(f"<tr><td>{r['kode']}</td><td>{r['pengguna']}</td><td>{r['rute']}</td><td>{r['tgl']}</td><td>{badge(r['status'])}</td></tr>" for r in rows) + "</table></div>"
    return page("Status Booking", f"<div class=card><form><select name=status>{opts}</select> <button>Filter</button></form></div>" + t)

def ctrl_kirim_etiket(p, pj):
    nomor = "ET" + uuid.uuid4().hex[:8].upper()
    q("INSERT INTO etiket(pesanan_id,nomor,tgl_terbit,email) VALUES(?,?,?,?)", (p["id"], nomor, date.today().isoformat(), pj["email"]))
    print(f"[EMAIL] E-tiket {nomor} dikirim ke {pj['email']}")  # ganti dengan SMTP asli bila perlu
    return nomor

@app.route("/booking/baru", methods=["GET", "POST"])
@need("manajer")
def booking_baru():
    if request.method == "POST":
        pj = q("SELECT * FROM pengguna WHERE id=? AND role='user'", (request.form["vid"],), one=True)
        p = ctrl_buat_pesanan(pj["id"], request.form["fid"], status="booked")
        nomor = ctrl_kirim_etiket(p, pj)
        flash(f"Pesanan {p['kode']} atas nama {pj['nama']} dibuat. E-tiket {nomor} dikirim ke {pj['email']}.", "ok")
        return redirect(url_for("booking"))
    tujuan = request.args.get("tujuan", "")
    rows = ctrl_cari_penerbangan([tujuan] if tujuan else [])
    vis = "".join(f"<option value={u['id']}>{u['nama']} ({u['email']})</option>" for u in q("SELECT * FROM pengguna WHERE role='user'"))
    body = f"<div class=card><form>Tujuan <input name=tujuan value='{escape(tujuan)}'> <button>Cari tiket</button></form></div>"
    if rows:
        body += f"<div class=card><form method=post>Pengunjung <select name=vid>{vis}</select><table><tr><th></th><th>Rute</th><th>Tanggal</th><th>Maskapai</th><th>Harga</th></tr>"
        body += "".join(f"<tr><td><input type=radio name=fid value={r['id']} required></td><td>{r['asal']} → {r['tujuan']}</td><td>{r['tgl']}</td><td>{r['maskapai']}</td><td>{rp(r['harga'])}</td></tr>" for r in rows)
        body += "</table><br><button>Pesan atas nama pengunjung</button></form></div>"
    return page("Pesan untuk Pengunjung", body)

def ctrl_otorisasi(kode):
    p = q("SELECT s.*, pg.nama pemesan FROM pesanan s JOIN pengguna pg ON pg.id=s.pengguna_id WHERE s.kode=?", (kode.strip(),), one=True)
    q("INSERT INTO otorisasi_tiket(kode_input,waktu,hasil) VALUES(?,?,?)", (kode, datetime.now().isoformat(timespec="seconds"), "sesuai" if p else "tidak sesuai"))
    return p

@app.route("/otorisasi", methods=["GET", "POST"])
@need("manajer")
def otorisasi():
    form = "<div class=card><form method=post>Kode booking reference <input name=kode required> <button>Otorisasi</button></form></div>"
    if request.method == "POST":
        p = ctrl_otorisasi(request.form["kode"])
        if not p: flash("Kode booking reference tidak sesuai. Silakan input ulang.", "err")
        else: form += f"<div class=card>Kode <b>{p['kode']}</b> sesuai · atas nama {p['pemesan']}<br>Status booking: {badge(p['status'])}</div>"
    return page("Otorisasi Tiket", form)

if __name__ == "__main__":
    init_db(); app.run()
