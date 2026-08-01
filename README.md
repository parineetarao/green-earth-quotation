# GreenEarth Quotation Management System

An internal quotation management system developed for Green Earth Engineers & Consultants to streamline the quotation workflow from customer enquiry to approved quotation delivery.

The application enables engineers to manually enter enquiry details, automatically generate quotations using predefined engineering templates, review draft quotations, and send approved quotations directly to customers via email.

Features
Customer enquiry management
Automatic quotation generation
Review and approval workflow
PDF and DOCX quotation generation
Email delivery of approved quotations
Customer quotation history
Dashboard with enquiry and quotation metrics
Manual pricing workflow for quotations outside the verified capacity range
Workflow
Create a new customer enquiry.
Enter project details such as plant type, capacity, and customer information.
Generate a draft quotation.
Review the generated quotation.
Approve or reject the quotation.
Approved quotations are emailed to the customer with downloadable PDF/DOCX copies.
Tech Stack
Frontend: Streamlit
Backend: FastAPI
Database: PostgreSQL
ORM: SQLAlchemy
Document Generation: python-docx, ReportLab
Email Service: Postmark
Deployment: Render (API) + Streamlit Cloud

Main Modules
Review Queue

Displays all draft quotations awaiting review. Quotations within the verified engineering range can be approved and emailed directly, while quotations outside the verified range are routed for manual pricing.

Customers

Search and browse customers along with their complete quotation history and current quotation status.

Enquiries

Manage incoming enquiries, filter by status, and complete any enquiries requiring additional information before quotation generation.

Summary

Provides an overview of key business metrics including enquiries received, quotations generated, pending approvals, and enquiry status distribution.

Current Workflow
Customer Enquiry
        ↓
Generate Draft Quotation
        ↓
Engineering Review
        ↓
Approve / Reject
        ↓
Generate PDF & DOCX
        ↓
Email Customer
Future Enhancements
AI-assisted quotation recommendations
Historical quotation similarity search
CRM integration
Automated enquiry capture from website
Customer portal for quotation tracking
Approval audit trail
Analytics dashboard with trend analysis
Developed For

Green Earth Engineers & Consultants

Environmental Engineering • Water & Wastewater Treatment • Air Pollution Control • Turnkey Environmental Solutions
