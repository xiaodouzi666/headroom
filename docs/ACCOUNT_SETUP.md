# Account setup and outstanding access

Checked 2026-10-23. This documents account requirements; no account or billing setup was performed.

Headroom requires real NVIDIA-model runtime calls through Nebius Token Factory. Its remaining code can run on azuki; an AI Cloud GPU rental is not required. Source: https://nebiusglobalaihackathon.devpost.com/details/faqs

1. Sign in to https://tokenfactory.nebius.com using Google or GitHub.
2. The current billing documentation requires a billing account and bank card during onboarding. It supports negative balances and automatic card charging. We have not confirmed an account-level hard spending cap. Do not assume promotional credits enforce a zero-overspend limit. Source: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new
3. Apply for the hackathon promotional credits via https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 . NEBIUS-DEVPOST-GLOBAL26 is the application activation code; it is not confirmed as a directly redeemable billing code. Check actual received credits in the console.
4. Optional additional Token Factory credit: https://dev.nebius.com/builders . Its terms specify a 90-day validity from issuance: https://nebius.com/builders-terms-and-conditions . The separate hackathon credit expiration has not been verified.
5. Create an API key in the Token Factory console. Store only in server .env (mode 600), not chat, source or reports. Source: https://docs.tokenfactory.nebius.com/api-reference/introduction
6. Obtain a Tavily key at https://tavily.com and store in the same .env file. No secret values belong in this document.

T0.1 remains incomplete until the credentials are verified and Frank confirms at least $25 credit. Live probes remain paused pending a confirmed spending boundary. No API usage or account setup has been performed here. If billing/country/credits block signup, the official FAQ directs participants to Nebius support: https://discord.com/invite/eXYTGhgnhK .
