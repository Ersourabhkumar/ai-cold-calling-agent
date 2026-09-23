# Usage Guide — AI Cold Calling Agent (Telecaller Team)

> Ye file team ke liye hai. Simple bhasha me — kya chalana hai, kaise call karni hai, kya NAHI karna hai.

---

## 1. Roz ka setup (5 minute, ek baar)

### Terminal 1 — Database (sirf pehli baar / restart ke baad)
Project folder me:
```
cd "E:\cold calling agent\ai-cold-calling-agent"
docker compose up -d postgres redis
```
Check: `docker ps` me `postgres-1` aur `redis-1` dono `Up` dikhne chahiye.
**`docker compose down` KABHI mat chalana — data chala jayega.**

### Terminal 2 — App server (roz chalu rakhna)
```
cd "E:\cold calling agent\ai-cold-calling-agent"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Band mat karo jab tak kaam chal raha hai. `.env` me kuch badla ho to restart zaroori hai (Ctrl+C, phir wahi command).

### Terminal 3 — Tunnel, sirf Sarvam ke liye (roz chalu rakhna)
```
cloudflared tunnel --url http://localhost:8000
```
Jo `https://...trycloudflare.com` URL mile — wahi `.env` ke `PUBLIC_BASE_URL` me hona chahiye.
**Is terminal ko restart mat karo** — restart hua to URL badal jayegi, phir `.env` update + app restart karna padega.

### Terminal 4 aur 5 — Followup worker (callbacks auto-process ke liye)
```
celery -A app.core.celery_app.celery_app worker --loglevel=INFO --pool=solo
```
```
celery -A app.core.celery_app.celery_app beat --loglevel=INFO
```
Ye dono chalu rahenge to callback followups apne time par process honge.

---

## 2. URLs ka rule (sabse zaroori)

| Kaun | URL |
|---|---|
| Tum / team (dashboard) | `http://localhost:8000/ui` |
| Tum / team (Swagger/API docs) | `http://localhost:8000/docs` |
| Sirf Sarvam webhook ke liye | tunnel wali `https://...trycloudflare.com` URL |

**Browser me HAMESHA localhost kholo.** Tunnel URL browser me khologe to kabhi-kabhi 502 error aayega (wo Sarvam ke liye hai, tumhare liye nahi).

---

## 3. API Key (ek baar setup)

- Key hai: `xy-admin-key`
- **Swagger me:** upar-right **Authorize** button → key dalo → Authorize → Close. Ab sab Execute kaam karenge.
- **Dashboard (UI) me:** left sidebar me neeche **API key field** hai → key dalo → Enter. Browser yaad rakhega.
- Bina key ke call/list wale buttons 401 denge — ghabrana mat, key dalo.

---

## 4. Call kaise karni hai (2 tareeke)

### Tareeka A — Dashboard se (team ke liye easy)
1. `http://localhost:8000/ui` kholo → sidebar me key dalo (ek baar)
2. **Fire Live Call** page kholo
3. Phone (E.164 format, jaise `+91...`), naam, city, requirement, budget, timeline bharo
4. **Campaign Name UNIQUE rakho** — roz naya naam, jaise `Team-2026-09-24-A`. Purana naam dobara use hoga to error (409) aayega.
5. **Fire Live Call** dabao → phone haath me rakho, kuch second me bajega
6. Baat khatam hone ke 1-2 min baad wahi page par **Call ID se Refresh Status** → status COMPLETED + transcript + qualification dekho

### Tareeka B — Swagger se (testing ke liye)
1. `http://localhost:8000/docs` kholo (localhost! tunnel nahi)
2. Authorize karo (Section 3)
3. **Admin → POST /api/admin/test-call → Try it out**, body:
```json
{
  "phone": "+917822007138",
  "lead_name": "Test Lead",
  "city": "Mumbai",
  "requirement": "2 BHK flat",
  "budget": "5000000",
  "timeline": "3 months",
  "campaign_name": "UNIQUE-NAAM-YAHAN"
}
```
4. Execute → `success: true` + `call.id` note karo → phone bajega
5. Status: **Admin → POST /api/admin/test-call/status** me `call_id` dalke Execute

---

## 5. Roz ke pages (dashboard me)

| Page | Kaam |
|---|---|
| Dashboard | Aaj ke stats — leads, calls, answered, pending followups, campaigns |
| Leads / CRM | Saare leads + **+ Add Lead** button; row par click = poori history |
| Calls | Saari calls — status, outcome, duration, provider |
| Follow-ups | PENDING callbacks (worker time par process karega), DONE history |
| Lead detail | Ek lead ki calls + transcript + qualification + followups |
| Fire Live Call | Nayi call trigger + status check |

---

## 6. Call ke baad kya check karna hai

- Status **COMPLETED** hona chahiye (FAILED aaye to response ka error padho)
- **Transcript** aaya? (Call detail / status me)
- **Lead fields update** hue? (city, budget, timeline, requirement)
- **Callback** manga tha to Follow-ups me PENDING entry bani?
- **Recording URL** available hai?

---

## 7. Kya MAT karna (strict rules)

1. `docker compose down` — kabhi nahi
2. Same `campaign_name` dobara — kabhi nahi (naya naam har call par)
3. Tunnel URL browser/share — kabhi nahi (sirf Sarvam webhook ke liye hai)
4. `.env` ki Sarvam keys chhedna — sirf tab jab agent ka naya version commit ho (tab sirf `SARVAM_APP_VERSION` badalta hai)
5. Terminal 2/3 band karna jab testing chal rahi ho — nahi
6. Pehli call verify hue bina bulk calling — nahi (ek-ek karke, phir scale)

---

## 8. Agent me change kiya to (prompt/voice/variables)

1. Dashboard me edit + commit → **naya version number note karo**
2. `.env` me `SARVAM_APP_VERSION=<naya-number>` (sirf ye 1 line!)
3. Terminal 2 restart
4. Test call → duration + transcript + cost compare karo

---

## 9. Problem aaye to (troubleshooting)

| Problem | Matlab | Kya karo |
|---|---|---|
| Swagger me 502 Cloudflare page | Tunnel URL par Swagger khola hai | `localhost:8000/docs` kholo |
| 401 Invalid API key | Swagger/UI me key nahi dali | Section 3: Authorize / sidebar key |
| 409 campaign exists | Naam purana hai | Naya unique campaign_name use karo |
| 502 Live dispatch + Sarvam 401 | Sarvam key galat | Dashboard Settings → API Key verify karo |
| 502 Live dispatch + Sarvam 422 | Agent variables mismatch | Error me jo naam ho, agent me declare karo |
| Call INITIATED me atki | Webhook wapas nahi aaya | Tunnel check karo (Terminal 3 live? URL same?) |
| `/health/ready` me error | DB/Redis down | `docker compose up -d postgres redis` |

---

## 10. Kharcha (yaad rakho)

- ~₹9-10 per 80-sec call (₹4.50/min voice + ₹0.40/min telephony)
- 200 calls/day ≈ ₹1,900/day ≈ ₹50,000/month
- Per-call cost dashboard → Usage page me (per-call split Call logs me)
- Cost ghatana hai to: call chhoti karo (kam questions) + conversion badhao — rate fixed hai

---

## 11. Baad me (jab bologe)

Hosting + domain → production hardening confirm → CRM plug-in (sir permission ke baad) → full login system.
