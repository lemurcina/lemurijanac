# Revenue Learning Playbook — NextLevel Media LA / Local-Service Vertical

> **Promotion rule:** a lesson appears here only when it is supported by ≥ 2 independent credible sources **or** has been tested with a clear positive outcome, and its falsification condition has not been triggered.  
> See `README.md` for the full governance model.

---

## P-01 — Google Business Profile completeness is a prerequisite for Local Pack visibility

**Sources:**
- Google Search Central — "How Google determines local ranking" (https://support.google.com/business/answer/7091 — updated periodically; verified present Aug 2026)
- Google Business Profile Help — "Complete your Business Profile" (https://support.google.com/business/answer/3038063)

**Lesson:** GBP profiles with complete name, address, phone, categories, hours, photos, and service areas rank higher in the Local Pack than incomplete profiles. This is a documented Google ranking signal, not a practitioner claim.

**Status:** FACT — directly stated in Google's own documentation.

**Confidence:** HIGH

**Relevance:** Every contractor client profile managed or referenced by NextLevel Media LA must be complete before any further acquisition work makes sense.

**Concrete improvement:** Implement a GBP completeness checklist as part of the client onboarding sequence. Block outreach-to-client handoff until all required fields are confirmed filled.

**Falsification / stop condition:** If a fully complete profile consistently fails to appear in Local Pack for core service-area queries after ≥ 90 days without penalty, re-evaluate the impact of completeness relative to other ranking factors.

---

## P-02 — Reducing contact-form friction (fewer required fields) increases conversion rate

**Sources:**
- web.dev — "Sign-in form best practices" (https://web.dev/sign-in-form-best-practices/) — discusses field minimisation and autofill
- Google's "Help users checkout faster with Autofill" (https://web.dev/payment-and-address-form-best-practices/) — confirms fewer mandatory fields reduces drop-off

**Lesson:** FACT — Google's own web.dev guidance explicitly recommends reducing required form fields and enabling autofill to lower submission friction. Applying this to lead-capture / quote-request forms on contractor landing pages is a direct, low-risk, reversible UX improvement.

**Status:** FACT (source), INFERENCE (magnitude of conversion lift without site-specific A/B data)

**Confidence:** HIGH (direction), LOW (exact percentage lift)

**Relevance:** The NextLevel Media LA site's quote-request / contact CTA is the primary lead-intake mechanism.

**Concrete improvement:** Audit the current contact/quote form: require only name + phone (or email) + service type. Remove optional fields from the required list. Enable browser autofill attributes (`autocomplete` on all inputs). A/B test a short form vs the current form if traffic volume permits.

**Falsification / stop condition:** If conversion rate does not increase (or decreases) after ≥ 200 submissions on the shorter form, revisit whether other friction sources dominate.

---

*Additional lessons will be promoted here as evidence accumulates. See daily briefs in `docs/revenue-learning/YYYY-MM-DD.md` files.*
