from invoice2data import extract_data
from invoice2data.extract.loader import read_templates
import json





# Path to your custom template:
template_file = "../templates/sierra.yml"
templates = read_templates("../templates")
# Path to the invoice PDF you wish to process:
pdf_file = "se1.pdf"

print(templates)
# Extract the data (invoice2data will scan your PDF using its OCR/text extraction)

data = extract_data(pdf_file, templates=templates)

print(json.dumps(data, indent=4))
