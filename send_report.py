"""data.json -> Region-wise Value ও CTN রিপোর্ট ইমেইল (প্রতিটি Regional Head-কে নিজের region-এর)।
Secrets (GitHub Actions): SMTP_USER, SMTP_PASS, RECIPIENTS (JSON)
DRY_RUN=1 দিলে ইমেইল না পাঠিয়ে preview_<REGION>.html ফাইল বানায়।"""
import json, os, smtplib, datetime, html, calendar
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DRY = os.environ.get("DRY_RUN") == "1"
data = json.load(open("data.json", encoding="utf-8"))
top = data["meta"]["top_level"]                      # BEVERAGE, NOODLES, ... (CSD/HOTFILL/HDPE BEVERAGE-এর ভেতরে, তাই আলাদা যোগ হবে না)
bd_now = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6)).replace(tzinfo=None)
rep = bd_now - datetime.timedelta(days=1)            # রিপোর্টের তারিখ = গতকাল (ডেটা গতদিন পর্যন্ত)
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

day = rep.day; days = calendar.monthrange(rep.year, rep.month)[1]
exp = day / days * 100                               # এ পর্যন্ত সময় কত % গেছে
left = days - day                                    # বাকি দিন

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

def focus(v, c):
    t, d, l = tot(v, top); p = pct(d, t)
    ok = p >= exp
    need = (t - d) / left if left > 0 else 0
    run = d / day
    if ok:
        head = f"<p style='margin:6px 0'>✅ সময় {exp:.0f}% গেছে, DO {p:.1f}% — প্রত্যাশার সমান/এগিয়ে আছে। এই গতি ধরে রাখুন।</p>"
    else:
        head = (f"<p style='margin:6px 0'>সময় <b>{exp:.0f}%</b> গেছে, কিন্তু Value DO মাত্র <b>{p:.1f}%</b> "
                f"(<b>{exp-p:.1f} পয়েন্ট</b> পিছিয়ে)। টার্গেট ধরতে বাকি {left} দিনে দিনে গড়ে <b>{fv(need,'value')}</b> DO দরকার, "
                f"এখন গড় হচ্ছে {fv(run,'value')}/দিন।</p>")
    def lag(items):                                  # (নাম, tgt, do) -> পিছিয়ে থাকাগুলো, সবচেয়ে খারাপ আগে
        out = []
        for n, tg, do in items:
            if tg <= 0: continue
            pp = pct(do, tg)
            if pp < exp: out.append((pp, n, tg, do))
        return sorted(out)[:3]
    cats = [(cn, *tot(v, [cn])[:2]) for cn in top]
    areas = [(r["area"], *tot([r], top)[:2]) for r in v]
    def li(rows):
        if not rows: return "<li>সবাই প্রত্যাশার সমান/এগিয়ে ✅</li>"
        return "".join(f"<li><b>{html.escape(n)}</b> — DO {pp:.1f}%, বাকি {fv(tg-do,'value')}"
                       f"{(' (দিনে '+fv((tg-do)/left,'value')+' দরকার)') if left>0 else ''}</li>" for pp, n, tg, do in rows)
    ct, cd, _ = tot(c, top); cp = pct(cd, ct)
    ctn = f"<p style='margin:6px 0'>CTN: DO {cp:.1f}% — " + ("প্রত্যাশার সমান/এগিয়ে ✅" if cp >= exp else f"<b>{exp-cp:.1f} পয়েন্ট পিছিয়ে</b>, বাকি {fv(ct-cd,'ctn')} CTN") + "</p>"
    return ("<div style='background:#fff4e5;border-left:4px solid #c0392b;padding:10px 14px;margin:14px 0;font-size:13px'>"
            "<div style='font-size:15px;font-weight:bold;color:#c0392b'>🎯 কোথায় উন্নতি দরকার</div>" + head +
            "<div style='margin-top:6px'><b>পিছিয়ে থাকা Category (সবচেয়ে কম DO % আগে):</b><ul style='margin:4px 0'>" + li(lag(cats)) + "</ul></div>"
            "<div><b>পিছিয়ে থাকা Area:</b><ul style='margin:4px 0'>" + li(lag(areas)) + "</ul></div>" + ctn + "</div>")

def build(region):
    v = [r for r in data["records"] if r["region"] == region]
    c = [r for r in data["ctn_records"] if r["region"] == region]
    return f"<div style='max-width:760px;font-family:Arial;color:#222'><h2 style='margin:0'>PPL FF Report – {html.escape(region)}</h2>" \
           f"<div style='font-size:12px;color:#666'>Report date: {rep:%d %b %Y} · Day {day}/{days} · সময় গেছে {exp:.0f}%</div>" \
           f"{focus(v,c)}{report(v,'value','১. Value Report (টাকা)')}{report(c,'ctn','২. CTN Report')}" \
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
    send(to, cc, f"PPL FF Report – {rg} – {rep:%d %b %Y}", body); print("sent:", rg)
