# Contact email setup for TanCat - research and walkthrough

Written 2026-09-25. Read-only investigation. No DNS was changed, no account was created.
All DNS evidence came from public lookups against the Google resolver 8.8.8.8.

## Status: FAILED (attempt 2026-09-25)

The mailbox was FOUND (see section 1). The setup was NOT completed.

- Zoho Mail still holds only cattanoperations.com. tancat.dev was NOT added.
- hello@tancat.dev is still receive-only (Namecheap eforward). No reply-as.
- Nothing is broken: the site, the forwarding MX records and the existing
  mailbox are all intact (re-verified from DNS after the attempt).

Blocker: the change was guided live from a terminal that cannot receive
screenshots, and copy-paste was not working for the user. The Zoho
verification value is a 47-character string that must be typed exactly, so
blind guidance could not get it into the DNS field reliably. After many
steps the record was still absent from the authoritative Namecheap
nameserver (checked directly, so no cache involved).

Remaining work, when copy-paste or a second pair of hands is available:
1. Add one TXT record on tancat.dev (section 4, Path A, steps 5-7).
2. Click Verify in Zoho.
3. Create hello@tancat.dev and test it.

Interim position: use louis@cattanoperations.com for contact (section 4, Path B).

## 1. Findings

- tancat.dev is LIVE (GitHub Pages, HTTP 200). Its MX records point at Namecheap
  "eforward" servers. eforward only FORWARDS mail. It cannot send mail.
- The roadmap (docs/plans/ROADMAP_ROADTO_PRODUCTION.md, session row 2026-07-31)
  spells the holding domains "cattanooperations" (two o's). That spelling does
  not exist in DNS. The real domains are "cattanoperations" (one o):
  cattanoperations.co.uk and cattanoperations.com both exist and both use
  Namecheap nameservers (so they are the user's).
- cattanoperations.com is hosted by Zoho Mail:
  - SPF: v=spf1 include:zoho.eu ~all
  - TXT: zoho-verification=zb96070062.zmverify.zoho.eu
  - DMARC: v=DMARC1; p=none; rua=mailto:louis@cattanoperations.com
  The DMARC record names a real mailbox: louis@cattanoperations.com.
  So the existing mailbox is on Zoho Mail, on the cattanoperations.com domain.
- cattanoperations.co.uk uses Namecheap eforward (receive-only), same as tancat.dev.
- tancat.dev has no DMARC record and no DKIM record. Neither is needed to receive.

What cannot be seen from DNS (panel-only):
- Where Namecheap eforward sends mail for tancat.dev (the destination address).
- The Zoho plan, the mailbox list, and whether tancat.dev is already added there.

Honest position: the mailbox EXISTS. It is Zoho Mail for cattanoperations.com,
and the address proven by DNS is louis@cattanoperations.com.

## 2. What an MX record is (plain words)

An MX record is a line in DNS that says "send mail for this domain to that
server". Without an MX record, mail to that domain bounces.

## 3. The one decision only the user can make

Receive-only, or send as hello@tancat.dev?

- Receive-only: free. Mail to hello@tancat.dev forwards to a mailbox you read.
  You reply from that mailbox's own address (for example louis@cattanoperations.com).
  The customer sees a different address from the one they wrote to.
- Send as hello@tancat.dev: costs about USD 12 to 19 per year. You read and
  reply as hello@tancat.dev. This matches the landing page and looks correct
  to a buyer.

Recommendation: choose send-as. It is small money, and the landing page already
shows hello@tancat.dev.

## 4. Walkthrough

### Path A - send as hello@tancat.dev (recommended)

Goal: move tancat.dev mail to Zoho Mail, add it to the existing Zoho account as
a domain alias, then create hello@tancat.dev.

Step 1. Log in to the Zoho Mail admin panel for cattanoperations.com.
Why: this is where a domain is added and the plan is upgraded.

Step 2. Check the current plan. If it is the Forever Free plan, note that it
allows ONE domain only. A second domain needs a paid plan.
Why: the free plan cannot hold two domains.

Step 3. Upgrade to Mail Lite. Cost about USD 1 per user per month, paid yearly
(about USD 12 per year for one user). One user is enough.
Why: paid plans allow extra domains and alias domains.

Step 4. Add tancat.dev in Zoho as a domain (or as an alias domain).
Why: this authorises Zoho to hold mail for tancat.dev.

Step 5. In Zoho, open the DNS page for tancat.dev and copy these values:
  MX records (delete any existing MX first):
    mx.zoho.eu    priority 10
    mx2.zoho.eu   priority 20
    mx3.zoho.eu   priority 50
  SPF record (replace the current one):
    v=spf1 include:zoho.eu ~all
  Verification TXT record: copy the exact value Zoho shows
    (shape: zoho-verification=zbNNNNNN.zmverify.zoho.eu)
  DKIM record: copy the exact value Zoho shows
    (host: zoho._domainkey, value starts v=DKIM1; k=rsa; p=...)
Why: MX sends tancat.dev mail to Zoho. SPF says Zoho may send for tancat.dev.
DKIM signs the mail so it does not look forged.

Step 6. At Namecheap (it runs the DNS for tancat.dev), edit the DNS for tancat.dev:
remove the five eforward MX records, then add the Zoho MX, SPF, verification
and DKIM records from Step 5.
Why: Namecheap holds the DNS; Zoho cannot set these for you.

Step 7. Wait for DNS to update (usually under one hour, up to 24 hours), then
click Verify in Zoho.
Why: verification passes only after the records are public.

Step 8. In Zoho, create hello@tancat.dev (an alias on your user, or a mailbox).
Test it: send from a personal account, then reply.
Why: this is the address the landing page already shows.

Step 9. Send a test from hello@tancat.dev to a Gmail address. Check it lands in
the inbox, not spam.
Why: confirms SPF and DKIM are correct.

### Path B - receive-only (free, today's state)

Step 1. Log in to Namecheap. Open Domain List, then tancat.dev, then the
"Email Forwarding" section.
Why: this shows where hello@tancat.dev mail currently goes.

Step 2. Confirm the destination mailbox. If it is empty or wrong, set it to
louis@cattanoperations.com.
Why: mail must land in a mailbox you actually read.

Step 3. Reply to customers from louis@cattanoperations.com, and add a signature
line naming TanCat and hello@tancat.dev.
Why: eforward can receive, but it cannot send as hello@tancat.dev.

## 5. Two provider options if a change is needed

- Zoho Mail Lite: about USD 1 per user per month, paid yearly (about USD 12 per
  year). Keeps one inbox and adds tancat.dev as an alias domain.
- Migadu Micro: USD 19 per year. Unlimited domains and mailboxes, 5 GB shared.

## 6. DNS values, exactly (for a provider change)

- Delete MX: eforward1..5.registrar-servers.com (tancat.dev).
- Add MX: mx.zoho.eu (10), mx2.zoho.eu (20), mx3.zoho.eu (50).
- Replace SPF: v=spf1 include:zoho.eu ~all
- Add DKIM: host zoho._domainkey, value copied from the Zoho panel.
- Optional DMARC: host _dmarc, value v=DMARC1; p=none; rua=mailto:hello@tancat.dev

## 7. Notes for the repo

- Fix the roadmap spelling: "cattanooperations" should be "cattanoperations"
  (ROADMAP_ROADTO_PRODUCTION.md line 1281, 2026-07-31 session row).
- landing/index.html, terms.html and privacy.html already use hello@tancat.dev.
  privacy.html line 63 says "Our email provider stores the mailbox behind
  hello@tancat.dev". That is fully true after Path A. Under Path B it is only
  partly true: Zoho stores cattanoperations.com, and Namecheap forwards tancat.dev.
