"""Compile production Windows and Android CSV parsers against bank input vectors."""
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);p.add_argument('--dotnet',default='dotnet');args=p.parse_args()
valid='\ufeffdate,description,reference,amount\r\n2026-11-12,"Receipt, with ""quote""\r\nnext line",00123,100\r\n'
expected='Receipt, with "quote"\r\nnext line'
bad=['date,description,amount\n2026-11-12,"Receipt"junk,100','date,description,amount\n2026-11-12,Rec"eipt,100','date,description,amount\n2026-11-12,"Receipt,100']
q=lambda s:json.dumps(s,ensure_ascii=True)
with tempfile.TemporaryDirectory(prefix='apex-bank-csv-') as folder:
 d=Path(folder)
 kotlin='''import com.apexbooks.accounting.data.Csv
fun reject(block:()->Unit){check(runCatching(block).isFailure)}
fun main(){
 val rows=Csv.parse(Csv.decode(VALID.toByteArray(Charsets.UTF_8)))
 check(rows.size==2&&rows[1][1]==EXPECTED&&rows[1][2]=="00123"&&rows[1][3]=="100")
 BAD
 reject{Csv.decode(byteArrayOf(65,0x96.toByte(),66))}
 for(ending in listOf("\\r","\\n","\\r\\n")){check(Csv.parse("date,description,amount"+ending+"2026-11-12,Receipt,100"+ending).size==2)}
 check(Csv.amount("(1,234.50)")=="-1234.50");check(Csv.amount("100 Dr")=="-100");check(Csv.amount("100 Cr")=="100")
 println("PASS Android production bank CSV: quotes/UTF-8, BOM/CRLF/doubled quotes, leading zeros, line endings and signed amounts")
}'''.replace('VALID',q(valid)).replace('EXPECTED',q(expected)).replace('BAD','\n'.join('reject{Csv.parse('+q(x)+')}' for x in bad))
 (d/'Proof.kt').write_text(kotlin)
 run_proof(args,[root/'native/android/app/src/main/java/com/apexbooks/accounting/data/Csv.kt',d/'Proof.kt'],d)
 cs='''using ApexBooks_Windows.Services;using System.Text;
class Program {
 static void Check(bool x){if(!x)throw new Exception("Failed");}
 static void Reject(Action f){try{f();}catch{return;}throw new Exception("Expected rejection");}
 static void Main(){var rows=Csv.Parse(Csv.Decode(Encoding.UTF8.GetBytes(VALID)));Check(rows.Count==2&&rows[1][1]==EXPECTED&&rows[1][2]=="00123"&&rows[1][3]=="100");
 BAD
 Reject(()=>Csv.Decode(new byte[]{65,0x96,66}));
 foreach(var ending in new[]{"\\r","\\n","\\r\\n"})Check(Csv.Parse("date,description,amount"+ending+"2026-11-12,Receipt,100"+ending).Count==2);
 Check(Csv.Money("(1,234.50)")=="-1234.50");Check(Csv.Money("100 Dr")=="-100");Check(Csv.Money("100 Cr")=="100");
 Console.WriteLine("PASS Windows production bank CSV: quotes/UTF-8, BOM/CRLF/doubled quotes, leading zeros, line endings and signed amounts");
 }}'''.replace('VALID',q(valid)).replace('EXPECTED',q(expected)).replace('BAD','\n'.join('Reject(()=>Csv.Parse('+q(x)+'));' for x in bad))
 (d/'Program.cs').write_text(cs)
 (d/'Proof.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup><ItemGroup><Compile Include="'+str(root/'native/windows/Services/Csv.cs')+'" /></ItemGroup></Project>')
 subprocess.run([args.dotnet,'run','--project',str(d/'Proof.csproj')],check=True,env={**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_GENERATE_ASPNET_CERTIFICATE':'false','DOTNET_CLI_HOME':str(d/'home')})
