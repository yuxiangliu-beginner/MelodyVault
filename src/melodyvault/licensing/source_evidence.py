"""Phase 2 license metadata checks; no download approval is issued."""
from urllib.parse import urlsplit
import re


def recognized_license(url):
    try:
        p=urlsplit(url.strip())
        if p.port not in (None,80,443):return False
    except ValueError:return False
    return p.scheme in {'http','https'} and p.hostname=='creativecommons.org' and not p.username and not p.query and bool(re.fullmatch(
        r'/(?:licenses/(?:by|by-sa|by-nc|by-nd|by-nc-sa|by-nc-nd)/(?:1\.0|2\.0|2\.5|3\.0|4\.0)(?:/[a-z]{2})?|publicdomain/zero/1\.0)/?',p.path))


def check_license(candidate,download_allowed=False,restricted=False):
    candidate.license_status='LICENSE_UNVERIFIED'
    try:
        audio=urlsplit(candidate.audio_url)
        valid_audio=audio.scheme=='https' and not audio.username and audio.port in (None,443) and (
            candidate.provider=='commons' and audio.hostname=='upload.wikimedia.org' or
            candidate.provider=='jamendo' and (audio.hostname or '').endswith('.jamendo.com'))
    except ValueError:valid_audio=False
    if restricted:
        candidate.license_status='LICENSE_UNVERIFIED';candidate.license_reason='来源含下载/使用限制，无法核验私人保存许可'
    elif not recognized_license(candidate.license_url):
        candidate.license_reason='未提供可识别的明确录音许可URL；公开可播放不是授权'
    elif candidate.provider=='archive':
        candidate.license_reason='Archive声明的许可仍无法核实上传者权利及其对具体录音的适用范围'
    elif download_allowed and valid_audio and candidate.provider in {'commons','jamendo'}:
        candidate.license_status='LICENSE_VERIFIED'
        candidate.license_reason='官方来源提供明确文件级开放许可'+('及允许下载标志' if candidate.provider=='jamendo' else '；保留署名等许可条件')+'；不等于确认原唱或下载执行授权'
    else:candidate.license_reason='缺少该具体录音允许下载/保存的明确证据'
    return candidate
