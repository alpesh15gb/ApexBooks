"""Readable PDF presentation of the existing party report; never recalculates balances."""
import io
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import date
from html import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, Table, TableStyle, Spacer
from reportlab.pdfbase.pdfdoc import PDFString
from currency import format_inr

FONT_DIR=Path(__file__).with_name('assets')/'fonts'
pdfmetrics.registerFont(TTFont('ApexReport',str(FONT_DIR/'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('ApexReportBold',str(FONT_DIR/'DejaVuSans-Bold.ttf')))

TYPES={'sales_invoice':'Sales invoice','purchase_bill':'Purchase bill','payment_in':'Receipt','payment_out':'Payment',
       'credit_note':'Credit note','debit_note':'Debit note','opening_receivable':'Opening receivable','opening_payable':'Opening payable',
       'advance_application':'Advance applied','credit_application':'Credit applied','customer_refund':'Customer refund','supplier_refund':'Supplier refund'}

def render(company_name, report):
    out=io.BytesIO();page=landscape(A4);width=page[0]-64
    body=ParagraphStyle('PartyBody',fontName='ApexReport',fontSize=9,leading=12,textColor=colors.HexColor('#24312c'))
    numeric=ParagraphStyle('PartyNumber',parent=body,alignment=TA_RIGHT)
    heading=ParagraphStyle('PartyHeading',parent=body,fontName='ApexReportBold',textColor=colors.white)
    number_heading=ParagraphStyle('PartyNumberHeading',parent=heading,alignment=TA_RIGHT)
    title=ParagraphStyle('PartyTitle',parent=body,fontName='ApexReportBold',fontSize=17,leading=21,spaceAfter=6)
    pretty=lambda value:date.fromisoformat(value).strftime('%d-%b-%Y')
    period=pretty(report['from_date'])+' to '+pretty(report['to_date'])
    cell=lambda value,style=body:Paragraph(escape(str(value)),style)
    story=[cell(company_name,title),cell('Party statement',ParagraphStyle('PartySubtitle',parent=body,fontName='ApexReportBold',fontSize=12,leading=16)),
           cell('Period: '+period),cell('Party scope: '+(report.get('party') or 'All parties')),cell('Currency: INR - all monetary amounts use Indian digit grouping.'),Spacer(1,12)]
    summary=[['Balance (INR)','Receivable','Payable'],['Opening before '+pretty(report['from_date']),format_inr(report['opening_receivable']),format_inr(report['opening_payable'])],['Closing through '+pretty(report['to_date']),format_inr(report['closing_receivable']),format_inr(report['closing_payable'])]]
    table=Table([[cell(v,heading if i==0 and j==0 else number_heading if i==0 else body if j==0 else numeric) for j,v in enumerate(row)] for i,row in enumerate(summary)],colWidths=[width*.46,width*.27,width*.27])
    base_style=[('BACKGROUND',(0,0),(-1,0),colors.HexColor('#244f43')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dbe4df'))]
    table.setStyle(TableStyle(base_style));story += [table,Spacer(1,15)]
    headers=['Date','Party','Type','Number','Amount (INR)','Receivable (INR)','Payable (INR)']
    rows=[[cell(value,heading if i<4 else number_heading) for i,value in enumerate(headers)]]
    for row in report['rows']:
        values=[pretty(row['date']),row['party'],TYPES.get(row['kind'],row['kind'].replace('_',' ').capitalize()),row['number'],*[format_inr(row[key]) for key in ('amount','receivable','payable')]]
        rows.append([cell(value,body if i<4 else numeric) for i,value in enumerate(values)])
    if report['rows']:
        table=LongTable(rows,colWidths=[76,156,85,100,(width-417)/3,(width-417)/3,(width-417)/3],repeatRows=1)
        table.setStyle(TableStyle(base_style+[('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8f5')])]))
        story.append(table)
    else:story.append(cell('No posted transactions in this period. Opening and closing balances are shown above.'))
    story += [Spacer(1,12),cell('Receivable and payable columns are running balances for the selected scope. Document amounts are shown separately. This statement follows the report\'s party-name matching and posted-entry rules; it is not a statutory return.')]
    if report.get('ordering_note'):story.append(cell(report['ordering_note']))
    def footer(canvas,doc):
        canvas.saveState();canvas._doc.Catalog.Lang=PDFString('en-IN');canvas.setFont('ApexReport',8);canvas.setFillColor(colors.HexColor('#52605b'))
        canvas.drawString(32,20,'Party statement | '+period+' | INR');canvas.drawRightString(page[0]-32,20,'Page '+str(doc.page));canvas.restoreState()
    SimpleDocTemplate(out,pagesize=page,leftMargin=32,rightMargin=32,topMargin=30,bottomMargin=38,title='Party statement - '+period,author=company_name).build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
