"""Copy user-owned audio into a local library without mutating its source."""
import hashlib,os,tempfile,struct
from pathlib import Path
from uuid import uuid4
import mutagen
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from melodyvault.database import connect
from melodyvault.database.catalog import utc_now
from melodyvault.downloads.files import contained,safe_component
from melodyvault.catalog.normalize import display_name

FORMATS={'.mp3':'mp3','.flac':'flac','.m4a':'m4a','.wav':'wav'}

def _wav_info(path):
    """Read bounded RIFF INFO fields that Mutagen does not expose as ID3 tags."""
    tags={}
    with path.open('rb') as stream:
        header=stream.read(12)
        if len(header)!=12 or header[:4]!=b'RIFF' or header[8:]!=b'WAVE':return tags
        limit=min(path.stat().st_size,struct.unpack('<I',header[4:8])[0]+8)
        for _ in range(8192):
            if stream.tell()+8>limit:break
            chunk=stream.read(8);size=struct.unpack('<I',chunk[4:])[0];start=stream.tell();end=start+size
            if end>limit:break
            if chunk[:4]==b'LIST' and 4<=size<=1024*1024:
                data=stream.read(size)
                if data[:4]==b'INFO':
                    pos=4
                    while pos+8<=len(data):
                        key=data[pos:pos+4];length=struct.unpack('<I',data[pos+4:pos+8])[0];pos+=8
                        if pos+length>len(data):break
                        if key in {b'INAM',b'IART',b'IPRD'}:
                            raw=data[pos:pos+length].rstrip(b'\x00')
                            try:value=raw.decode('utf8')
                            except UnicodeDecodeError:value=raw.decode('cp1252',errors='replace')
                            tags[{b'INAM':'title',b'IART':'artist',b'IPRD':'album'}[key]]=value.strip()
                        pos+=length+(length%2)
            stream.seek(end+(size%2))
    return tags

def inspect_audio(path):
    path=Path(path);fmt=FORMATS.get(path.suffix.lower())
    if not fmt or not path.is_file():raise ValueError('文件不存在或格式不支持')
    media=mutagen.File(path,easy=True)
    if not isinstance(media,{'mp3':MP3,'flac':FLAC,'m4a':MP4,'wav':WAVE}[fmt]) or not media.info or media.info.length<=0:raise ValueError('无法读取音频或扩展名与格式不符')
    def tag(name):
        value=media.get(name,[]) if media.tags else []
        return str(value[0]).strip() if value else ''
    wav=_wav_info(path) if fmt=='wav' else {}
    inferred=path.stem.split(' - ',1)
    return {'path':str(path.resolve()),'title':tag('title') or wav.get('title') or inferred[-1], 'artist':tag('artist') or wav.get('artist') or (inferred[0] if len(inferred)==2 else '未知歌手'),
            'album':tag('album') or wav.get('album',''),'duration':float(media.info.length),'format':fmt}

def destination(root,item):
    artist=safe_component(display_name(item['artist']) or '未知歌手');title=safe_component(item['title'].strip())
    return contained(root,artist,artist+' - '+title+'.'+item['format'])

def recover_imports(db_path):
    from melodyvault.downloads.manager import RunLock
    with RunLock(str(db_path)+'.imports'):
        with connect(db_path) as db:db.execute("UPDATE download_jobs SET state='PAUSED',reason_code='RESTART_RECOVERY',reason='上次导入未结束，等待重新导入',updated_at=? WHERE state='DOWNLOADING' AND json_extract(target_json,'$.namespace')='local_import'",(utc_now(),))

def import_one(db_path,root,item,cancel,progress=lambda *args:None):
    source=Path(item['path']);target=destination(root,item);target.parent.mkdir(parents=True,exist_ok=True)
    if not item['title'].strip():raise ValueError('歌曲名称不能为空')
    if not source.is_file() or source.suffix.lower() not in FORMATS:raise ValueError('源文件不可用')
    temp=None
    try:
        digest=hashlib.sha256();size=0;initial=source.stat()
        with source.open('rb') as inp,tempfile.NamedTemporaryFile(dir=target.parent,prefix='.mv-import-',suffix='.part',delete=False) as out:
            temp=Path(out.name)
            while True:
                if cancel.is_set():raise InterruptedError('导入已取消')
                block=inp.read(1024*1024)
                if not block:break
                out.write(block);digest.update(block);size+=len(block);progress(size,source.stat().st_size)
        sha=digest.hexdigest()
        final=source.stat()
        if (initial.st_size,initial.st_mtime_ns)!=(final.st_size,final.st_mtime_ns) or size!=initial.st_size:raise ValueError('源文件在导入期间发生变化')
        checked={}
        def duplicate(rows):
            for row in rows:
                path=Path(row[0])
                if item.get('source_type')=='conversion' and path.resolve()==source.resolve():continue
                if not path.is_file():continue
                st=path.stat();key=(str(path),st.st_size,st.st_mtime_ns)
                if key not in checked:
                    known=hashlib.sha256()
                    with path.open('rb') as stream:
                        for chunk in iter(lambda:stream.read(1024*1024),b''):
                            if cancel.is_set():raise InterruptedError('导入已取消')
                            known.update(chunk)
                    checked[key]=known.hexdigest()
                if checked[key]==sha:return str(path)
            return None
        with connect(db_path) as db:
            existing=db.execute('SELECT path FROM personal_music WHERE sha256=? UNION ALL SELECT path FROM downloaded_files WHERE sha256=?',(sha,sha)).fetchall()
        match=duplicate(existing)
        if match:return {'state':'DUPLICATE','path':match}
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE');published=False
            try:
                existing=db.execute('SELECT path FROM personal_music WHERE sha256=? UNION ALL SELECT path FROM downloaded_files WHERE sha256=?',(sha,sha)).fetchall()
                match=duplicate(existing)
                if match:db.commit();return {'state':'DUPLICATE','path':match}
                if cancel.is_set():raise InterruptedError('导入已取消')
                if target.exists():raise FileExistsError('同名文件已存在，未覆盖')
                if os.name=='nt':os.rename(temp,target)
                else:os.link(temp,target);temp.unlink()
                temp=None;published=True
                db.execute('INSERT INTO personal_music VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (str(uuid4()),item['title'].strip(),display_name(item['artist']) or '未知歌手',item['album'],item['duration'],item['format'],str(target),size,sha,item.get('source_type','import'),utc_now()));db.commit()
            except Exception:
                db.rollback()
                if published:target.unlink(missing_ok=True)
                raise
        return {'state':'IMPORTED','path':str(target),'sha256':sha,'bytes':size}
    finally:
        if temp:temp.unlink(missing_ok=True)
