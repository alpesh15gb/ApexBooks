package com.apexbooks.backup;

import com.fasterxml.jackson.core.*;
import org.bouncycastle.crypto.engines.AESEngine;
import org.bouncycastle.crypto.modes.GCMModeCipher;
import org.bouncycastle.crypto.modes.GCMBlockCipher;
import org.bouncycastle.crypto.params.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.SecureRandom;
import java.util.*;
import java.util.function.BooleanSupplier;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

/** Existing encrypted-v1 wire format, with bounded buffers and authenticate-before-expose staging.
 * The directory MUST be app-private cache storage. Callers own/close input streams and returned files.
 * No network operations, global crypto-provider registration, or new encryption protocol.
 */
public final class StreamingEncryptedBackup {
    public static final long MAX_PLAIN_BYTES=320L*1024*1024;
    private static final int BUFFER=65536;
    private static final Set<String> FIELDS=new HashSet<>(Arrays.asList("format","version","salt","iv","ciphertext"));
    private static final JsonFactory JSON=JsonFactory.builder()
        .streamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(4).maxStringLength(1024).maxNameLength(64).maxNumberLength(4).build())
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build();
    private StreamingEncryptedBackup(){}
    public static final class PrivateFile implements AutoCloseable {
        private final File file; private boolean closed;
        private PrivateFile(File file){this.file=file;}
        public File file(){if(closed)throw new IllegalStateException("Backup staging is closed");return file;}
        @Override public void close() throws IOException {if(!closed){Files.deleteIfExists(file.toPath());closed=true;}}
    }
    private static File temporary(File directory)throws IOException {
        if(!directory.isDirectory())throw new IOException("An existing app-private staging directory is required");
        return Files.createTempFile(directory.toPath(),"apex-backup-",".part").toFile();
    }
    private static void check(BooleanSupplier cancelled)throws InterruptedIOException {
        if(Thread.currentThread().isInterrupted()||cancelled.getAsBoolean())throw new InterruptedIOException("Backup operation cancelled");
    }
    private static long limit(long maximum){if(maximum<1||maximum>MAX_PLAIN_BYTES)throw new IllegalArgumentException("Unsupported backup byte budget");return maximum;}
    private static byte[] derive(char[] password,byte[] salt)throws Exception {
        PBEKeySpec spec=new PBEKeySpec(password,salt,250000,256);
        try{return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();}finally{spec.clearPassword();}
    }
    private static GCMModeCipher cipher(boolean encrypt,byte[] key,byte[] iv){
        GCMModeCipher cipher=GCMBlockCipher.newInstance(AESEngine.newInstance());
        cipher.init(encrypt,new AEADParameters(new KeyParameter(key),128,iv));return cipher;
    }
    private static final class BudgetInput extends FilterInputStream {
        private final long maximum;private long count;private final BooleanSupplier cancelled;
        BudgetInput(InputStream in,long maximum,BooleanSupplier cancelled){super(in);this.maximum=maximum;this.cancelled=cancelled;}
        private void add(int n)throws IOException {check(cancelled);if(n>0&&(count+=n)>maximum)throw new IOException("Backup exceeds the supported byte budget");}
        @Override public int read()throws IOException{check(cancelled);int v=in.read();add(v<0?0:1);return v;}
        @Override public int read(byte[] b,int o,int n)throws IOException{check(cancelled);int v=in.read(b,o,(int)Math.min(n,maximum-count+1));add(v);return v;}
        @Override public void close(){} // caller owns the selected source
    }
    private static final class BudgetOutput extends FilterOutputStream {
        private final long maximum;private long count;private final BooleanSupplier cancelled;
        BudgetOutput(OutputStream out,long maximum,BooleanSupplier cancelled){super(out);this.maximum=maximum;this.cancelled=cancelled;}
        @Override public void write(int value)throws IOException {check(cancelled);if(++count>maximum)throw new IOException("Backup exceeds the supported byte budget");out.write(value);}
        @Override public void write(byte[] b,int o,int n)throws IOException {check(cancelled);if((count+=n)>maximum)throw new IOException("Backup exceeds the supported byte budget");out.write(b,o,n);}
    }
    private static void transform(InputStream source,File destination,boolean encrypt,byte[] key,byte[] iv,long maximum,BooleanSupplier cancelled)throws Exception {
        GCMModeCipher cipher=cipher(encrypt,key,iv);byte[] input=new byte[BUFFER],output=new byte[BUFFER+32];
        try(OutputStream target=new BudgetOutput(new FileOutputStream(destination),maximum,cancelled)){
            int n;while((n=source.read(input))!=-1){check(cancelled);int size=cipher.processBytes(input,0,n,output,0);target.write(output,0,size);}
            check(cancelled);int size=cipher.doFinal(output,0);target.write(output,0,size);check(cancelled);
        }finally{Arrays.fill(input,(byte)0);Arrays.fill(output,(byte)0);}
    }
    public static PrivateFile encrypt(InputStream source,char[] password,File privateDirectory,long maximum,BooleanSupplier cancelled)throws Exception {
        limit(maximum);if(password.length<12)throw new IllegalArgumentException("Use a password of at least 12 characters");
        File ciphertext=temporary(privateDirectory),envelope=null;byte[] salt=new byte[16],iv=new byte[12],key=null;boolean success=false;
        try{
            SecureRandom random=new SecureRandom();random.nextBytes(salt);random.nextBytes(iv);check(cancelled);key=derive(password,salt);check(cancelled);
            transform(new BudgetInput(source,maximum,cancelled),ciphertext,true,key,iv,maximum+16,cancelled);
            envelope=temporary(privateDirectory);
            try(JsonGenerator json=JSON.createGenerator(new BudgetOutput(new FileOutputStream(envelope),(maximum+16)*4/3+16384,cancelled));InputStream bytes=new FileInputStream(ciphertext)){
                json.writeStartObject();json.writeStringField("format","apex-encrypted-backup");json.writeNumberField("version",1);
                json.writeStringField("salt",Base64.getEncoder().encodeToString(salt));json.writeStringField("iv",Base64.getEncoder().encodeToString(iv));
                json.writeFieldName("ciphertext");json.writeBinary(Base64Variants.MIME_NO_LINEFEEDS,new BudgetInput(bytes,maximum+16,cancelled),(int)ciphertext.length());json.writeEndObject();
            }
            check(cancelled);Files.deleteIfExists(ciphertext.toPath());success=true;return new PrivateFile(envelope);
        }finally{if(key!=null)Arrays.fill(key,(byte)0);try{Files.deleteIfExists(ciphertext.toPath());}finally{if(!success&&envelope!=null)Files.deleteIfExists(envelope.toPath());}}
    }
    public static PrivateFile decrypt(InputStream source,char[] password,File privateDirectory,long maximum,BooleanSupplier cancelled)throws Exception {
        limit(maximum);File ciphertext=temporary(privateDirectory),plaintext=null;byte[] key=null;boolean success=false;
        try{
            String format=null,saltText=null,ivText=null;int version=-1;Set<String> seen=new HashSet<>();
            try(JsonParser json=JSON.createParser(new BudgetInput(source,((maximum+18)/3)*4*6+16384,cancelled))){
                if(json.nextToken()!=JsonToken.START_OBJECT)throw new IOException("Invalid encrypted backup envelope");
                while(json.nextToken()!=JsonToken.END_OBJECT){
                    check(cancelled);if(json.currentToken()!=JsonToken.FIELD_NAME)throw new IOException("Invalid encrypted backup field");
                    String field=json.currentName();if(!FIELDS.contains(field)||!seen.add(field))throw new IOException("Unknown or duplicate encrypted backup field");
                    JsonToken token=json.nextToken();
                    if(field.equals("version")){if(token!=JsonToken.VALUE_NUMBER_INT)throw new IOException("Invalid backup version");version=json.getIntValue();}
                    else {if(token!=JsonToken.VALUE_STRING)throw new IOException("Invalid encrypted backup value");
                        if(field.equals("ciphertext")){try(OutputStream bytes=new BudgetOutput(new FileOutputStream(ciphertext),maximum+16,cancelled)){json.readBinaryValue(Base64Variants.MIME_NO_LINEFEEDS,bytes);}}
                        else {String value=json.getText();if(value.length()>128)throw new IOException("Encrypted metadata exceeds its limit");if(field.equals("format"))format=value;else if(field.equals("salt"))saltText=value;else ivText=value;}
                    }
                }
                if(json.nextToken()!=null||!seen.equals(FIELDS)||!"apex-encrypted-backup".equals(format)||version!=1)throw new IOException("Unsupported encrypted backup format");
            }
            byte[] salt=Base64.getDecoder().decode(saltText),iv=Base64.getDecoder().decode(ivText);
            if(salt.length!=16||iv.length!=12||ciphertext.length()<16)throw new IOException("Invalid encrypted backup parameters");
            check(cancelled);key=derive(password,salt);check(cancelled);plaintext=temporary(privateDirectory);
            try(InputStream bytes=new FileInputStream(ciphertext)){transform(bytes,plaintext,false,key,iv,maximum,cancelled);}
            // Only this point can hand plaintext to callers: GCM authentication has succeeded.
            check(cancelled);Files.deleteIfExists(ciphertext.toPath());success=true;return new PrivateFile(plaintext);
        }finally{if(key!=null)Arrays.fill(key,(byte)0);try{Files.deleteIfExists(ciphertext.toPath());}finally{if(!success&&plaintext!=null)Files.deleteIfExists(plaintext.toPath());}}
    }
}
