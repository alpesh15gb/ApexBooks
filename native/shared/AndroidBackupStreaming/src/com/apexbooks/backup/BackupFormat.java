package com.apexbooks.backup;

import com.fasterxml.jackson.core.*;
import java.io.*;
import java.util.zip.GZIPInputStream;

/** Header/schema routing only. ZIP contents remain untrusted until bounded server preflight. */
public final class BackupFormat {
    public enum Kind { ENCRYPTED_V1, LEGACY_JSON, LEGACY_GZIP, ZIP_ARCHIVE }
    private BackupFormat(){}
    public static Kind inspect(File file,long expandedJsonLimit)throws IOException {
        if(expandedJsonLimit<1||expandedJsonLimit>50_000_000)throw new IOException("Invalid JSON budget");
        try(BufferedInputStream raw=new BufferedInputStream(new FileInputStream(file))){
            raw.mark(8);int first=raw.read(),second=raw.read();raw.reset();
            if(first=='P'&&second=='K')return Kind.ZIP_ARCHIVE; // Never extract/render local untrusted ZIP entries.
            boolean gzip=first==31&&second==139;
            InputStream source=gzip?new GZIPInputStream(raw):raw;
            InputStream bounded=new FilterInputStream(source){long count;
                private void add(int n)throws IOException{if(n>0&&(count+=n)>expandedJsonLimit)throw new IOException("Expanded financial JSON exceeds its limit");}
                @Override public int read()throws IOException{int n=in.read();add(n<0?0:1);return n;}
                @Override public int read(byte[] b,int o,int n)throws IOException{int size=in.read(b,o,(int)Math.min(n,expandedJsonLimit-count+1));add(size);return size;}
            };
            JsonFactory factory=JsonFactory.builder().streamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(200).maxStringLength(1024).maxNameLength(512).maxNumberLength(100).build()).enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build();
            try(JsonParser json=factory.createParser(bounded)){
                if(json.nextToken()!=JsonToken.START_OBJECT)throw new IOException("Choose a supported portable backup");
                String scope=null;int schema=-1;
                while(json.nextToken()!=JsonToken.END_OBJECT){
                    if(json.currentToken()!=JsonToken.FIELD_NAME)throw new IOException("Invalid backup JSON");
                    String name=json.currentName();JsonToken token=json.nextToken();
                    if(name.equals("format")&&token==JsonToken.VALUE_STRING&&json.getText().equals("apex-encrypted-backup"))return Kind.ENCRYPTED_V1;
                    if(name.equals("ciphertext"))return Kind.ENCRYPTED_V1; // Strict encrypted parser must authenticate it; never upload wrapper.
                    if(name.equals("scope")&&token==JsonToken.VALUE_STRING)scope=json.getText();
                    else if(name.equals("schema_version")&&token==JsonToken.VALUE_NUMBER_INT)schema=json.getIntValue();
                    else json.skipChildren();
                }
                if(json.nextToken()!=null||!"single_company_data_export".equals(scope)||(schema!=6&&schema!=7))throw new IOException("Unsupported legacy schema. Complete schema8 backups must be ZIP archives.");
                return gzip?Kind.LEGACY_GZIP:Kind.LEGACY_JSON;
            }
        }
    }
}
