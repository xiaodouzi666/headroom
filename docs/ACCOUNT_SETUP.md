# Account setup and outstanding access

Nebius billing is active and its server-only private key was previously verified.
Promotional credit was redeemed in the current Token Factory organization on
2026-10-24. At 14:50 UTC, the refreshed Transactions page showed
**Adjustment: AI Builder Program Credits +$30.25 (Incl. tax)** and an account
balance of **$30.25**. Trial credit remained separately listed as **$1 / 29 days**.
This is promotional account credit, not a cash payment or cash balance.
The received promotion had a $25 face value; $25 × 1.21 = $30.25 is consistent
with the official 21% Netherlands VAT rate and the displayed inclusive-tax
adjustment. This arithmetic does not establish an account hard spending cap.
See reports/promo-redemption-20261024.json and the
[official billing documentation](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new).

The original at-least-$25 credit-availability condition is now evidenced.
The earlier $1 trial / $0 cash observation remains historical; it is not the
current promotional balance. Both authenticated directories and minimal
Super/Nano calls had already succeeded; preserve their separate evidence in
reports/tokenfactory-minimal-20261024.json. The same account's default project
still lists the existing headroom-azuki key. Redemption created no new key,
performed no card recharge, and made no additional inference call.
Tavily was verified live on 2026-10-24: its existing key is configured in the
server .env (0600), T0.5 passed, and the free-plan counter is 6/1,000 credits used after the real Research component check (994 remain).
See reports/tavily-account-after-research-20261024.json.
Pay-as-you-go and auto-upgrade remain off. No secret value is stored here.

Headroom requires real NVIDIA-model runtime calls through Nebius Token Factory. Its remaining code can run on azuki; an AI Cloud GPU rental is not required. Source: https://nebiusglobalaihackathon.devpost.com/details/faqs

1. Sign in to https://tokenfactory.nebius.com using Google or GitHub.
2. The current billing documentation requires a billing account and bank card during onboarding. It supports negative balances and automatic card charging. We have not confirmed an account-level hard spending cap. Do not assume promotional credits enforce a zero-overspend limit. Source: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new
3. Original hackathon application route (completed for the received promotion; no repeat application is needed): https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 . NEBIUS-DEVPOST-GLOBAL26 is the application activation code; it is not confirmed as a directly redeemable billing code. Check actual received credits in the console.
4. Optional additional Token Factory credit: https://dev.nebius.com/builders . The previously consulted general terms specify a 90-day validity from issuance: https://nebius.com/builders-terms-and-conditions . Keep those generic terms separate from the specific received promotion email recorded below; do not apply a generic expiry assumption to the redeemed balance.
5. Create an API key in the Token Factory console. Store only in server .env (mode 600), not chat, source or reports. Source: https://docs.tokenfactory.nebius.com/api-reference/introduction
6. Tavily is complete: the existing default key was imported by Frank via hidden
   input, and all four real API probes succeeded. See reports/t0.5-acceptance.json.
   No further Tavily signup or key entry is required for this checkpoint.

T0.1's account/key/repository/credit gates are now accepted; see
reports/t0.1-acceptance-promo-20261024.json. The separate full-campaign spending
boundary remains unapproved. The previous $0.10 trial-connectivity authorization
covered the two completed minimal calls; it does not authorize recharge or the
full capability/repair evaluation. A new proposed checkpoint of at most three
single calls, $1.25 in token charges and a $2 total envelope including tax reserve,
has been presented for explicit approval and is still pending as of this
reconciliation. Promotional redemption does not grant additional inference
authorization. Tavily has a separate completed live acceptance record; its usage
does not prove Nebius model capabilities. If billing/country/credits block signup,
the official FAQ directs participants to Nebius support: https://discord.com/invite/eXYTGhgnhK .

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

The owner's request to switch to promotional credit when it arrived has been
carried out by redeeming the received promotion in the existing organization.
The promotion email states a redemption deadline of 2026-12-31 and says redeemed
credits do not expire. These are recorded terms from that specific email, not a
general promise about other offers. The transaction and refreshed account balance,
rather than the email alone, establish that credit was posted.

Preserve the earlier account snapshots and spend records. Refresh the same
account's available promotional balance before any newly authorized dispatch;
no provider switch, new key or recharge is needed for this checkpoint.
The full runtime profile remains closed/absent, and the proposed checkpoint and
full-campaign spending boundaries still require their own explicit authorization.
No automatic recharge or additional spending was enabled by redemption.
