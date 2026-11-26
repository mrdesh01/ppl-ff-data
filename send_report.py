"""data.json -> Region-wise Value ও CTN রিপোর্ট ইমেইল (প্রতিটি Regional Head-কে নিজের region-এর)।
Secrets (GitHub Actions): SMTP_USER, SMTP_PASS, RECIPIENTS (JSON)
DRY_RUN=1 দিলে ইমেইল না পাঠিয়ে preview_<REGION>.html ফাইল বানায়।"""
import json, os, smtplib, datetime, html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DRY = os.environ.get("DRY_RUN") == "1"
data = json.load(open("data.json", encoding="utf-8"))
top = data["meta"]["top_level"]                      # BEVERAGE, NOODLES, ... (CSD/HOTFILL/HDPE BEVERAGE-এর ভেতরে, তাই আলাদা যোগ হবে না)
bd_now = datetime.datetime.utcnow() + datetime.timedelta(hours=6)
gen = datetime.datetime.fromisoformat(data["meta"]["generated_at"])
fresh = DRY or gen.date() == bd_now.date()           # আজকের data.json না হলে regional head-দের পাঠানো হবে না

def fv(x, unit):                                     # value -> Cr/L, ctn -> সংখ্যা
    if unit == "ctn": return f"{x:,.0f}"
    if abs(x) >= 1e7: return f"{x/1e7:.2f} Cr"
    if abs(x) >= 1e5: return f"{x/1e5:.2f} L"
    return f"{x:,.0f}"
def pct(a, b): return (a / b * 100) if b else 0
def col(p, exp):                                     # সময়ের তুলনায় অবস্থা: সবুজ/হলুদ/লাল
    return "#1a7f37" if p >= exp else ("#b7791f" if p >= exp - 10 else "#c0392b")

day, days = bd_now.day, 30
exp = day / days * 100
TH = "padding:6px 10px;background:#0f6b6b;color:#fff;text-align:right;font-size:12px"
TD = "padding:6px 10px;border-bottom:1px solid #e5e0d5;text-align:right;font-size:13px"

def table(rows, label, unit):
    h = f"<table style='border-collapse:collapse;width:100%;font-family:Arial'><tr><th style='{TH};text-align:left'>{label}</th>" \
        + "".join(f"<th style='{TH}'>{t}</th>" for t in ["Target", "DO", "DO %", "Delivery", "DEL %", "Gap"]) + "</tr>"
    for name, t, d, l, bold in rows:
        p, q = pct(d, t), pct(l, t); w = "font-weight:bold;background:#f3efe6;" if bold else ""
        h += f"<tr><td style='{TD};text-align:left;{w}'>{html.escape(name)}</td><td style='{TD};{w}'>{fv(t,unit)}</td><td style='{TD};{w}'>{fv(d,unit)}</td>" \
             f"<td style='{TD};{w}color:{col(p,exp)}'>{p:.1f}%</td><td style='{TD};{w}'>{fv(l,unit)}</td><td style='{TD};{w}color:{col(q,exp)}'>{q:.1f}%</td><td style='{TD};{w}'>{fv(max(t-d,0),unit)}</td></tr>"
    return h + "</table>"

def tot(recs, cats):
    return [sum(r["categories"][c][k] for r in recs for c in cats) for k in ("tgt", "do", "del")]

def report(recs, unit, title):
    t, d, l = tot(recs, top)
    cat_rows = [(c, *tot(recs, [c]), False) for c in top] + [("TOTAL", t, d, l, True)]
    area_rows = [(r["area"], *tot([r], top), False) for r in recs] + [("TOTAL", t, d, l, True)]
    return f"<h3 style='font-family:Arial;color:#0f6b6b;margin:22px 0 6px'>{title}</h3>" \
           f"{table(cat_rows,'Category',unit)}<div style='height:12px'></div>{table(area_rows,'Area',unit)}"

def build(region):
    v = [r for r in data["records"] if r["region"] == region]
    c = [r for r in data["ctn_records"] if r["region"] == region]
    return f"<div style='max-width:760px;font-family:Arial;color:#222'><h2 style='margin:0'>PPL FF Report – {html.escape(region)}</h2>" \
           f"<div style='font-size:12px;color:#666'>Report date: {bd_now:%d %b %Y} · Day {day}/{days} · সময় গেছে {exp:.0f}%</div>" \
           f"{report(v,'value','১. Value Report (টাকা)')}{report(c,'ctn','২. CTN Report')}" \
           f"<p style='font-size:11px;color:#888;margin-top:18px'>Auto-generated report · Source: {html.escape(data['meta']['source'])}</p></div>"

recip = json.loads(os.environ.get("RECIPIENTS", "{}"))
regions = sorted({r["region"] for r in data["records"]})
user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")

def send(to, cc, subject, body):
    m = MIMEMultipart("alternative"); m["From"] = user; m["To"] = ", ".join(to); m["Subject"] = subject
    if cc: m["Cc"] = ", ".join(cc)
    m.attach(MIMEText(body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw); s.sendmail(user, to + cc, m.as_string())

if not fresh:
    msg = f"আজকের ({bd_now:%d %b}) data.json আপলোড হয়নি। শেষ data: {gen:%d %b %H:%M}। Regional head-দের ইমেইল পাঠানো হয়নি।"
    print(msg)
    if user: send([user], [], "⚠ PPL FF report পাঠানো হয়নি", f"<p>{msg}</p>")
    raise SystemExit(0)

cc = recip.get("CC", [])
for rg in regions:
    body = build(rg)
    if DRY:
        open(f"preview_{rg.replace(' ','_')}.html", "w", encoding="utf-8").write(body); continue
    to = recip.get(rg, [])
    if not to: print("প্রাপক নেই:", rg); continue
    send(to, cc, f"PPL FF Report – {rg} – {bd_now:%d %b %Y}", body); print("sent:", rg)
