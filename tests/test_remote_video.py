from melodyvault.downloads.remote_video import CommonsVideoWorker

def test_remote_video_rejects_unapproved_url_without_network(tmp_path):
    worker=CommonsVideoWorker('https://example.org/video.mp4',tmp_path);errors=[]
    worker.failed.connect(errors.append);worker.run()
    assert errors and '仅支持 Wikimedia Commons' in errors[0]
    assert not list(tmp_path.iterdir())
