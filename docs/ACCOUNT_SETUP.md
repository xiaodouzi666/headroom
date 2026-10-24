# Account setup and outstanding access

Nebius billing is now active and its server-only private key has been verified.
On2026-10-24 the account displayed1USD trial credit and zero cash balance. Both
authenticated directories and minimal Super/Nano calls succeeded. Promotional
credits and the original at-least25USD gate remain pending; see
reports/tokenfactory-minimal-20261024.json.
Tavily was verified live on 2026-10-24: its existing key is configured in the
server .env (0600), T0.5 passed, and the free-plan counter is 6/1,000 credits used after the real Research component check (994 remain).
See reports/tavily-account-after-research-20261024.json.
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

T0.1 remains incomplete until at least25USD available credit and the full-campaign
spending boundary are confirmed. The current authorization covers only0.10USD
from trial credit for minimal connectivity; it does not authorize recharge or
the full capability/repair evaluation. Two minimal calls have completed. Tavily has a separate completed live acceptance record; its usage does not
prove that Nebius is configured. If billing/country/credits block signup, the official FAQ directs participants to Nebius support: https://discord.com/invite/eXYTGhgnhK .

## Self-funding versus promotional approval

Checked against official Token Factory billing/quickstart on 2026-10-24. If only Builders or hackathon promotional-credit approval is pending, normal paid Token Factory onboarding can be used independently: activate the billing account, obtain an API key and fund usage. The documentation says manual top-ups become available immediately; it does not establish that payment bypasses account-level review or eligibility restrictions.

No recharge was authorized or performed by the question about feasibility. Current billing allows negative balances and automatically charges the card at the configured threshold or at the next monthly settlement. A $25 top-up is not a $25 account spending cap. The project also requires explicit per-run/daily/total spending boundaries and reviewed real model/pricing evidence before paid inference.

Sources: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new and https://docs.tokenfactory.nebius.com/quickstart . No minimum top-up amount was verified; use the actual console amount.

## Prepared hidden-input importer on azuki

Once an existing Token Factory API key is available, the owner can run:

```sh
ssh -t -p 40022 xiaodouzi@azuki.ubj.ink 'python3 /home/xiaodouzi/workspace/headroom/.cache/setup/import_nebius_key.py'
```

Input is hidden and the key is never printed. This server-only ignored helper refuses to overwrite an existing key or write to a nonregular/nonprivate `.env`, preserves the Tavily entry and writes atomically with mode0600. The owner has used it and the resulting private key authenticated both model directories and two minimal calls. Credential presence alone does not verify service access, model availability, balance, or spending authorization. The helper does not create a key, top up an account or call the API.


## Promotional credit continuation

The owner requested using promotional credit once it arrives. Reconcile actual
credit availability and expiration in this same Token Factory account; neither a
new provider nor another API key is implied. Preserve existing spend records and
get a sufficient explicit campaign authorization before the original full probes
and repair evaluations. A pending application or promotional email is not proof
of credited balance. No automatic recharge or additional spending is enabled.
