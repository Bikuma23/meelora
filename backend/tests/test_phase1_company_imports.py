from io import BytesIO
from openpyxl import Workbook
from core.company_imports import parse_workbook

def book(headers, rows):
    wb=Workbook(); ws=wb.active; ws.append(headers)
    for r in rows: ws.append(r)
    b=BytesIO(); wb.save(b); return b.getvalue()

def test_parse_company_import_defaults():
    data=book(["Nom","Code société","Juridiction"], [["ABC SA","CH-001","CH"]])
    r=parse_workbook(data)[0]
    assert r["name"]=="ABC SA" and r["functional_currency"]=="CHF" and r["company_type"]=="operating"

def test_parse_fiduciary_assignments():
    data=book(["Nom","Juridiction","Code mandat","Responsable principal","Collaborateurs"], [["ABC SA","CA","M-1","boss@example.com","a@example.com; b@example.com"]])
    r=parse_workbook(data, fiduciary=True)[0]
    assert r["mandate_code"]=="M-1" and r["principal_email"]=="boss@example.com" and len(r["collaborator_emails"])==2
