package com.apexbooks.accounting.data

object Csv {
    fun decode(bytes:ByteArray):String = try {
        Charsets.UTF_8.newDecoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT).onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString()
    } catch(e:java.nio.charset.CharacterCodingException) {throw Exception("CSV encoding is invalid. Save the file as UTF-8 and try again.")}
    fun parse(input:String):List<List<String>> {
        val text=input.trimStart('\uFEFF');val rows=mutableListOf<List<String>>();val row=mutableListOf<String>();val cell=StringBuilder();var quoted=false;var closed=false;var line=1;var index=0
        fun finishCell(){row.add(cell.toString().trim());cell.clear();closed=false}
        fun finishRow(){finishCell();if(row.any{it.isNotEmpty()})rows.add(row.toList());row.clear()}
        while(index<text.length){val c=text[index]
            if(quoted){if(c=='"'){if(index+1<text.length&&text[index+1]=='"'){cell.append('"');index++}else{quoted=false;closed=true}}else{cell.append(c);if(c=='\n')line++}}
            else when {
                c==','->finishCell()
                c=='\r'||c=='\n'->{if(c=='\r'&&index+1<text.length&&text[index+1]=='\n')index++;finishRow();line++}
                closed->{if(c!=' '&&c!='\t')throw Exception("CSV row $line: unexpected text after a closing quote.")}
                c=='"'->{if(cell.isNotEmpty())throw Exception("CSV row $line: quote must begin a field.");quoted=true}
                else->cell.append(c)
            };index++
        }
        if(quoted)throw Exception("CSV row $line: unclosed quoted field.");finishRow();if(rows.size>5001)throw Exception("Import at most 5,000 transactions at a time.");return rows
    }
    fun validateColumns(table:List<List<String>>,headers:List<String>,supported:Set<String>){
        val named=headers.filter{it.isNotEmpty()};if(named.distinct().size!=named.size)throw Exception("CSV headers must be unique.")
        table.drop(1).forEachIndexed{i,row->row.forEachIndexed{j,value->if(value.isNotEmpty()&&(j>=headers.size||headers[j].isEmpty()||headers[j] !in supported))throw Exception("CSV row ${i+2}, column ${j+1}: populated column has no supported header.")}}
    }
    fun boolean(value:String):Boolean=when(value.trim().lowercase()){"true","1","yes"->true;"","false","0","no"->false;else->throw Exception("CSV track_stock must be true/false, yes/no or 1/0.")}
    fun amount(text:String):String {if(text.isBlank()||text.trim()=="-")return "0";var value=text.trim().replace(",","").replace("₹","").replace("INR","",true);val negative=value.startsWith('(')&&value.endsWith(')')||value.endsWith("Dr",true);value=value.trim('(',')');if(value.endsWith("Dr",true)||value.endsWith("Cr",true))value=value.dropLast(2).trim();val decimal=value.toBigDecimalOrNull()?:throw Exception("Invalid amount: $text");return (if(negative)-decimal.abs()else decimal).toPlainString()}
}
