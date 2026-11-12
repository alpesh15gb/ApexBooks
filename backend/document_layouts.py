from currency import format_inr
"""Five reference-inspired A4 layouts sharing a single accounting data source."""
import base64
import io
from collections import defaultdict
from decimal import Decimal
from html import escape
from urllib.parse import urlencode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, LongTable, TableStyle, Spacer, Image, KeepTogether
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget

LAYOUTS = {'modern', 'vintage', 'mrp_discount', 'elegant', 'evergreen'}

def line_discount_label(line):
    """Fixed-amount input wins by presence; computed percent is also stored as zero."""
    if 'discount_amount' in line:
        return 'INR ' + format_inr(line['discount_amount'])
    return str(line.get('discount_percent', '0')) + '%'


def words(number):
    small = 'Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen'.split()
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    def whole(n):
        if n < 20: return small[n]
        if n < 100: return tens[n // 10] + (' ' + small[n % 10] if n % 10 else '')
        for value, label in ((10000000, 'Crore'), (100000, 'Lakh'), (1000, 'Thousand'), (100, 'Hundred')):
            if n >= value: return whole(n // value) + ' ' + label + (' ' + whole(n % value) if n % value else '')
    amount = Decimal(str(number)).quantize(Decimal('.01'))
    rupees = int(amount); paise = int((amount - rupees) * 100)
    return whole(rupees) + ' Rupees' + (' and ' + whole(paise) + ' Paise' if paise else '') + ' Only'

def render_document(record, supplier, branding, template, title, paid=Decimal('0')):
    out = io.BytesIO(); width = A4[0] - 48
    grid = template in {'vintage', 'evergreen'}
    accent = colors.black if template == 'elegant' else colors.HexColor('#19365b')
    body = ParagraphStyle('body', fontName='Helvetica', fontSize=8, leading=11)
    bold = ParagraphStyle('bold', parent=body, fontName='Helvetica-Bold')
    right = ParagraphStyle('right', parent=body, alignment=TA_RIGHT)
    heading = ParagraphStyle('heading', parent=bold, fontSize=12, leading=16, textColor=accent)
    company_style = ParagraphStyle('company', parent=heading, textColor=colors.black)
    total_style = ParagraphStyle('total', parent=bold, fontSize=11, leading=15, alignment=TA_RIGHT)
    centered_heading = ParagraphStyle('centered-heading', parent=heading, alignment=TA_CENTER)
    def p(value, style=body): return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)
    def image(value, w, h):
        if not value: return Spacer(1, 1)
        raw = base64.b64decode(value.split(',', 1)[1])
        result = Image(io.BytesIO(raw)); result._restrictSize(w, h)
        return result
    def table(rows, widths, boxed=False, split_in_row=False):
        result = Table(rows, colWidths=widths, hAlign='LEFT', splitInRow=int(split_in_row))
        commands = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]
        if boxed: commands.append(('GRID', (0, 0), (-1, -1), .5, colors.black))
        result.setStyle(TableStyle(commands)); return result
    data = record.data
    lines = data.get('lines', [])
    tax_mode = data.get('tax_mode', supplier.get('tax_mode', 'regular'))
    has_tax = any(Decimal(str(line.get('tax', 0))) > 0 for line in lines)
    seller = [p(supplier.get('name'), company_style), p(('GSTIN ' + supplier['gstin'] + '\n' if supplier.get('gstin') else '') + supplier.get('address', '') + '\n' + branding.get('phone', '') + ('  ' + branding.get('email', '') if branding.get('email') else ''))]
    logo = image(branding.get('logo'), 82, 65)
    elements = []
    if grid:
        bar = table([['',p(title.upper(), centered_heading), p('ORIGINAL FOR RECIPIENT', right)]], [width*.25,width*.50,width*.25])
        bar.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,colors.black)])); elements.append(bar)
    if template == 'elegant':
        elements.append(table([[logo, seller, [p(title.upper(), heading), p('ORIGINAL FOR RECIPIENT', right)]]], [90, width-260, 170]))
    elif grid:
        elements.append(table([[table([[logo, seller]], [90, width/2-100]), [p('Invoice / document #: ' + (record.number or record.id[:8]), bold), p('Date: ' + record.date.isoformat()), p('Due date: ' + str(data.get('due_date') or '—')), p('Place of supply: ' + str(data.get('place_of_supply') or '—'))]]], [width/2]*2, True))
    else:
        elements.append(table([[[p(title.upper(), heading), *seller], [p('ORIGINAL FOR RECIPIENT', right), logo]]], [width*.67, width*.33]))
        elements.append(table([[p('Invoice / document #: ' + (record.number or record.id[:8]), bold), p('Date: ' + record.date.isoformat()), p('Due date: ' + str(data.get('due_date') or '—'))]], [width/3]*3))
    party_label='Supplier details' if record.kind in {'purchase_bill','purchase_order','debit_note'} else 'Payee details' if record.kind in {'expense','payment_out','customer_refund'} else 'Received from' if record.kind in {'payment_in','supplier_refund'} else 'Customer / party details'
    bill = [p(party_label, bold), p(record.name, bold), p(data.get('party_address', '')), p(('GSTIN ' + data['party_gstin']) if data.get('party_gstin') else ''), p(data.get('party_phone', ''))]
    shipping = [p('Shipping address', bold), p(data.get('shipping_address') or data.get('party_address', ''))]
    if template == 'elegant':
        elements.append(table([[bill + shipping, [p('Document #: ' + record.number, right), p('Date: ' + record.date.isoformat(), right), p('Due: ' + str(data.get('due_date') or '—'), right), p('Place of supply: ' + str(data.get('place_of_supply') or '—'), right)]]], [width*.55,width*.45]))
    elif grid: elements.append(table([[bill, shipping]], [width/2]*2, True))
    else:
        contact = [p(party_label,bold),p(record.name,bold),p(data.get('party_phone','')),p(('GSTIN '+data['party_gstin']) if data.get('party_gstin') else '')]
        billing = [p('Billing address',bold),p(data.get('party_address',''))]
        elements.append(table([[contact,billing,shipping]],[width/3]*3))
    if tax_mode == 'composition': elements.append(p('Composition taxable person, not eligible to collect tax on supplies', bold))
    if not grid and template != 'elegant' and tax_mode == 'regular': elements.append(p('Place of supply: ' + str(data.get('place_of_supply') or '—'), bold))
    elements.append(Spacer(1, 9))
    if template == 'mrp_discount': headers = ['#', 'Item', 'MRP', 'Selling price', 'Qty', 'Amount']; fractions = [.035,.39,.14,.14,.095,.20]
    elif template == 'evergreen': headers = ['#','Item','HSN/SAC','Tax','Qty','Rate / item','Per','Amount']; fractions = [.035,.315,.10,.07,.09,.13,.08,.18]
    elif template == 'elegant': headers = ['#','Item','HSN/SAC','Rate / item','Qty','Amount']; fractions = [.035,.39,.13,.16,.085,.20]
    else: headers = ['#','Item','HSN/SAC','Rate / item','Qty','Taxable value','Tax amount','Amount']; fractions = [.035,.285,.10,.13,.06,.14,.13,.14]
    scale = width / sum(fractions); widths = [v*scale for v in fractions]
    rows = [[p(h, bold) for h in headers]]
    tax_summary = defaultdict(lambda: [Decimal('0'),Decimal('0')])
    total_qty = Decimal('0')
    for index, line in enumerate(lines, 1):
        qty, rate, taxable, tax = [Decimal(str(line.get(key, 0))) for key in ('quantity','rate','taxable','tax')]
        total_qty += qty
        desc = line.get('description', '')
        if line.get('unit'): desc += '\nUnit: ' + str(line['unit'])
        if template == 'mrp_discount': desc += '\nHSN: ' + str(line.get('hsn') or '—')
        if line.get('price_includes_tax'):desc += chr(10)+'Rate includes GST'
        if 'discount_amount' in line or Decimal(str(line.get('discount_percent',0))):desc+=chr(10)+'Line discount: '+line_discount_label(line)
        if Decimal(str(line.get('document_discount',0))):desc+=chr(10)+'Document discount: INR '+format_inr(line['document_discount'])
        gross = taxable + tax
        amount = taxable if template in {'elegant','evergreen'} else gross
        mrp = Decimal(str(line.get('mrp') or '0'))
        values = {'#':index, 'Item':desc, 'HSN/SAC':line.get('hsn',''), 'Tax':str(line.get('gst_rate',0))+'%' if has_tax else '—', 'Qty':str(qty), 'Per':line.get('unit',''), 'Rate / item':format_inr(rate), 'MRP':(format_inr(mrp) if mrp > 0 else '—'), 'Selling price':format_inr(gross/qty if qty else rate), 'Taxable value':format_inr(taxable), 'Tax amount':format_inr(tax), 'Amount':format_inr(amount)}
        rows.append([p(values[h], body if h in {'Item','HSN/SAC','#','Per'} else right) for h in headers])
        key = (str(line.get('hsn','')),str(line.get('gst_rate',0)))
        tax_summary[key][0] += taxable; tax_summary[key][1] += tax
    if grid and len(lines) < 6: rows.append(['']*len(headers))
    line_table = LongTable(rows, colWidths=widths, repeatRows=1, hAlign='LEFT', minRowHeights=[0]*(len(rows)-1)+([max(24,180-18*len(lines))] if grid and len(lines)<6 else [0]))
    style = [('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEABOVE',(0,0),(-1,0),1,accent),('LINEBELOW',(0,0),(-1,0),1,accent)]
    style += ([('BOX',(0,0),(-1,-1),.4,colors.HexColor('#777777'))]+[('LINEBEFORE',(col,0),(col,-1),.4,colors.HexColor('#777777')) for col in range(1,len(headers))]) if grid else [('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#bbbbbb'))]
    if template == 'elegant': style += [('BACKGROUND',(0,0),(-1,0),colors.black),('TEXTCOLOR',(0,0),(-1,0),colors.white)]
    # Paragraph colours must be set explicitly; Table TEXTCOLOR does not affect them.
    if template == 'elegant':
        white = ParagraphStyle('white',parent=bold,textColor=colors.white)
        line_table._cellvalues[0] = [p(h,white) for h in headers]
    line_table.setStyle(TableStyle(style))
    if lines: elements.append(line_table)
    totals = [('Taxable amount' if has_tax and not any(Decimal(str(data.get(key,0))) for key in ('nil_rated_value','exempt_value','non_gst_value')) else 'Subtotal',data.get('taxable',record.amount))] if lines else []
    if has_tax:
        rates = {Decimal(str(line.get('gst_rate',0))) for line in lines if Decimal(str(line.get('tax',0))) > 0}
        def tax_label(key):
            if len(rates)!=1: return key.upper()
            rate = next(iter(rates)) / (2 if key in {'cgst','sgst'} else 1)
            return key.upper()+' '+format(rate.normalize(),'f')+'%'
        totals += [(tax_label(key),data.get(key,0)) for key in ('cgst','sgst','igst') if Decimal(str(data.get(key,0))) > 0]
        if Decimal(str(data.get('supplier_tax',0))) > 0: totals.append(('Supplier tax',data['supplier_tax']))
    if Decimal(str(data.get('additional_charges',0))): totals.append(('Additional charges',data['additional_charges']))
    if Decimal(str(data.get('round_off',0))): totals.append(('Round off',data['round_off']))
    totals.append(('Total INR',record.amount))
    if template=='mrp_discount': totals=[totals[-1],*totals[:-1]]
    total_rows=[[p(label,total_style if label=='Total INR' else right),p(format_inr(value),total_style if label=='Total INR' else right)] for label,value in totals]
    if grid: elements.append(table(total_rows,[width*.76,width*.24],True))
    else:
        block=table(total_rows,[width*.29,width*.20]);block.setStyle(TableStyle([('LINEABOVE',(0,next(i for i,row in enumerate(totals) if row[0]=='Total INR')),(-1,next(i for i,row in enumerate(totals) if row[0]=='Total INR')),.5,accent)]))
        total_wrapper=table([['',block]],[width*.51,width*.49]);total_wrapper.setStyle(TableStyle([('LEFTPADDING',(1,0),(1,0),0),('RIGHTPADDING',(1,0),(1,0),0),('TOPPADDING',(1,0),(1,0),0),('BOTTOMPADDING',(1,0),(1,0),0)]));elements.append(total_wrapper)
    units = {str(line.get('unit', '')).strip() for line in lines}
    quantity_summary = f'Total items / Qty: {len(lines)} / {total_qty}' if len(units) <= 1 else f'Total items: {len(lines)} (mixed units)'
    elements.append(table([[p(quantity_summary if lines else ''), p('Amount in words: INR ' + words(record.amount),right)]], [width*.27,width*.73],grid))
    if grid and has_tax:
        central=Decimal(str(data.get('cgst',0)));state_tax=Decimal(str(data.get('sgst',0)));integrated=Decimal(str(data.get('igst',0)))
        if central or state_tax:
            tax_rows=[[p(h,bold) for h in ['HSN/SAC','Base value','Central tax','','State tax','','Total tax']],['','','Rate','Amount','Rate','Amount','']]
            total_tax=sum((tax for base,tax in tax_summary.values()),Decimal('0'));cumulative=allocated=Decimal('0')
            for (hsn,rate),(base,tax) in tax_summary.items():
                cumulative+=tax;desired=(cumulative*central/total_tax).quantize(Decimal('.01')) if total_tax else Decimal('0');cgst=desired-allocated;allocated=desired;sgst=tax-cgst
                tax_rows.append([p(hsn),p(format_inr(base),right),p(str(Decimal(rate)/2)+'%',right),p(format_inr(cgst),right),p(str(Decimal(rate)/2)+'%',right),p(format_inr(sgst),right),p(format_inr(tax),right)])
            tax_rows.append([p('TOTAL',bold),p(format_inr(sum((v[0] for v in tax_summary.values()),Decimal('0'))),right),'',p(format_inr(central),right),'',p(format_inr(state_tax),right),p(format_inr(total_tax),right)])
            tax_table=table(tax_rows,[width*f for f in (.13,.19,.09,.15,.09,.15,.20)],True)
            tax_table.setStyle(TableStyle([('SPAN',(0,0),(0,1)),('SPAN',(1,0),(1,1)),('SPAN',(2,0),(3,0)),('SPAN',(4,0),(5,0)),('SPAN',(6,0),(6,1))]));tax_table.repeatRows=2
        else:
            tax_rows=[[p(h,bold) for h in ['HSN/SAC','Base value','IGST rate' if integrated else 'GST rate','Tax amount']]]
            for (hsn,rate),(base,tax) in tax_summary.items():tax_rows.append([p(hsn),p(format_inr(base),right),p(rate+'%',right),p(format_inr(tax),right)])
            tax_rows.append([p('TOTAL',bold),p(format_inr(sum((v[0] for v in tax_summary.values()),Decimal('0'))),right),'',p(format_inr(sum((v[1] for v in tax_summary.values()),Decimal('0'))),right)])
            tax_table=table(tax_rows,[width/4]*4,True);tax_table.repeatRows=1
        elements.append(tax_table)
    used_label,remaining_label=('Credit used / refunded','Credit remaining') if record.kind in {'credit_note','debit_note'} else ('Amount paid','Amount payable')
    used_text=used_label+': INR '+format_inr(paid)
    if record.kind in {'sales_invoice','purchase_bill'}:
        payments=Decimal(str(data.get('payments_applied',paid)))
        adjustments=max(Decimal('0'),paid-payments)
        used_text=('Payments received' if record.kind=='sales_invoice' else 'Payments made')+': INR '+format_inr(payments)
        if adjustments:
            used_text+='\n'+('Credit notes / adjustments' if record.kind=='sales_invoice' else 'Debit notes / adjustments')+': INR '+format_inr(adjustments)
    elements.append(table([[p(used_text,right),p(remaining_label+': INR ' + format_inr(max(Decimal('0'),record.amount-paid)),right)]],[width/2]*2,grid))
    if record.kind=='pos' and data.get('payment_account','cash')=='cash':elements.append(table([[p('Cash tendered: INR '+str(data.get('tender_amount',record.amount))),p('Change: INR '+str(data.get('change_amount','0')),right)]],[width/2]*2,grid))
    bank = [p('Bank details',bold)] + [p(label + ': ' + branding[key]) for key,label in [('bank_name','Bank'),('account_number','Account #'),('ifsc','IFSC'),('branch','Branch')] if branding.get(key)]
    qr = ''
    payable=max(Decimal('0'),record.amount-paid)
    if branding.get('upi_id') and record.kind in {'sales_invoice','estimate','proforma','pos'} and payable > 0:
        uri='upi://pay?'+urlencode({'pa':branding['upi_id'],'pn':supplier.get('name',''),'cu':'INR','am':format(payable,'.2f')})
        code=QrCodeWidget(uri); x0,y0,x1,y1=code.getBounds(); size=78
        qr=Drawing(size,size,transform=[size/(x1-x0),0,0,size/(y1-y0),0,0]);qr.add(code)
        qr=[p('Pay using UPI',bold),qr,p(branding['upi_id'])]
    signature=[p('For '+supplier.get('name',''),right), image(branding.get('signature'),95,60),p('Authorized signatory',right)]
    if grid:
        payment_block=table([[bank,qr or '']],[width*.43,width*.24])
        payment_wrapper=table([[payment_block,signature]],[width*.67,width*.33],True);payment_wrapper.setStyle(TableStyle([('LEFTPADDING',(0,0),(0,0),0),('RIGHTPADDING',(0,0),(0,0),0)]));elements.append(KeepTogether(payment_wrapper))
        elements.append(table([[[p('Notes',bold),p(branding.get('notes',''))],[p('Terms and conditions',bold),p(branding.get('terms',''))]]],[width/2]*2,True,split_in_row=True))
    else:
        elements.append(KeepTogether(table([[qr,bank,signature]],[width*.18,width*.45,width*.37]) if qr else table([[bank,signature]],[width*.63,width*.37])))
        for label,key in [('Notes','notes'),('Terms and conditions','terms')]:
            if branding.get(key):elements += [Spacer(1,7),p(label,bold),p(branding[key])]
    def footer(c,doc):
        c.setFont('Helvetica',7);c.drawString(24,20,'Page '+str(doc.page));c.drawRightString(A4[0]-24,20,'Generated with Apex Books')
    pdf=SimpleDocTemplate(out,pagesize=A4,leftMargin=24,rightMargin=24,topMargin=24,bottomMargin=34,title=title)
    pdf.build(elements,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


# Roll receipts for thermal printers (Vyapar / MyBillBook POS style). One page as tall as its content.
THERMAL = {'thermal_80': 80, 'thermal_58': 58}

def render_thermal(record, supplier, branding, template, title, paid=Decimal('0')):
    from reportlab.lib.units import mm
    roll = THERMAL[template] * mm; margin = 3 * mm - 6; width = roll - 2 * margin - 12  # the page frame pads 6pt per side
    small = template == 'thermal_58'
    size = 7 if small else 8
    body = ParagraphStyle('t-body', fontName='Helvetica', fontSize=size, leading=size + 2.5)
    bold = ParagraphStyle('t-bold', parent=body, fontName='Helvetica-Bold')
    center = ParagraphStyle('t-center', parent=body, alignment=TA_CENTER)
    center_bold = ParagraphStyle('t-center-bold', parent=bold, alignment=TA_CENTER)
    shop = ParagraphStyle('t-shop', parent=center_bold, fontSize=size + 4, leading=size + 6)
    right = ParagraphStyle('t-right', parent=body, alignment=TA_RIGHT)
    right_bold = ParagraphStyle('t-right-bold', parent=bold, alignment=TA_RIGHT)
    grand = ParagraphStyle('t-grand', parent=right_bold, fontSize=size + 3, leading=size + 5)
    def p(value, style=body): return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)
    def pair(label, value, left=body, value_style=right):
        t = Table([[p(label, left), p(value, value_style)]], colWidths=[width * .58, width * .42])
        t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 1), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t
    def rule(): return p('-' * (38 if small else 52), center)
    data = record.data; lines = data.get('lines', [])
    els = [p(supplier.get('name'), shop)]
    contact = '\n'.join(x for x in [supplier.get('address', ''), ('GSTIN ' + supplier['gstin']) if supplier.get('gstin') else '', branding.get('phone', '')] if x)
    if contact: els.append(p(contact, center))
    els += [Spacer(1, 3), p(title.upper(), center_bold), pair('No. ' + (record.number or record.id[:8]), record.date.strftime('%d-%m-%Y'))]
    if record.name and record.name.strip().lower() not in {'walk-in', 'walk in', 'cash', 'cash sale'}:
        els.append(p(record.name + (('\n' + data['party_phone']) if data.get('party_phone') else ''), bold))
    els.append(rule())
    for index, line in enumerate(lines, 1):
        qty, rate, taxable, tax = [Decimal(str(line.get(key, 0))) for key in ('quantity', 'rate', 'taxable', 'tax')]
        els.append(p(f"{index}. {line.get('description', '')}", bold))
        detail = f"{qty.normalize():f} {line.get('unit') or ''} x {format_inr(rate)}".replace('  ', ' ')
        if Decimal(str(line.get('gst_rate', 0))) and tax: detail += f" · GST {Decimal(str(line['gst_rate'])).normalize():f}%"
        els.append(pair(detail, format_inr(taxable + tax)))
    els.append(rule())
    if lines: els.append(pair('Items / Qty', f"{len(lines)} / {sum((Decimal(str(l.get('quantity', 0))) for l in lines), Decimal('0')).normalize():f}"))
    has_tax = any(Decimal(str(data.get(k, 0))) for k in ('cgst', 'sgst', 'igst'))
    if has_tax: els.append(pair('Taxable value', format_inr(data.get('taxable', record.amount))))
    for key in ('cgst', 'sgst', 'igst'):
        if Decimal(str(data.get(key, 0))): els.append(pair(key.upper(), format_inr(data[key])))
    if Decimal(str(data.get('round_off', 0))): els.append(pair('Round off', format_inr(data['round_off'])))
    els.append(pair('TOTAL', 'INR ' + format_inr(record.amount), bold, grand))
    payable = max(Decimal('0'), record.amount - paid)
    if record.kind == 'pos' and data.get('payment_account', 'cash') == 'cash':
        els += [pair('Cash tendered', format_inr(data.get('tender_amount', record.amount))), pair('Change', format_inr(data.get('change_amount', '0')))]
    elif record.kind == 'pos':
        els.append(pair('Paid by', 'Bank / UPI / card'))
    elif paid: els.append(pair('Paid', format_inr(paid)))
    if record.kind != 'pos' and payable > 0: els.append(pair('Balance due', 'INR ' + format_inr(payable), bold, right_bold))
    if branding.get('upi_id') and record.kind in {'sales_invoice', 'estimate', 'proforma', 'pos'} and payable > 0:
        uri = 'upi://pay?' + urlencode({'pa': branding['upi_id'], 'pn': supplier.get('name', ''), 'cu': 'INR', 'am': format(payable, '.2f')})
        code = QrCodeWidget(uri); x0, y0, x1, y1 = code.getBounds(); side = min(width * .62, 34 * mm)
        drawing = Drawing(side, side, transform=[side / (x1 - x0), 0, 0, side / (y1 - y0), 0, 0]); drawing.add(code); drawing.hAlign = 'CENTER'
        els += [Spacer(1, 4), p('Scan to pay with UPI', center_bold), drawing, p(branding['upi_id'], center)]
    if branding.get('notes'): els += [Spacer(1, 3), p(branding['notes'], center)]
    els += [Spacer(1, 3), p('Thank you! Visit again.', center_bold)]
    height = 2 * margin + sum(e.wrap(width, 10_000)[1] + e.getSpaceBefore() + e.getSpaceAfter() for e in els) + 6 * mm
    out = io.BytesIO()
    SimpleDocTemplate(out, pagesize=(roll, height), leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin, title=title).build(els)
    return out.getvalue()
