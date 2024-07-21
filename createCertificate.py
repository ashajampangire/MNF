import pdfkit
from django.shortcuts import render
from django.template.loader import get_template
from datetime import datetime
from datetime import date
from MNF.settings import BasePath
basepath = BasePath()

# doc_fname = (
# (str(x.translated_ppt.upload_ppt).split("/"))[-1]).split(".")[0]
# x.lpp_invoice_dialogue = f'{doc_fname}_Invoice.pdf'
# x.save()
# str1 = str(datetime.now()).split("-")
# from .utils import render_to_pdf


def certificateGenrate(name,file_from,Hash):
    context = {
        "name": name,
        "file_from": file_from,
        "date": date.today(),
        "hash": Hash
    }
    template = get_template(
        f'{basepath}/lpp/templates/lpp/blockchainCertificate.html')
    html = template.render(context)
    options = {
        'page-size': 'A4',
        'margin-top': '0.0in',
        'margin-right': '0.0in',
        'margin-bottom': '0.0in',
        'margin-left': '0.0in'
    }
    pdfkit.from_string(
        html, f'{basepath}/lpp/certificate/certificate.pdf', options=options)
    return f'{basepath}/lpp/certificate/certificate.pdf'
