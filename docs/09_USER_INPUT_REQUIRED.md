# User Input Required

**Date:** 2026-09-21

---

## NEEDED NOW (Before Development)

### 1. Sarvam Account Access
- [ ] Sarvam account created at https://dashboard.sarvam.ai/
- [ ] API key generated
- [ ] Organization ID noted
- [ ] Workspace ID noted

**Where to get it:**
- Sign up at https://dashboard.sarvam.ai/
- Go to Settings -> API Key
- Copy Organization ID and Workspace ID from dashboard URL or Settings

**Why needed:**
- API authentication for all Sarvam calls
- Identifies your account and workspace

---

### 2. Sarvam Voice Agent
- [ ] Agent created in Sarvam dashboard
- [ ] Agent published (not just draft)
- [ ] App ID noted
- [ ] App Version noted

**Where to get it:**
- Go to Build -> Create Agent
- Design agent for real-estate lead qualification
- Publish the agent
- Copy App ID and Version from Deploy page

**Why needed:**
- The agent handles the actual conversation with leads
- App ID identifies which agent places calls

---

### 3. Telephony Connection
- [ ] Connection configured (Exotel, Twilio, or Rent from Sarvam)
- [ ] Connection ID noted
- [ ] Indian phone number obtained
- [ ] Phone number in E.164 format

**Where to get it:**
- Go to Deploy -> Phone Numbers
- Add Connection (or use "Rent from Sarvam")
- Copy Connection ID
- Note the agent phone number

**Why needed:**
- Connection provides the telephony infrastructure
- Phone number is the outbound caller ID

---

### 4. Webhook URL
- [ ] Public HTTPS URL available
- [ ] URL accessible from internet

**Where to get it:**
- Option A: Cloudflare Tunnel (free)
  ```bash
  cloudflared tunnel --url http://localhost:8000
  ```
- Option B: ngrok (free tier)
  ```bash
  ngrok http 8000
  ```
- Option C: Production domain with SSL

**Why needed:**
- Sarvam sends call status updates to this URL
- Without it, we cannot track call outcomes

---

## NEEDED LATER (Before First Real Call)

### 5. Agent Configuration
- [ ] Agent persona (name, company, role)
- [ ] System prompt for qualification flow
- [ ] Agent variables defined
- [ ] Language support configured (Hindi/English/Hinglish)
- [ ] Voice selected

**Example agent variables:**

Input variables (pass from our system):
```
customer_name: string
city: string
requirement: string
budget: string
timeline: string
```

Output variables (Sarvam extracts during call):
```
qualification_status: string
interested: boolean
budget_collected: string
timeline_collected: string
callback_requested: boolean
appointment_requested: boolean
```

---

### 6. Business Rules
- [ ] Qualification criteria defined
- [ ] Callback scheduling rules
- [ ] Site visit scheduling rules
- [ ] Objection handling approach
- [ ] Do Not Call list handling

---

## What I Will Provide (Development)

During development, I will:
- Create SarvamCallingProvider
- Create webhook handler
- Create enrichment logic
- Update configuration
- Write tests
- Update documentation

**I need you to:**
1. Create Sarvam account and get credentials
2. Create and publish voice agent
3. Configure telephony connection
4. Set up webhook URL
5. Provide all credentials in .env

---

## Credential Template

Please fill this and provide:

```
SARVAM_API_KEY=_________________
SARVAM_ORG_ID=_________________
SARVAM_WORKSPACE_ID=_________________
SARVAM_APP_ID=_________________
SARVAM_APP_VERSION=1
SARVAM_CONNECTION_ID=_________________
SARVAM_AGENT_PHONE_NUMBER=+91___________
PUBLIC_BASE_URL=_________________
```

---

## Timeline

| Step | What | Who | When |
|------|------|-----|------|
| 1 | Create Sarvam account | You | Now |
| 2 | Get API credentials | You | Now |
| 3 | Create voice agent | You | Now |
| 4 | Configure telephony | You | Now |
| 5 | Set up webhook URL | You | Now |
| 6 | Provide credentials | You | Before Phase 2 |
| 7 | Build Sarvam provider | Me | After step 6 |
| 8 | Build webhook handler | Me | After step 6 |
| 9 | Build enrichment | Me | After step 6 |
| 10 | Test with mock | Me + You | After step 9 |
| 11 | First real call | You (GO) | After step 10 |
