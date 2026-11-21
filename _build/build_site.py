#!/usr/bin/env python3
"""Build the password-locked colby! tour book site for GitHub Pages.

Usage: python3 -I build_site.py <abs src dir> <abs out dir> <password> [api.json]

src must hold only: template.html, data.js, logo-mask.png, photo-hero.jpg,
photo-wide.jpg and the PDFs. Everything else in src is ignored; every PDF is
published. The tour data (and the backend url/token from api.json, if given) is
encrypted with the password (AES-GCM, PBKDF2-SHA256 250k), so index.html holds
no readable tour data.
"""
import sys, os, json, re, base64, hashlib, shutil, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from PIL import Image

BG = (243, 233, 226)      # cream  --bg
INK = (23, 26, 40)        # navy   --ink
NAME, SHORT = "colby! Tour Book", "colby!"
ITER = 250000

src, out, pw = sys.argv[1:4]
api = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else None
os.makedirs(out, exist_ok=True)

tpl = open(os.path.join(src, "template.html"), encoding="utf-8").read()
js = open(os.path.join(src, "data.js"), encoding="utf-8").read()
m = re.search(r"window\.TOUR\s*=\s*(\{.*\})\s*;?\s*$", js, re.S)
data = json.loads(m.group(1))
if api:
    data["api"] = {"url": api["url"], "token": api["token"]}

# ---- encrypt ----
salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())
ct = AESGCM(key).encrypt(iv, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), None)
blob = {"s": base64.b64encode(salt).decode(), "i": base64.b64encode(iv).decode(), "n": ITER,
        "c": base64.b64encode(ct).decode()}

loader = """<script>
window.TOURBLOB=%s;
(function(){
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function unlock(pw){
  const B=window.TOURBLOB, enc=new TextEncoder();
  const base=await crypto.subtle.importKey("raw",enc.encode(pw),"PBKDF2",false,["deriveKey"]);
  const key=await crypto.subtle.deriveKey({name:"PBKDF2",salt:b64(B.s),iterations:B.n,hash:"SHA-256"},base,{name:"AES-GCM",length:256},false,["decrypt"]);
  const pt=await crypto.subtle.decrypt({name:"AES-GCM",iv:b64(B.i)},key,b64(B.c));
  return JSON.parse(new TextDecoder().decode(pt));
}
async function go(pw,remember){
  try{ window.TOUR=await unlock(pw); }catch(e){ return false; }
  if(remember){ try{localStorage.setItem("cb-pw",pw)}catch(e){} }
  if(window.TOUR.api && window.makeHostedClaude) window.claude=window.makeHostedClaude(window.TOUR.api);
  document.getElementById("lock").remove(); window.startApp(); return true;
}
document.getElementById("lockf").addEventListener("submit",async e=>{e.preventDefault();
  const btn=e.target.querySelector("button"); btn.disabled=true; btn.textContent="Opening…";
  const ok=await go(document.getElementById("pw").value,true);
  if(!ok){ btn.disabled=false; btn.textContent="Open"; document.getElementById("lockerr").hidden=false; }});
let saved=null; try{saved=localStorage.getItem("cb-pw")}catch(e){}
(async()=>{ if(!(saved && await go(saved,false))){ try{localStorage.removeItem("cb-pw")}catch(e){} document.getElementById("pw").focus(); } })();
if("serviceWorker" in navigator){ navigator.serviceWorker.register("sw.js").catch(()=>{}); }
})();
</script>""" % json.dumps(blob)
html = tpl.replace("<!--LOADER-->", loader)
assert "<!--LOADER-->" not in html and "window.TOURBLOB" in html

# safety: no plain tour data may leak into the page
for d in data["days"]:
    for field in ("venue", "address"):
        v = d.get(field)
        if v and len(v) > 6 and v in html:
            raise SystemExit("plain tour data found in index.html: " + v)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)

# ---- static files ----
pub = ["photo-hero.jpg", "photo-wide.jpg", "logo-mask.png"] + sorted(f for f in os.listdir(src) if f.lower().endswith(".pdf"))
for f in pub:
    shutil.copy2(os.path.join(src, f), os.path.join(out, f))

# ---- Home Screen icons: logo in ink on the background colour ----
logo = Image.open(os.path.join(src, "logo-mask.png")).convert("RGBA")
alpha = logo.getchannel("A")
for size in (180, 192, 512):
    icon = Image.new("RGB", (size, size), BG)
    w = int(size * 0.74)
    a = alpha.resize((w, round(alpha.height * w / alpha.width)), Image.LANCZOS)
    ink = Image.new("RGB", a.size, INK)
    icon.paste(ink, ((size - a.width) // 2, (size - a.height) // 2 + int(size * 0.02)), a)
    icon.save(os.path.join(out, "icon-%d.png" % size), optimize=True)

hexbg = "#%02X%02X%02X" % BG
json.dump({"name": NAME, "short_name": SHORT, "start_url": "./", "display": "standalone",
           "background_color": hexbg, "theme_color": hexbg,
           "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                     {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]},
          open(os.path.join(out, "manifest.webmanifest"), "w"))

ver = "cb-" + hashlib.sha256(html.encode()).hexdigest()[:10]
open(os.path.join(out, "sw.js"), "w").write("""const V="%s";
self.addEventListener("install",e=>{self.skipWaiting();});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener("fetch",e=>{const r=e.request; if(r.method!=="GET") return;
  const net=fetch(r).then(res=>{ if(res.ok){const c=res.clone(); caches.open(V).then(ca=>ca.put(r,c));} return res; });
  if(r.mode==="navigate"||r.url.endsWith(".html")){ e.respondWith(net.catch(()=>caches.match(r).then(m=>m||caches.match("./")))); }
  else { e.respondWith(caches.match(r).then(m=>m||net)); }
});""" % ver)
open(os.path.join(out, ".nojekyll"), "w").close()
print("built", out, "files:", sorted(os.listdir(out)))
