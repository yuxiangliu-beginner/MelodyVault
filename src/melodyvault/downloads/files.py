"""No lossy conversion. Verify bytes and media before publishing without overwrite."""
import hashlib,os,re,wave,shutil
from pathlib import Path
from melodyvault.downloads.models import DownloadError


def safe_component(text):
    text=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(text)).strip(' .')[:65].rstrip(' .') or '_'
    if text.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:text='_'+text
    if text in {'.','..'}:text='_'
    return text


def contained(root,*parts):
    root=Path(root).resolve();path=root.joinpath(*parts).resolve()
    if not path.is_relative_to(root) or path==root:raise DownloadError('UNSAFE_PATH','归档路径超出下载目录')
    if os.name=='nt' and len(str(path))>245:raise DownloadError('UNSAFE_PATH','下载目录过长，请选择更短的目录')
    return path


def hashes(path):
    values={name:hashlib.new(name) for name in ('sha256','sha1','md5')}
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            for digest in values.values():digest.update(block)
    return {name:d.hexdigest() for name,d in values.items()}


def verify_file(path,candidate,max_bytes):
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.wave import WAVE
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    from mutagen.mp4 import MP4
    from mutagen.aac import AAC
    path=Path(path);size=path.stat().st_size
    if not 0<size<=max_bytes:raise DownloadError('FILE_SIZE_MISMATCH','文件大小超出允许范围')
    if candidate.file_size and size!=candidate.file_size:raise DownloadError('FILE_SIZE_MISMATCH',f'文件字节数不符：预期{candidate.file_size}，实际{size}')
    digests=hashes(path)
    for name,expected in candidate.checksums.items():
        if name in digests and expected and expected.lower()!=digests[name]:raise DownloadError('HASH_MISMATCH',f'{name.upper()}与官方文件校验值不符')
    try:
        media=mutagen.File(path)
        # Content sniffing misses valid streams after leading padding (e.g. zero
        # bytes before the first MP3 frame). Retry with the declared format's own
        # parser; the full FFmpeg decode afterwards still has to pass.
        explicit={'mp3':MP3,'flac':FLAC,'wav':WAVE,'ogg':OggVorbis,'opus':OggOpus,'m4a':MP4,'aac':AAC}.get(candidate.file_format)
        if media is None and explicit:media=explicit(path)
        kind=next((v for t,v in ((MP3,'mp3'),(FLAC,'flac'),(WAVE,'wav'),(OggVorbis,'ogg'),(OggOpus,'opus'),(MP4,'m4a'),(AAC,'aac')) if isinstance(media,t)),None)
        if not kind or not media.info or not 0<media.info.length<24*3600:raise ValueError()
        if kind=='m4a' and not str(media.info.codec).startswith(('mp4a','alac')):raise ValueError()
        duration=float(media.info.length)
        if kind=='wav':
            with wave.open(str(path),'rb') as wav:
                expected=wav.getnframes()*wav.getnchannels()*wav.getsampwidth()
                actual=0
                while True:
                    block=wav.readframes(65536)
                    if not block:break
                    actual+=len(block)
                if actual!=expected:raise DownloadError('INCOMPLETE_AUDIO','WAV声明的采样数据不完整')
    except DownloadError:raise
    except Exception:raise DownloadError('MEDIA_FORMAT_INVALID','媒体解析失败或不是允许的完整音频格式') from None
    # Opus commonly arrives as audio/ogg: Ogg is its container, not a promise
    # that the codec is Vorbis. Bytes remain unchanged; report the parsed codec.
    if candidate.file_format and kind!=candidate.file_format and not (candidate.file_format=='ogg' and kind=='opus'):
        raise DownloadError('MEDIA_FORMAT_INVALID','实际音频格式与来源声明不符')
    if candidate.duration and abs(duration-candidate.duration)>max(.05,min(2.,candidate.duration*.02)):
        raise DownloadError('INCOMPLETE_AUDIO',f'实际时长{duration:.3f}秒与核验时长{candidate.duration:.3f}秒不符')
    return {'format':kind,'bytes':size,'duration':duration,**digests}


def check_space(directory,remaining):
    if shutil.disk_usage(directory).free<remaining+16*1024*1024:raise DownloadError('DISK_FULL','剩余磁盘空间不足（含16MiB安全余量）')


def decode_file(path,check=lambda:None,timeout=90):
    """Decode every audio frame before publication; cancellable and bounded."""
    import subprocess,time
    executable=shutil.which('ffmpeg')
    if not executable:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            executable=get_ffmpeg_exe()
        except (ImportError,RuntimeError):pass
    if not executable:raise DownloadError('DECODER_UNAVAILABLE','未找到 FFmpeg，无法完成音频完整性验证')
    check();deadline=time.monotonic()+timeout
    process=subprocess.Popen([executable,'-nostdin','-v','error','-xerror','-i',str(path),'-map','0:a:0','-f','null','-'],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        while True:
            check()
            if time.monotonic()>deadline:raise DownloadError('MEDIA_DECODE_TIMEOUT','音频完整解码超时，请稍后重试')
            try:
                _,errors=process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:continue
        check()
        if process.returncode:
            import logging
            logging.getLogger(__name__).warning('FFmpeg validation failed: %s',errors.decode('utf-8','replace')[:2000])
            raise DownloadError('MEDIA_DECODE_FAILED','音频无法完整解码，未发布到音乐库')
        return {'decoder':'ffmpeg','full_decode':True}
    finally:
        if process.poll() is None:process.kill()
        process.communicate()


def publish(part,root,candidate,verified):
    from melodyvault.catalog.normalize import display_name
    artist=safe_component(display_name(candidate.artist_name) if candidate.artist_name.strip() else '未知歌手')
    target=contained(root,artist)
    target.mkdir(parents=True,exist_ok=True)
    basename=f'{artist} - {safe_component(candidate.title)}'
    # Another recording may already use this display name (two uploads of the same
    # song). Keep both as "name (2)", ...; an identical file is reused; nothing is overwritten.
    for number in range(1,100):
        final=contained(root,artist,f'{basename}.{verified["format"]}' if number==1 else f'{basename} ({number}).{verified["format"]}')
        if final.exists():
            if final.is_file() and hashes(final)['sha256']==verified['sha256']:return final
            continue
        # Both paths are on the same volume. Windows rename fails if destination exists.
        try:
            if os.name=='nt':os.rename(part,final)
            else:os.link(part,final);Path(part).unlink()
        except FileExistsError:continue
        return final
    raise DownloadError('FILE_CONFLICT','同名文件过多，未覆盖任何已有文件')
