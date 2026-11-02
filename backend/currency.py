from decimal import Decimal,ROUND_HALF_UP

def format_inr(value):
    number=Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    whole,fraction=f'{abs(number):.2f}'.split('.')
    tail=whole[-3:];head=whole[:-3];groups=[]
    while head:groups.insert(0,head[-2:]);head=head[:-2]
    return ('-' if number<0 else '')+(','.join(groups+[tail]))+'.'+fraction
