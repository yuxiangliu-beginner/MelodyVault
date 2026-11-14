"""Kill only this harness's own download child, then resume in a fresh process."""
import argparse,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
from melodyvault.database.downloads import DownloadRepository
from melodyvault.downloads.manager import DownloadManager
from melodyvault.downloads.models import DownloadSettings


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-downloads',action='store_true');p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--target-report',type=Path,default=Path('.local/reports/phase3b/native-validator/native-gui.json'));p.add_argument('--stage',choices=['parent','child','resume'],default='parent');args=p.parse_args()
    if not args.execute_downloads:raise SystemExit('Explicit QA download opt-in required')
    root=args.report_dir.resolve();path=root/'qa.sqlite3';report_path=root/'restart.json'
    if args.stage!='parent':
        report=json.loads(report_path.read_text(encoding='utf-8'));repo=DownloadRepository(path);manager=DownloadManager(repo)
        if args.stage=='resume':
            manager.recover();recovered=repo.get(report['job_id']);assert recovered['state']=='PAUSED' and recovered['reason_code']=='RESTART_RECOVERY'
            report['recovered']={k:recovered[k] for k in ('state','reason_code','bytes_received','part_path')};report['resume_pid']=os.getpid()
            settings=repo.settings();settings.speed_limit=0;repo.save_settings(settings);manager.resume(report['job_id']);manager.run()
            row=repo.get(report['job_id']);report['completed']=row;report['resume_evidence']=[e for e in repo.evidence_rows(row['id']) if e['step']=='resume'];report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            assert row['state']=='COMPLETED' and any(e['decision']=='RANGE_ACCEPTED' for e in report['resume_evidence'])
        else:manager.run()
        return
    root.mkdir(parents=True,exist_ok=True)
    if path.exists():raise SystemExit('Refuse to overwrite existing QA data')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(path) as dst:src.backup(dst)
    repo=DownloadRepository(path);settings=DownloadSettings(directory=str(root/'music'),automatic_download=True,max_concurrent=1,speed_limit=128*1024)
    repo.save_settings(settings)
    source=json.loads(args.target_report.read_text(encoding='utf-8'))['completed']['target']
    jid=repo.enqueue(source,settings,candidate=source['source_hint']);report={'job_id':jid,'parent_pid':os.getpid()};report_path.write_text(json.dumps(report),encoding='utf-8')
    command=[sys.executable,str(Path(__file__).resolve()),'--execute-downloads','--report-dir',str(root)]
    with (root/'child.log').open('w',encoding='utf-8') as out:
        child=subprocess.Popen([*command,'--stage','child'],stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                row=repo.get(jid)
                if row['state']=='DOWNLOADING' and row['bytes_received']>=131072:break
                if child.poll() is not None:raise RuntimeError('Download child exited before fault injection; see child.log')
                time.sleep(.05)
            else:raise TimeoutError('No real persisted partial download')
            # child is the exact Popen object created by this harness, not an
            # existing user app or a discovered process. Windows kill is abrupt.
            child.kill();child.wait(timeout=10)
            interrupted=repo.get(jid);assert interrupted['state']=='DOWNLOADING'
            report.update(killed_child_pid=child.pid,interrupted_state=interrupted['state'],persisted_bytes=interrupted['bytes_received'],part_bytes=Path(interrupted['part_path']).stat().st_size)
            report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=10)
    resumed=subprocess.run([*command,'--stage','resume'],capture_output=True,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (root/'resume.log').write_text(resumed.stdout+'\n'+resumed.stderr,encoding='utf-8');assert resumed.returncode==0,'Resume failed; see resume.log'
    report=json.loads(report_path.read_text(encoding='utf-8'));assert report['resume_pid']!=report['killed_child_pid']
    print('REAL_PROCESS_RESTART_OK',report['killed_child_pid'],report['resume_pid'],report['completed']['result']['sha256'],flush=True)


if __name__=='__main__':main()
