"""Synthetic knowledge base for the fictional NovaCRM platform (12 documents,
mirroring the paper's §3.1 topical clusters). Facts are invented."""

NOVACRM_DOCS: dict[str, str] = {
"company_overview.md": """# NovaCRM Company Overview

NovaCRM is an AI-powered customer relationship management platform founded in 2019 and headquartered in Austin, Texas. The company has 420 employees and serves more than 8,000 customers in 40 countries, from startups to Fortune 500 enterprises.

NovaCRM's mission is to make every customer conversation smarter. The platform combines contact management, deal pipelines, and an AI assistant called Nova that drafts emails, summarizes calls, and predicts which deals are likely to close.

The company is led by CEO Dana Whitfield and CTO Marcus Oyelaran. NovaCRM raised a 120 million dollar Series C in 2024. Customer support is available 24 hours a day on weekdays and 9am to 5pm Central on weekends. The company is SOC 2 Type II certified and operates data centers in the United States, Germany, and Singapore.""",

"product_features.md": """# NovaCRM Product Features

Contact Management: NovaCRM stores contacts, companies, and activity history in one timeline. Duplicate detection merges records automatically, and custom fields support up to 200 attributes per contact.

Deal Pipelines: Teams build multiple pipelines with customizable stages. Each deal shows probability, expected close date, and next steps. Drag-and-drop boards and forecasting reports are included in every plan.

Nova AI Assistant: Nova drafts follow-up emails, summarizes meeting transcripts, scores leads from 0 to 100, and recommends the next best action. Lead scoring uses engagement, firmographics, and deal history.

Workflow Automation: Visual workflow builder triggers actions such as assigning owners, sending sequences, or creating tasks when a deal changes stage. Reporting and Dashboards: Over 60 prebuilt reports, a drag-and-drop dashboard builder, and scheduled report delivery by email. Mobile Apps: iOS and Android apps support offline access and voice notes.""",

"pricing_plans.md": """# NovaCRM Pricing Plans

Starter: 19 dollars per user per month billed annually, or 25 dollars billed monthly. Includes contact management, one pipeline, basic reports, and email support. Limited to 5,000 contacts and 10 users.

Professional: 59 dollars per user per month billed annually, or 75 dollars billed monthly. Includes unlimited pipelines, workflow automation, Nova AI assistant with 500 AI actions per user per month, and the REST API with 100,000 calls per month.

Enterprise: Custom pricing, typically starting at 120 dollars per user per month with a 25 user minimum. Includes unlimited AI actions, single sign-on, audit logs, a dedicated customer success manager, a 99.95 percent uptime SLA, and premium 24/7 support.

Discounts: Annual billing saves about 20 percent. Nonprofits and educational institutions receive 30 percent off any plan. Volume discounts start at 100 seats. All paid plans include a 14-day free trial with no credit card. Add-ons: extra AI actions cost 10 dollars per 1,000, and additional API calls cost 5 dollars per 100,000.""",

"api_overview.md": """# NovaCRM API Overview

The NovaCRM REST API lets you read and write CRM data programmatically. The base URL is https://api.novacrm.example/v2. All responses are JSON and all requests must use HTTPS.

Authentication: Use an API key in the Authorization header as a Bearer token, or use OAuth 2.0 authorization code flow for apps acting on behalf of users. API keys are created under Settings, then Developers.

Rate limits: Professional plans allow 100 requests per minute and Enterprise plans allow 1,000 requests per minute. Exceeding the limit returns HTTP 429 with a Retry-After header.

Pagination: List endpoints use cursor pagination with a limit parameter up to 100 and a next_cursor field. Errors follow a consistent format with a code, message, and request_id. Webhooks: Subscribe to events such as contact.created, deal.updated, and deal.won; payloads are signed with an HMAC-SHA256 signature in the X-Nova-Signature header. Official SDKs exist for Python, JavaScript, and Go.""",

"api_contacts.md": """# Contacts API

GET /v2/contacts returns a paginated list of contacts. Filter with query parameters such as email, company_id, owner_id, and updated_since.

POST /v2/contacts creates a contact. Required fields are first_name and email. Optional fields include phone, title, company_id, and custom_fields, an object of key value pairs. A successful request returns 201 with the new contact object.

GET /v2/contacts/{id} retrieves one contact. PATCH /v2/contacts/{id} updates only the fields you send. DELETE /v2/contacts/{id} soft deletes a contact, which can be restored for 30 days.

POST /v2/contacts/bulk accepts up to 500 contacts per request and returns a job_id; poll GET /v2/jobs/{job_id} for results. Duplicate emails return a 409 conflict error with the existing contact id. Search: GET /v2/contacts/search takes a q parameter for full-text search across names, emails, and notes.""",

"api_deals.md": """# Deals API

GET /v2/deals lists deals. Filter by pipeline_id, stage, owner_id, status (open, won, lost), and min_amount.

POST /v2/deals creates a deal. Required fields are name, pipeline_id, and stage_id. Optional fields are amount, currency, contact_ids, expected_close_date, and custom_fields. Amounts are integers in the smallest currency unit, such as cents.

PATCH /v2/deals/{id} updates a deal. Moving a deal to a new stage is done by setting stage_id, which fires the deal.updated webhook. POST /v2/deals/{id}/won marks a deal won and records the close date; POST /v2/deals/{id}/lost requires a lost_reason.

GET /v2/pipelines returns pipelines and their stages. GET /v2/deals/{id}/forecast returns the Nova AI win probability and the factors behind it. Deleting a deal with DELETE is permanent and requires the deals:delete scope.""",

"integrations.md": """# NovaCRM Integrations

NovaCRM offers more than 150 integrations. Email and Calendar: Gmail, Outlook, and Microsoft 365 sync email and meetings two ways, and every message is attached to the right contact.

Communication: Slack posts deal alerts to channels, Microsoft Teams supports meeting logging, and Zoom automatically uploads recordings for Nova to summarize. Marketing: HubSpot, Mailchimp, and Marketo sync lists and campaign engagement.

Finance: QuickBooks and Stripe sync invoices and payment status to deals. Productivity: Google Drive, Dropbox, and Notion link documents to records. Data: Snowflake and BigQuery connectors export CRM tables nightly on Enterprise plans.

Zapier and Make provide no-code connections to over 5,000 apps. Salesforce Migration: a guided importer maps Salesforce objects and fields to NovaCRM, usually completing for 100,000 records in under an hour. Custom integrations can be built with the REST API and webhooks.""",

"security_compliance.md": """# Security and Compliance

Certifications: NovaCRM is SOC 2 Type II and ISO 27001 certified. It supports HIPAA compliance with a signed Business Associate Agreement on Enterprise plans, and is GDPR and CCPA compliant.

Encryption: Data is encrypted in transit with TLS 1.3 and at rest with AES-256. Enterprise customers can bring their own encryption keys through a customer managed key service.

Access control: Role-based permissions, field-level security, and IP allowlisting are available. Single sign-on supports SAML 2.0 with Okta, Azure AD, and Google Workspace, and SCIM provisioning automates user lifecycle. Two-factor authentication is mandatory for administrators.

Data residency: Customers choose United States, European Union, or Singapore regions. Audit logs record every login, export, and permission change and are retained for 365 days. Backups run every hour with 35 day retention, and the recovery time objective is 4 hours. Annual third party penetration tests are available under NDA.""",

"onboarding_guide.md": """# Onboarding Guide

Step 1, create your workspace: Sign up, name your workspace, and invite teammates by email. Administrators can assign roles of Admin, Manager, or Rep.

Step 2, import your data: Upload a CSV of contacts and companies, or connect another CRM. The importer previews field mapping and flags duplicates before anything is saved.

Step 3, build your pipeline: Start from a template such as Sales, Recruiting, or Customer Success, then rename stages to match your process.

Step 4, connect email and calendar so activity is logged automatically. Step 5, turn on Nova AI, which needs about 50 historical deals to begin scoring accurately. Step 6, set up your first workflow automation.

Most teams finish setup in two to three days. Free live training webinars run every Tuesday and Thursday, and Enterprise customers receive a dedicated onboarding specialist for 30 days.""",

"troubleshooting.md": """# Troubleshooting Guide

Emails not syncing: Reconnect the mailbox under Settings, Integrations, and confirm the OAuth permission to read mail was granted. Sync usually resumes within 5 minutes. A banner with error EMAIL_401 means the token expired.

Import failures: Error IMPORT_422 means a required column such as email is missing or malformed. Files must be UTF-8 CSV under 50 MB; split larger files.

API errors: 401 means the API key is invalid or revoked, 403 means missing scope, 404 means the record does not exist, and 429 means rate limit exceeded; wait for the Retry-After seconds. Webhook deliveries that fail are retried 5 times over 24 hours.

Slow dashboards: Reports with more than 1 million rows can take 30 seconds; add date filters. Login problems: use Forgot Password, and if SSO fails check that the identity provider certificate has not expired. Nova AI scores missing: the feature requires at least 50 closed deals. Contact support with the request_id from the error.""",

"faq.md": """# Frequently Asked Questions

Can I try NovaCRM before buying? Yes, every paid plan has a 14-day free trial with no credit card required.

Can I cancel anytime? Monthly plans cancel at any time. Annual plans are non-refundable after 30 days but can be downgraded at renewal.

How do I export my data? Admins can export all records as CSV or JSON under Settings, Data, Export. Enterprise plans can schedule automatic exports.

Is there a mobile app? Yes, for iOS and Android, with offline mode and voice notes.

Does NovaCRM support multiple currencies? Yes, over 130 currencies with daily exchange rate updates. Which languages are supported? The interface is available in 12 languages including English, Spanish, German, French, and Japanese.

How many users can share a workspace? Starter allows 10, while Professional and Enterprise are unlimited. Who owns my data? You do; NovaCRM never sells customer data or uses it to train models for other customers.""",

"release_notes.md": """# Release Notes

Version 4.2, released March 2026: Nova AI call summaries now support 14 languages. New deal forecast explanations show the top five factors behind win probability. The Contacts API gained a bulk endpoint accepting 500 records per request.

Version 4.1, released January 2026: Added Microsoft Teams integration and a redesigned mobile app with offline voice notes. Dashboard load time improved by 40 percent. Fixed a bug where duplicate detection merged contacts with shared phone numbers.

Version 4.0, released October 2025: Introduced the visual workflow builder, SCIM provisioning, and customer managed encryption keys for Enterprise. The REST API moved to v2 with cursor pagination; v1 will be retired in December 2026.

Version 3.9, released July 2025: Launched Snowflake and BigQuery export connectors, the Salesforce guided importer, and webhook signature verification using HMAC-SHA256. Upcoming: email sequence A/B testing and a public marketplace for third party apps.""",
}
