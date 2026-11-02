package com.apexbooks.accounting.data

object Csv {
    fun parse(text:String):List<List<String>> {val rows=mutableListOf<List<String>>();val row=mutableListOf<String>();val cell=StringBuilder();var quoted=false;var index=0
        while(index<text.length){val c=text[index];when{c=='"'->{if(quoted&&index+1<text.length&&text[index+1]=='"'){cell.append('"');index++}else quoted=!quoted};c==','&&!quoted->{row.add(cell.toString().trim());cell.clear()};(c=='\n'||c=='\r')&&!quoted->{if(c=='\r'&&index+1<text.length&&text[index+1]=='\n')index++;row.add(cell.toString().trim());cell.clear();if(row.any{it.isNotBlank()})rows.add(row.toList());row.clear()};else->cell.append(c)};index++}
        if(quoted)throw Exception("The CSV contains an unclosed quoted field.");row.add(cell.toString().trim());if(row.any{it.isNotBlank()})rows.add(row);if(rows.size>5001)throw Exception("Import at most 5,000 transactions at a time.");return rows.mapIndexed{i,r->if(i==0)r.mapIndexed{j,s->if(j==0)s.trimStart('\uFEFF')else s}else r}}
    fun amount(text:String):String {if(text.isBlank()||text.trim()=="-")return "0";var value=text.trim().replace(",","").replace("₹","").replace("INR","",true);val negative=value.startsWith('(')&&value.endsWith(')')||value.endsWith("Dr",true);value=value.trim('(',')');if(value.endsWith("Dr",true)||value.endsWith("Cr",true))value=value.dropLast(2).trim();val decimal=value.toBigDecimalOrNull()?:throw Exception("Invalid amount: $text");return (if(negative)-decimal.abs()else decimal).toPlainString()}
}
