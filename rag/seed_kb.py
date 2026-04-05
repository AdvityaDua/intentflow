"""
IntentFlow — Knowledge Base Seed Data.
15 genuine IT support articles covering common enterprise scenarios.
Seeds ChromaDB on first run.
"""

import logging

from rag.retriever import index_batch, count

logger = logging.getLogger(__name__)

KB_ARTICLES = [
    {
        "id": "KB-001",
        "title": "Password Reset Procedure",
        "category": "access",
        "tags": "password,reset,login,locked",
        "text": (
            "KB-001: Password Reset Procedure\n\n"
            "When a user cannot log in or has forgotten their password:\n"
            "1. Verify user identity by confirming employee ID and registered email address.\n"
            "2. Check if the account is locked (3+ failed attempts triggers auto-lock).\n"
            "3. If locked, unlock the account first via PUT /iam/unlock.\n"
            "4. Send a password reset link via POST /iam/reset-password with method 'email_link'.\n"
            "5. The reset link expires in 24 hours.\n"
            "6. Inform the user to check spam/junk folder if email is not received within 5 minutes.\n"
            "7. For VPN-only accounts, direct the user to the internal portal reset page.\n\n"
            "Escalation: If the user's email is also compromised, escalate to Security team."
        ),
    },
    {
        "id": "KB-002",
        "title": "Account Unlock After Failed Login Attempts",
        "category": "access",
        "tags": "account,locked,unlock,login,failed",
        "text": (
            "KB-002: Account Unlock After Failed Login Attempts\n\n"
            "Accounts are automatically locked after 3 consecutive failed login attempts.\n"
            "1. Verify user identity using employee ID and security questions.\n"
            "2. Check the account status via GET /iam/status to confirm it is locked.\n"
            "3. Unlock the account via PUT /iam/unlock.\n"
            "4. Advise the user to reset their password if they've forgotten it.\n"
            "5. If the user reports they did not make those login attempts, escalate to Security.\n\n"
            "Auto-unlock occurs after 30 minutes for Standard accounts. "
            "Admin accounts require manual unlock by IT Security."
        ),
    },
    {
        "id": "KB-003",
        "title": "VPN Connection Troubleshooting",
        "category": "technical",
        "tags": "vpn,connection,remote,network",
        "text": (
            "KB-003: VPN Connection Troubleshooting\n\n"
            "For users unable to connect to the corporate VPN:\n"
            "1. Verify the user's VPN credentials are active via GET /iam/status.\n"
            "2. Check if the VPN client is updated to the latest version (v4.2+).\n"
            "3. Common fix: Clear VPN client cache and reconnect.\n"
            "4. If using split-tunnel, ensure the correct profile is selected.\n"
            "5. Firewall ports required: UDP 500, UDP 4500, ESP protocol.\n"
            "6. If on hotel/airport WiFi, switch to TCP 443 mode.\n"
            "7. Create a support ticket if the issue persists after steps 1-6.\n\n"
            "Known issue: VPN disconnects every 2 hours on macOS Sonoma — patch pending."
        ),
    },
    {
        "id": "KB-004",
        "title": "Email Configuration and Troubleshooting",
        "category": "technical",
        "tags": "email,outlook,configuration,sync",
        "text": (
            "KB-004: Email Configuration and Troubleshooting\n\n"
            "For email-related issues:\n"
            "1. Verify the user's email account is active via GET /user/profile.\n"
            "2. For Outlook sync issues: Clear local cache, remove and re-add account.\n"
            "3. Mobile email setup: Use ActiveSync with server mail.company.com, port 443.\n"
            "4. For email delivery failures, check the message trace in admin portal.\n"
            "5. Shared mailbox access: Submit access request via POST /access/request.\n"
            "6. Large attachment limit: 25MB internal, 10MB external. Use file share for larger.\n"
            "7. If user receives bounce-backs for all emails, check if account is flagged for spam.\n\n"
            "Escalation: Suspected email compromise → immediately disable account and escalate to Security."
        ),
    },
    {
        "id": "KB-005",
        "title": "Refund Processing Policy",
        "category": "billing",
        "tags": "refund,billing,payment,return",
        "text": (
            "KB-005: Refund Processing Policy\n\n"
            "Refund eligibility and process:\n"
            "1. Verify the order exists via GET /billing/order with the order_id.\n"
            "2. Check refund eligibility via GET /billing/refund-eligibility.\n"
            "3. Eligibility criteria: Within 30 days of purchase, item not consumed/activated.\n"
            "4. If eligible, process refund via POST /billing/refund.\n"
            "5. Refund processing time: 5-7 business days to credit card, 3-5 days to company credit.\n"
            "6. Partial refunds allowed for multi-item orders.\n"
            "7. Refunds over $5,000 require Finance Director approval — escalate with documentation.\n\n"
            "Exception: Subscription cancellations are prorated based on remaining days."
        ),
    },
    {
        "id": "KB-006",
        "title": "Billing Dispute Resolution",
        "category": "billing",
        "tags": "billing,dispute,invoice,charge,incorrect",
        "text": (
            "KB-006: Billing Dispute Resolution\n\n"
            "For incorrect charges or billing disputes:\n"
            "1. Look up the invoice via GET /billing/invoice with invoice_id.\n"
            "2. Compare the disputed amount with the service agreement on file.\n"
            "3. If discrepancy confirmed, file a dispute via POST /billing/dispute.\n"
            "4. The billing team reviews disputes within 2 business days.\n"
            "5. Credits are issued within 1 billing cycle if the dispute is upheld.\n"
            "6. Provide the customer with dispute ID for tracking.\n\n"
            "Note: Disputes over $10,000 require VP-level approval. "
            "All billing disputes are logged in the compliance audit trail."
        ),
    },
    {
        "id": "KB-007",
        "title": "New Access Request Process",
        "category": "access",
        "tags": "access,permission,request,system,authorize",
        "text": (
            "KB-007: New Access Request Process\n\n"
            "When a user needs access to a new system or resource:\n"
            "1. Verify the user's identity and current role via GET /user/profile.\n"
            "2. Confirm the requested system exists and accepts access requests.\n"
            "3. Submit access request via POST /access/request with user_id and system name.\n"
            "4. Notify the user's manager for approval via POST /user/notify.\n"
            "5. Standard access requests are processed within 24 hours after approval.\n"
            "6. For Finance, HR, or Security systems, additional compliance training is required.\n\n"
            "Escalation: Emergency access for production incidents → can be fast-tracked by on-call manager."
        ),
    },
    {
        "id": "KB-008",
        "title": "SAP System Access and Issues",
        "category": "technical",
        "tags": "sap,erp,access,module,error",
        "text": (
            "KB-008: SAP System Access and Issues\n\n"
            "For SAP-related problems:\n"
            "1. Check user's SAP role assignment in the IAM portal.\n"
            "2. Common error S:001 — user profile not synced. Fix: trigger AD sync.\n"
            "3. Module access (FI, CO, MM, SD) requires separate role assignment.\n"
            "4. SAP GUI connectivity: Ensure ports 3200-3299 are open.\n"
            "5. For SAP Fiori launchpad issues, clear browser cache and cookies.\n"
            "6. Transaction authorization errors: Log the t-code and escalate to SAP Basis team.\n"
            "7. Create ticket via POST /ticket/create with category 'sap_issue'.\n\n"
            "Known issue: SAP BW reports timeout after 5 minutes — optimization in progress."
        ),
    },
    {
        "id": "KB-009",
        "title": "Hardware Request and Replacement",
        "category": "hardware",
        "tags": "hardware,laptop,monitor,keyboard,replacement,request",
        "text": (
            "KB-009: Hardware Request and Replacement\n\n"
            "For hardware-related requests:\n"
            "1. For new hardware: Submit request via POST /ticket/create with category 'hardware_request'.\n"
            "2. Standard laptop refresh cycle: Every 3 years.\n"
            "3. Broken/damaged hardware: Provide incident photos and asset tag number.\n"
            "4. Replacement timeline: 3-5 business days for in-stock items.\n"
            "5. Special peripherals (ergonomic equipment): Requires manager and HR approval.\n"
            "6. Loaner devices available for urgent situations — contact IT Help Desk.\n\n"
            "Asset return: All company hardware must be returned within 5 days of offboarding."
        ),
    },
    {
        "id": "KB-010",
        "title": "Software Installation and License Request",
        "category": "software",
        "tags": "software,install,license,application,request",
        "text": (
            "KB-010: Software Installation and License Request\n\n"
            "For software installation or license requests:\n"
            "1. Check the approved software catalog in the Self-Service Portal.\n"
            "2. Approved software can be self-installed from the Software Center.\n"
            "3. For non-catalog software: Submit request via POST /ticket/create with justification.\n"
            "4. License compliance: All commercial software must have a valid license on file.\n"
            "5. Free/open-source software still requires security review before installation.\n"
            "6. Developer tools (Docker, VS Code, etc.) are pre-approved for Engineering role.\n\n"
            "Restricted: No personal software on company devices. No cryptocurrency miners."
        ),
    },
    {
        "id": "KB-011",
        "title": "Security Incident Response",
        "category": "security",
        "tags": "security,incident,breach,phishing,malware,compromised",
        "text": (
            "KB-011: Security Incident Response\n\n"
            "CRITICAL: All security incidents require IMMEDIATE human escalation.\n"
            "Automated resolution is NOT permitted for security incidents.\n\n"
            "Initial triage steps:\n"
            "1. Classify the incident: phishing, malware, unauthorized access, data breach, or DDoS.\n"
            "2. Isolate affected systems if possible (disconnect from network).\n"
            "3. Preserve evidence — do NOT delete suspicious emails or files.\n"
            "4. Create a Critical priority ticket via POST /ticket/create.\n"
            "5. Notify the Security Operations Center (SOC) immediately.\n"
            "6. If data breach suspected, Legal and Compliance must be notified within 1 hour.\n\n"
            "NEVER attempt to remediate a security incident autonomously."
        ),
    },
    {
        "id": "KB-012",
        "title": "Data Recovery and Backup Restoration",
        "category": "technical",
        "tags": "data,recovery,backup,restore,deleted,lost",
        "text": (
            "KB-012: Data Recovery and Backup Restoration\n\n"
            "For lost or accidentally deleted data:\n"
            "1. Check the Recycle Bin and OneDrive version history first.\n"
            "2. SharePoint sites retain deleted items for 93 days.\n"
            "3. For email recovery: Deleted items retained for 30 days in Exchange.\n"
            "4. Server/database recovery: Backups run nightly at 2 AM UTC.\n"
            "5. Recovery Point Objective (RPO): Maximum 24-hour data loss for Tier 2 systems.\n"
            "6. For Tier 1 (critical) systems: Real-time replication, RPO < 1 hour.\n"
            "7. Submit recovery request with specific date/time range and file paths.\n\n"
            "Escalation: Large-scale recovery (> 100GB) requires Infrastructure Manager approval."
        ),
    },
    {
        "id": "KB-013",
        "title": "Printer and Peripheral Troubleshooting",
        "category": "technical",
        "tags": "printer,peripheral,print,scanner,issue",
        "text": (
            "KB-013: Printer and Peripheral Troubleshooting\n\n"
            "For printing and peripheral issues:\n"
            "1. Verify the printer is online and has paper/toner.\n"
            "2. Re-add the network printer using \\\\printserver\\printer-name.\n"
            "3. Clear the print queue: Stop Print Spooler service, clear queue, restart.\n"
            "4. For badge-release printers: Ensure user's badge is enrolled in the print system.\n"
            "5. Scanner issues: Install the latest TWAIN/WIA drivers.\n"
            "6. USB peripherals not recognized: Try a different port, check Device Manager.\n"
            "7. Create ticket if hardware replacement is needed.\n\n"
            "Note: Wireless printing is only supported on designated printers per floor."
        ),
    },
    {
        "id": "KB-014",
        "title": "Access Revocation and Offboarding",
        "category": "access",
        "tags": "access,revoke,offboarding,deactivate,terminate",
        "text": (
            "KB-014: Access Revocation and Offboarding\n\n"
            "IMPORTANT: Access revocation requires authorized approval.\n\n"
            "For employee offboarding or access removal:\n"
            "1. Verify the revocation request is authorized by HR or the employee's manager.\n"
            "2. Disable Active Directory account (do not delete — retain for 90 days).\n"
            "3. Revoke VPN, email, and all application access.\n"
            "4. Transfer mailbox and OneDrive ownership to the manager.\n"
            "5. Collect all hardware assets within 5 business days.\n"
            "6. Document all actions in the audit trail.\n\n"
            "Emergency revocation (terminated for cause): Immediate access disable, "
            "notify Security to escort if on premises."
        ),
    },
    {
        "id": "KB-015",
        "title": "General IT Inquiry and Service Catalog",
        "category": "general",
        "tags": "general,inquiry,question,help,catalog,information",
        "text": (
            "KB-015: General IT Inquiry and Service Catalog\n\n"
            "For general questions and information requests:\n"
            "1. Direct users to the Self-Service Portal for common requests.\n"
            "2. Service catalog includes: Hardware, Software, Access, Network, and Support services.\n"
            "3. Business hours: IT Help Desk available 7 AM - 7 PM local time, Mon-Fri.\n"
            "4. After-hours support: Critical issues only — call the emergency hotline.\n"
            "5. Average resolution times: Critical (30 min), High (2 hrs), Medium (8 hrs), Low (24 hrs).\n"
            "6. For project-related IT requests, engage the IT Business Partner for the department.\n\n"
            "Feedback: Users can rate their support experience via the post-resolution survey."
        ),
    },
]


def seed_knowledge_base() -> int:
    """
    Seed the ChromaDB vector store with KB articles.
    Returns the number of articles indexed.
    """
    current_count = count()
    if current_count >= len(KB_ARTICLES):
        logger.info(f"Knowledge base already seeded ({current_count} articles)")
        return current_count

    logger.info(f"Seeding knowledge base with {len(KB_ARTICLES)} articles...")
    docs = []
    for article in KB_ARTICLES:
        docs.append({
            "id": article["id"],
            "text": article["text"],
            "metadata": {
                "title": article["title"],
                "category": article["category"],
                "tags": article["tags"],
            },
        })

    index_batch(docs)
    logger.info(f"Knowledge base seeded: {len(docs)} articles indexed")
    return len(docs)
