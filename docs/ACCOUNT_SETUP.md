# Account setup and outstanding access

Nebius requirements below were documented on 2026-10-23; its key and promotional
credits remain unverified, and troubleshooting is deferred at Frank's request.
Tavily was verified live on 2026-10-24: its existing key is configured in the
server .env (0600), T0.5 passed, and the free-plan counter is 3/1,000 credits used.
Pay-as-you-go and auto-upgrade remain off. No secret value is stored here.

Headroom requires real NVIDIA-model runtime calls through Nebius Token Factory. Its remaining code can run on azuki; an AI Cloud GPU rental is not required. Source: https://nebiusglobalaihackathon.devpost.com/details/faqs

1. Sign in to https://tokenfactory.nebius.com using Google or GitHub.
2. The current billing documentation requires a billing account and bank card during onboarding. It supports negative balances and automatic card charging. We have not confirmed an account-level hard spending cap. Do not assume promotional credits enforce a zero-overspend limit. Source: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new
3. Apply for the hackathon promotional credits via https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 . NEBIUS-DEVPOST-GLOBAL26 is the application activation code; it is not confirmed as a directly redeemable billing code. Check actual received credits in the console.
4. Optional additional Token Factory credit: https://dev.nebius.com/builders . Its terms specify a 90-day validity from issuance: https://nebius.com/builders-terms-and-conditions . The separate hackathon credit expiration has not been verified.
5. Create an API key in the Token Factory console. Store only in server .env (mode 600), not chat, source or reports. Source: https://docs.tokenfactory.nebius.com/api-reference/introduction
6. Tavily is complete: the existing default key was imported by Frank via hidden
   input, and all four real API probes succeeded. See reports/t0.5-acceptance.json.
   No further Tavily signup or key entry is required for this checkpoint.

T0.1 remains incomplete until the Nebius credential is verified and Frank confirms
at least $25 available credit and its spending boundary. Nebius live probes remain
paused. Tavily has a separate completed live acceptance record; its usage does not
prove that Nebius is configured. If billing/country/credits block signup, the official FAQ directs participants to Nebius support: https://discord.com/invite/eXYTGhgnhK .
