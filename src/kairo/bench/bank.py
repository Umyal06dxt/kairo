"""Real-world direction: a voice support line for a (fictional) credit union.

Harbor Federal Credit Union is invented; all rates, fees and phone numbers are made up for
evaluation. Support calls follow predictable chains (lost card -> freeze -> fraud -> credit ->
replacement), which is exactly the structure speculative prefetching can exploit. Every scripted
turn carries gold facts (`expect`) and the source document, so we can measure *answer
correctness* and *evidence recall*, not just cache hit rate."""

from .domains import Domain, Turn

BANK_DOCS: dict[str, str] = {
"accounts_overview.md": """# Harbor Federal Credit Union - Accounts

Everyday Checking has no monthly fee, a 25 dollar minimum opening deposit, and no minimum balance. It includes a free debit card and access to more than 30,000 surcharge-free ATMs.

Premier Checking costs 12 dollars per month. The fee is waived with a 5,000 dollar combined balance or 2,500 dollars in monthly direct deposits. It earns 0.50 percent APY and rebates up to 20 dollars per month in other banks' ATM fees.

Share Savings needs only a 5 dollar minimum and earns 0.75 percent APY. High-Yield Savings earns 4.10 percent APY with a 1,000 dollar minimum balance and allows up to six withdrawals per month.

Certificates of deposit: the 12-month certificate earns 4.50 percent APY and the 24-month certificate earns 4.25 percent APY. Withdrawing early costs 180 days of interest. Youth Savings is available for members under 18 with a joint owner.""",

"fees_schedule.md": """# Fee Schedule

Overdraft fee: 30 dollars per item, with a maximum of three overdraft fees per day. There is no fee if the account is overdrawn by less than 10 dollars. Overdraft protection, which automatically transfers money from your savings account, costs 5 dollars per transfer. A returned item for non-sufficient funds also costs 30 dollars.

Using an ATM outside the surcharge-free network costs 3 dollars plus whatever the ATM owner charges. Premier Checking members get up to 20 dollars per month back.

Wire fees: incoming wires cost 15 dollars, outgoing domestic wires cost 25 dollars, and outgoing international wires cost 45 dollars.

Other fees: a stop payment costs 20 dollars. Paper statements cost 3 dollars per month; electronic statements are free. A replacement debit card costs 10 dollars, and is free when the replacement is due to fraud. Overnight rush delivery of a card costs 30 dollars. Monthly fees are 0 dollars for Everyday Checking and 12 dollars for Premier Checking.""",

"debit_cards.md": """# Debit Cards

Activate a new card in the mobile app, at any Harbor ATM with your PIN, or by calling 1-800-555-0142. New and replacement cards arrive in 7 to 10 business days. Everyday and Premier Checking members can also add an instant digital card to their phone wallet within minutes in the app.

Daily limits: ATM withdrawals are limited to 600 dollars and purchases to 3,000 dollars. In the app you can temporarily raise these to 1,500 dollars for ATM and 5,000 dollars for purchases for up to 3 days.

Freeze or unfreeze a card instantly in the app under Cards, then Freeze. A frozen card declines new purchases but recurring payments you already set up may still process.

Travel: a travel notice is recommended but not required. International transactions are off by default and can be turned on in the app under Cards. A 1 percent foreign transaction fee applies to debit card purchases made abroad.""",

"lost_stolen_fraud.md": """# Lost, Stolen Cards and Fraud

If you lose your card or see a charge you do not recognize, freeze the card in the app right away and call the 24 hour fraud line at 1-800-555-0199. The fraud line is open every day, all day.

Zero liability: you pay nothing for unauthorized debit card transactions that you report within 60 days of the statement date showing them.

While we investigate, you receive a provisional credit within 10 business days. Investigations usually take up to 45 days, or up to 90 days for new accounts, point-of-sale, or foreign transactions.

A compromised card is closed and replaced with a new number. Replacement cards due to fraud are free and arrive in 7 to 10 business days, or you can use an instant digital card in the app. After the new card is issued, update any recurring payments such as subscriptions and utility bills; our card updater service refreshes many merchants automatically. Fraud alerts arrive by text message: reply YES if the transaction is yours and NO if it is not.""",

"disputes_chargebacks.md": """# Disputes and Chargebacks

You must report a disputed transaction within 60 days of the statement date on which it first appeared.

To dispute in the app, open Transactions, select the charge, and tap Dispute. Have the merchant name, date, amount, a description of the problem, and what you did to try to resolve it with the merchant.

We contact the merchant and decide the dispute within 45 days. You receive a provisional credit within 10 business days while the case is open.

Subscriptions: if you canceled a subscription and were still charged, dispute the charge and attach proof of cancellation such as a confirmation email. Disputes are not available for purchases you authorized where you received the goods or services as described. Disputes on credit card charges follow the same 60 day window.""",

"online_mobile_banking.md": """# Online and Mobile Banking

Enroll at harborfcu.example/enroll using your account number, the last four digits of your Social Security number, and your email address.

Forgot password: tap Forgot Password and we send a 6-digit code to your phone, which is valid for 10 minutes. After 5 failed sign-in attempts the profile locks for 30 minutes, or you can unlock it right away by verifying your identity in the app or calling 1-800-555-0142. Multi-factor authentication is required and works with an authenticator app or text message.

Mobile check deposit: new members can deposit up to 5,000 dollars per day and 10,000 dollars per month. Funds are available the next business day. Endorse the check with For mobile deposit only and your signature.

HarborSend person-to-person payments are limited to 1,000 dollars per day and 5,000 dollars per month. Bill pay is free.""",

"transfers_wires.md": """# Transfers and Wires

Transfers between your Harbor accounts are instant. ACH transfers to accounts at other banks take 1 to 3 business days. Same-day ACH is available if you submit before the 1:00 pm Eastern cutoff. The ACH limit is 10,000 dollars per day online.

Domestic wires sent before the 4:00 pm Eastern cutoff are sent the same business day. International wires must be submitted before 2:00 pm Eastern and take 1 to 5 business days. For an international wire you need the recipient's full name and address, account number, and the bank's SWIFT or BIC code.

The online wire limit is 50,000 dollars per day; higher amounts can be sent at a branch. A wire cannot be reversed or recalled once it is sent, so verify the details carefully. For wires above 10,000 dollars we make a call-back to verify the request before sending.""",

"loans_auto_personal.md": """# Auto and Personal Loans

New car loans start at 5.49 percent APR and used car loans start at 6.19 percent APR. Terms run from 36 to 84 months. Preapproval takes only a few minutes online and stays valid for 60 days. You can finance up to 100 percent of the value of a new vehicle. There is no prepayment penalty on auto loans. A credit score of about 640 or higher is typical for the best rates.

Personal loans range from 1,000 to 35,000 dollars with rates from 8.99 to 17.99 percent APR and terms of 12 to 60 months. There is no origination fee. Approved funds are deposited the same or next business day.

Autopay from a Harbor checking account earns a 0.25 percent rate discount on any loan. Skip-a-payment is available once per year on auto loans for a 25 dollar fee.""",

"mortgages_heloc.md": """# Mortgages and HELOC

The 30-year fixed mortgage is currently 6.38 percent APR and the 15-year fixed is 5.65 percent APR. First-time homebuyers can put down as little as 3 percent; the standard minimum down payment is 5 percent. Private mortgage insurance applies when you put down less than 20 percent. The minimum credit score is 620.

Mortgage preapproval takes 24 to 48 hours. Closing usually takes 30 to 45 days from the signed purchase contract. Closing costs typically run 2 to 5 percent of the loan amount.

A home equity line of credit, or HELOC, has a variable rate of prime plus 0.50 percent. You can borrow up to 85 percent of your home's value minus what you owe. The draw period is 10 years followed by a 20 year repayment period. There is no annual fee for the first year.""",

"credit_cards.md": """# Credit Cards

Harbor Cash Rewards earns 1.5 percent cash back on every purchase and 3 percent on gas and groceries, with a 15.99 to 24.99 percent variable APR and no annual fee. There is no foreign transaction fee.

Balance transfers carry a 0 percent introductory APR for 15 months with a 3 percent transfer fee. The grace period on purchases is 25 days when you pay the full statement balance. The late payment fee is up to 30 dollars.

You can request a credit limit increase online every 6 months. Lost credit cards can be frozen in the app and reported on the same 24 hour fraud line, 1-800-555-0199. Disputed credit card charges follow the same 60 day rule as debit cards.""",

"branches_contact.md": """# Branches, Hours and Contact

Harbor FCU has 14 branches across Maryland and northern Virginia, with headquarters in Baltimore. Branch lobbies are open Monday through Friday from 9 am to 5 pm and Saturday from 9 am to 1 pm. Drive-through lanes stay open until 6 pm on weekdays. All branches are closed on Sundays and federal holidays.

Phone support at 1-800-555-0142 is open Monday through Friday from 7 am to 9 pm Eastern and Saturday from 8 am to 4 pm Eastern. The fraud line, 1-800-555-0199, is open 24 hours a day.

Safe deposit boxes start at 35 dollars per year. Notary service is free for members.""",

"membership_security.md": """# Membership and Security

Anyone who lives, works, worships, or attends school in Maryland, Washington DC, or northern Virginia can join. Relatives of members can also join, and so can anyone who joins the Harbor Maritime Association for a one-time 10 dollar fee.

To join you make a 5 dollar membership share deposit into Share Savings and provide a government photo ID, your Social Security number, and proof of address. Online applications take about 10 minutes. Joint accounts are allowed, and members under 18 need an adult joint owner.

Deposits are insured by the NCUA up to 250,000 dollars per depositor. Harbor will never ask for your PIN or full password by phone, text, or email. Forward suspicious emails to the phishing report address. Biometric sign-in and instant transaction alerts are available in the app. We never sell member data.""",
}

T = Turn
BANK_SCENARIOS: dict[str, list[Turn]] = {
"B1 Lost debit card": [
    T("I think I lost my debit card, what should I do?", ("freeze", "0199"), "lost_stolen_fraud.md"),
    T("How do I freeze it in the app?", ("cards", "freeze"), "debit_cards.md"),
    T("What is the fraud line number?", ("0199",), "lost_stolen_fraud.md"),
    T("Am I responsible for charges I didn't make?", ("zero|not|nothing|no liab",), "lost_stolen_fraud.md"),
    T("How long until I get a provisional credit?", ("10",), "lost_stolen_fraud.md"),
    T("How long does the investigation take?", ("45",), "lost_stolen_fraud.md"),
    T("How soon will my replacement card arrive?", ("7|seven",), "lost_stolen_fraud.md"),
    T("Is there a fee for the replacement card?", ("free|no fee|no charge|10",), "fees_schedule.md"),
    T("Can I get a digital card right away?", ("app|wallet|minutes",), "debit_cards.md"),
    T("Do I need to update my recurring payments?", ("update|recurring",), "lost_stolen_fraud.md")],
"B2 Fees": [
    T("What's the overdraft fee?", ("30",), "fees_schedule.md"),
    T("Is there a limit on how many overdraft fees per day?", ("three|3",), "fees_schedule.md"),
    T("Is there any fee if I'm only overdrawn by a few dollars?", ("10|no fee|less than",), "fees_schedule.md"),
    T("What does overdraft protection from savings cost?", ("5",), "fees_schedule.md"),
    T("How much is it to use an out of network ATM?", ("3",), "fees_schedule.md"),
    T("What's the fee for an outgoing domestic wire?", ("25",), "fees_schedule.md"),
    T("And an international wire?", ("45",), "fees_schedule.md"),
    T("How much is a stop payment?", ("20",), "fees_schedule.md"),
    T("Do you charge for paper statements?", ("3",), "fees_schedule.md"),
    T("What is the monthly fee on Premier Checking?", ("12",), "accounts_overview.md")],
"B3 Joining the credit union": [
    T("Who is eligible to join?", ("live|work|worship|school",), "membership_security.md"),
    T("How much does it cost to become a member?", ("5",), "membership_security.md"),
    T("What documents do I need to join?", ("id",), "membership_security.md"),
    T("How long does the online application take?", ("10",), "membership_security.md"),
    T("Can I open a joint account?", ("yes|allowed|joint",), "membership_security.md"),
    T("What about my teenage daughter?", ("adult|joint|18",), "membership_security.md"),
    T("Are my deposits insured?", ("250,000|250000",), "membership_security.md"),
    T("What's the minimum to open Everyday Checking?", ("25",), "accounts_overview.md"),
    T("What's the rate on your high yield savings?", ("4.10|4.1",), "accounts_overview.md"),
    T("And the twelve month certificate?", ("4.50|4.5",), "accounts_overview.md")],
"B4 Car loan": [
    T("What are your auto loan rates for a new car?", ("5.49",), "loans_auto_personal.md"),
    T("And for a used car?", ("6.19",), "loans_auto_personal.md"),
    T("What loan terms can I choose?", ("36", "84"), "loans_auto_personal.md"),
    T("Can I get preapproved online?", ("yes|minutes|online|preapprov",), "loans_auto_personal.md"),
    T("How long does the preapproval last?", ("60",), "loans_auto_personal.md"),
    T("Is there a prepayment penalty?", ("no|not|none",), "loans_auto_personal.md"),
    T("What credit score do I need?", ("640",), "loans_auto_personal.md"),
    T("Do you also offer personal loans?", ("yes|personal|1,000|35,000",), "loans_auto_personal.md"),
    T("What are the personal loan rates?", ("8.99",), "loans_auto_personal.md"),
    T("How fast would I get the money?", ("same|next",), "loans_auto_personal.md")],
"B5 Buying a home": [
    T("What is your thirty year mortgage rate?", ("6.38",), "mortgages_heloc.md"),
    T("And the fifteen year?", ("5.65",), "mortgages_heloc.md"),
    T("How much do I need for a down payment?", ("5",), "mortgages_heloc.md"),
    T("I'm a first time buyer, is it lower?", ("3",), "mortgages_heloc.md"),
    T("Will I need mortgage insurance?", ("20|insurance|pmi",), "mortgages_heloc.md"),
    T("How fast can I get preapproved?", ("24", "48"), "mortgages_heloc.md"),
    T("How long does closing take?", ("30", "45"), "mortgages_heloc.md"),
    T("What are typical closing costs?", ("2", "5"), "mortgages_heloc.md"),
    T("Do you offer a home equity line of credit?", ("yes|heloc|equity|prime",), "mortgages_heloc.md"),
    T("How long is the HELOC draw period?", ("10",), "mortgages_heloc.md")],
"B6 Locked out of online banking": [
    T("My online banking account is locked, why?", ("5|five|failed",), "online_mobile_banking.md"),
    T("How long does the lock last?", ("30",), "online_mobile_banking.md"),
    T("Can I unlock it faster?", ("verify|call|app",), "online_mobile_banking.md"),
    T("How do I reset my password?", ("code|forgot",), "online_mobile_banking.md"),
    T("How long is the reset code valid?", ("10",), "online_mobile_banking.md"),
    T("Do I have to use two factor authentication?", ("yes|required|authenticator|text",), "online_mobile_banking.md"),
    T("What's the mobile deposit limit per day?", ("5,000|5000",), "online_mobile_banking.md"),
    T("When will the deposited funds be available?", ("next",), "online_mobile_banking.md"),
    T("How do I endorse the check?", ("mobile deposit",), "online_mobile_banking.md"),
    T("What's the daily limit for sending money to a friend?", ("1,000|1000",), "online_mobile_banking.md")],
"B7 Transfers and wires": [
    T("How long does an ACH transfer to another bank take?", ("1", "3"), "transfers_wires.md"),
    T("Is there a same day option?", ("1:00|1 pm|1pm|yes",), "transfers_wires.md"),
    T("What is the daily ACH limit?", ("10,000|10000",), "transfers_wires.md"),
    T("What's the cutoff for a domestic wire?", ("4",), "transfers_wires.md"),
    T("And for an international wire?", ("2",), "transfers_wires.md"),
    T("What information do I need for an international wire?", ("swift|bic",), "transfers_wires.md"),
    T("What's the online wire limit?", ("50,000|50000",), "transfers_wires.md"),
    T("Can I cancel a wire after sending it?", ("not|cannot|can't|no",), "transfers_wires.md"),
    T("Do you verify large wires?", ("call",), "transfers_wires.md"),
    T("Are transfers between my own accounts instant?", ("instant|yes",), "transfers_wires.md")],
"B8 Disputes and visiting us": [
    T("How long do I have to dispute a charge?", ("60",), "disputes_chargebacks.md"),
    T("How do I file a dispute in the app?", ("transactions|dispute",), "disputes_chargebacks.md"),
    T("How long until you decide the dispute?", ("45",), "disputes_chargebacks.md"),
    T("I canceled a subscription but was still charged.", ("proof|cancel",), "disputes_chargebacks.md"),
    T("What time do branches open on Saturday?", ("9",), "branches_contact.md"),
    T("When does the phone support close on weekdays?", ("9",), "branches_contact.md"),
    T("How many branches do you have?", ("14",), "branches_contact.md"),
    T("How late is the drive through open?", ("6",), "branches_contact.md"),
    T("How much is a safe deposit box?", ("35",), "branches_contact.md"),
    T("Is notary service free?", ("free|yes|no charge",), "branches_contact.md")],
"B9 New member, many needs": [
    T("I'd like to join, what do I need?", ("id",), "membership_security.md"),
    T("What's the rate on the high yield savings?", ("4.10|4.1",), "accounts_overview.md"),
    T("Is there a fee for incoming wires?", ("15",), "fees_schedule.md"),
    T("Can I deposit checks with my phone?", ("mobile|yes|deposit",), "online_mobile_banking.md"),
    T("What's the mobile deposit limit for new members?", ("5,000|5000",), "online_mobile_banking.md"),
    T("How do I activate my debit card?", ("app|atm|call",), "debit_cards.md"),
    T("What's the cash back on your credit card?", ("1.5",), "credit_cards.md"),
    T("And on gas and groceries?", ("3",), "credit_cards.md"),
    T("What are the branch hours on weekdays?", ("9", "5"), "branches_contact.md"),
    T("Do you have a branch near Baltimore?", ("baltimore|14|branch",), "branches_contact.md")],
"B10 Rapid-fire, mixed topics": [
    T("What's the APR on a used car loan?", ("6.19",), "loans_auto_personal.md"),
    T("How do I report a stolen card?", ("0199|freeze",), "lost_stolen_fraud.md"),
    T("What time does the drive through close?", ("6",), "branches_contact.md"),
    T("What's the cutoff for international wires?", ("2",), "transfers_wires.md"),
    T("How much is the overdraft fee?", ("30",), "fees_schedule.md"),
    T("What's the HELOC draw period?", ("10",), "mortgages_heloc.md"),
    T("How long does the dispute decision take?", ("45",), "disputes_chargebacks.md"),
    T("How long is the password reset code valid?", ("10",), "online_mobile_banking.md"),
    T("What's the 24 month CD rate?", ("4.25",), "accounts_overview.md"),
    T("What's the credit card balance transfer fee?", ("3",), "credit_cards.md")],
}

BANK = Domain(
    key="bank",
    title="Harbor FCU - credit union voice support",
    blurb=("A voice support line for a fictional credit union. Calls follow predictable chains "
           "(lost card -> freeze -> fraud line -> provisional credit -> replacement), so a "
           "background agent can usually predict the next question. Gold answers let us score "
           "correctness, not just cache hits."),
    docs=BANK_DOCS,
    scenarios=BANK_SCENARIOS,
)

assert len(BANK_DOCS) == 12 and len(BANK_SCENARIOS) == 10 and all(len(v) == 10 for v in BANK_SCENARIOS.values())
