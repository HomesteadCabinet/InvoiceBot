You're an expert in Python and PDF parsing using `pdfplumber`, `PyMuPDF`, and `Camelot`.

I need you to generate a custom parsing function for a vendor invoice. I will provide:
- The raw text extracted from the PDF
- Key fields I need extracted
- Notes about how the invoice is structured

Please return a Python function that:
- Accepts a `pdf_path` as input
- Uses `pdfplumber`, `PyMuPDF`, `Camelot` or all of the above to extract structured data
- Returns a `dict` or `DataFrame` with the extracted fields

Some fields are repeated across the document, so you will need to be careful to not duplicate them.
Some fields have a header above the value.
Method needs to be able to handle irregularly structured invoices.
Method needs to be able to handle invoices with multiple line items, possibly with multiple pages.

Method needs to return these fields along with the line items
Key fields to extract:
- Invoice Number
- Ship Date
- Vendor Name
- Invoice Total
- Invoice Due Date
- Invoice Amount
- Cust. P.O.

Method needs to return a list of line items, each with the following fields:
Line items (outcolumnname:pdfcolumnname):
- Id:Code
- Description:Description
- Qty:Ordered
- Unit:Unit Price
- Total_Price:Ext. Price
- Name:Description
