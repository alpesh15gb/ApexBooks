"""Complete ZIP format: bounded financial JSON plus immutable binary entries."""
import base64,hashlib,json,re,stat,zipfile,struct
from uuid import UUID
from datetime import datetime
from bounded_json import loads as bounded_loads
import attachment_limits as limits
from document_attachments import validate_content,validate_filename
from backup_transport import DatabaseChunkReader


def read_bounded(entry,maximum):
    content=bytearray()
    while True:
        part=entry.read(min(65536,maximum+1-len(content)))
        if not part:break
        content.extend(part)
        if len(content)>maximum:raise ValueError('Archive entry exceeds its expanded byte limit')
    return bytes(content)

def preflight_zip(reader):
    """Bound central-directory allocation and entry count before ZipFile parses it."""
    total=reader.job.byte_count
    if total<22:raise ValueError('Incomplete ZIP directory')
    tail_size=min(total,65535+22);reader.seek(total-tail_size);tail=reader.read(tail_size)
    position=tail.rfind(b'PK\x05\x06')
    if position<0 or position+22>len(tail):raise ValueError('Missing ZIP end directory')
    _,disk,central_disk,disk_entries,entries,directory_size,directory_offset,comment_size=struct.unpack_from('<4s4H2IH',tail,position)
    end_offset=total-tail_size+position
    if position+22+comment_size!=len(tail):raise ValueError('ZIP trailing data or invalid comment')
    if disk or central_disk or disk_entries!=entries:raise ValueError('Multipart ZIP files are not supported')
    if entries==65535 or directory_size==0xffffffff or directory_offset==0xffffffff or tail[max(0,position-20):position-16]==b'PK\x06\x07':raise ValueError('ZIP64 is not supported for bounded company backups')
    if not 1<=entries<=limits.MAX_FILES_PER_COMPANY+1 or directory_size>131072 or directory_size<46*entries:raise ValueError('ZIP directory exceeds entry or byte limits')
    if directory_offset+directory_size!=end_offset:raise ValueError('Invalid ZIP directory bounds')
    reader.seek(directory_offset);directory=reader.read(directory_size);offset=0;names=set()
    for _ in range(entries):
        if offset+46>len(directory) or directory[offset:offset+4]!=b'PK\x01\x02':raise ValueError('Invalid ZIP directory entry')
        name_size,extra_size,entry_comment_size=struct.unpack_from('<3H',directory,offset+28)
        disk_start=struct.unpack_from('<H',directory,offset+34)[0]
        packed,expanded=struct.unpack_from('<2I',directory,offset+20)
        local_offset=struct.unpack_from('<I',directory,offset+42)[0]
        end=offset+46+name_size+extra_size+entry_comment_size
        if not 1<=name_size<=80 or extra_size>4096 or end>len(directory) or disk_start or local_offset>=directory_offset:raise ValueError('Invalid ZIP directory field')
        if packed==0xffffffff or expanded==0xffffffff or local_offset==0xffffffff:raise ValueError('ZIP64 is not supported')
        name=directory[offset+46:offset+46+name_size]
        if name in names or not (name==b'company.json' or re.fullmatch(rb'attachments/[a-f0-9-]{36}\.bin',name)):raise ValueError('Unsupported or duplicate ZIP entry name')
        names.add(name)
        extra=directory[offset+46+name_size:offset+46+name_size+extra_size];index=0
        while index<len(extra):
            if index+4>len(extra):raise ValueError('Invalid ZIP extra field')
            tag,size=struct.unpack_from('<2H',extra,index);index+=4
            if tag==1 or index+size>len(extra):raise ValueError('Unsupported ZIP64 or invalid extra field')
            index+=size
        offset=end
    if offset!=len(directory):raise ValueError('ZIP directory entry count mismatch')
    reader.seek(0)

class CompleteArchive:
    def __init__(self,m,session,job):
        self.m=m;self.session=session;self.job=job
        self.reader=DatabaseChunkReader(m,session,job)
        preflight_zip(self.reader)
        self.archive=zipfile.ZipFile(self.reader,'r')
        infos=self.archive.infolist()
        if not 1<=len(infos)<=limits.MAX_FILES_PER_COMPANY+1:raise ValueError('Archive entry count exceeds its limit')
        paths=[entry.filename for entry in infos]
        if len(set(paths))!=len(paths) or paths.count('company.json')!=1:raise ValueError('Archive has missing or duplicate entries')
        self.entries={entry.filename:entry for entry in infos}
        for entry in infos:
            if entry.flag_bits & 1 or entry.is_dir() or stat.S_ISLNK(entry.external_attr>>16) or entry.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('Unsupported archive entry')
            maximum=limits.BACKUP_COMPANY_JSON_MAX_BYTES if entry.filename=='company.json' else limits.MAX_FILE_BYTES
            if not 0<entry.file_size<=maximum or entry.compress_size>job.byte_count:raise ValueError('Archive entry size exceeds its limit')
        with self.archive.open('company.json') as stream:raw=read_bounded(stream,limits.BACKUP_COMPANY_JSON_MAX_BYTES)
        self.payload=bounded_loads(raw,reject_duplicates=True)
        if not isinstance(self.payload,dict) or self.payload.get('scope')!='single_company_data_export' or self.payload.get('schema_version')!=8:raise ValueError('Unsupported complete backup format')
        manifest=self.payload.get('attachments')
        if not isinstance(manifest,list) or len(manifest)>limits.MAX_FILES_PER_COMPANY:raise ValueError('Invalid attachment manifest')
        records={row['id']:row for row in self.payload.get('records',[]) if isinstance(row,dict) and isinstance(row.get('id'),str)}
        self.attachments=[];seen=set();per_record={};content_keys=set();total=0
        for item in manifest:
            if not isinstance(item,dict):raise ValueError('Invalid attachment manifest entry')
            aid=item.get('id');rid=item.get('record_id')
            try:
                if not isinstance(aid,str) or str(UUID(aid))!=aid:raise ValueError()
            except (ValueError,TypeError,AttributeError):raise ValueError('Invalid attachment identifier')
            path='attachments/'+aid+'.bin'
            if aid in seen or aid in records or item.get('entry')!=path or path not in self.entries:raise ValueError('Invalid attachment entry reference')
            seen.add(aid)
            if not isinstance(rid,str) or rid not in records or records[rid].get('kind') not in {'purchase_bill','expense'}:raise ValueError('Attachment target is not a purchase or expense')
            size=item.get('size_bytes');digest=item.get('sha256');mime=item.get('media_type');filename=item.get('filename')
            if isinstance(size,bool) or not isinstance(size,int) or not 0<size<=limits.MAX_FILE_BYTES or size!=self.entries[path].file_size:raise ValueError('Attachment size mismatch')
            if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid attachment checksum')
            if mime not in {'application/pdf','image/png','image/jpeg'}:raise ValueError('Unsupported attachment type')
            if validate_filename(filename,mime)!=filename:raise ValueError('Attachment filename must have its canonical safe extension')
            if not isinstance(item.get('is_archived',False),bool):raise ValueError('Invalid attachment archive state')
            version=item.get('version',0)
            if isinstance(version,bool) or not isinstance(version,int) or not 0<=version<=2147483647:raise ValueError('Invalid attachment version')
            created=item.get('created_at')
            if not isinstance(created,str) or len(created)>80:raise ValueError('Invalid attachment creation time')
            datetime.fromisoformat(created)
            if (rid,digest) in content_keys:raise ValueError('Duplicate attachment content for one record')
            content_keys.add((rid,digest))
            per_record[rid]=per_record.get(rid,0)+1;total+=size
            if per_record[rid]>limits.MAX_FILES_PER_RECORD or total>limits.COMPANY_QUOTA_BYTES:raise ValueError('Attachment storage quota exceeded')
            self.attachments.append(item)
        if set(paths)!={'company.json',*(item['entry'] for item in self.attachments)}:raise ValueError('Archive contains unrecognized or unlisted entries')
        self.attachment_bytes=total
    def content(self,item):
        with self.archive.open(item['entry']) as stream:content=read_bounded(stream,limits.MAX_FILE_BYTES)
        if len(content)!=item['size_bytes'] or hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError('Attachment checksum or size mismatch')
        validate_content(content,item['media_type'])
        return content
    def validate_evidence(self):
        for item in self.attachments:self.content(item)
    def close(self):self.archive.close();self.reader.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
