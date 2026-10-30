"""Static local preview with byte-range support for seeking long audio tracks."""
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import argparse,functools,re

class RangeHandler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.m4a':'audio/mp4','.m4b':'audio/mp4'}
    def log_message(self,*args): pass
    def send_head(self):
        self.byte_range=None
        path=Path(self.translate_path(self.path))
        if not path.is_file():return super().send_head()
        file=path.open('rb');size=path.stat().st_size
        value=self.headers.get('Range')
        start,end=0,size-1
        if value:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',value.strip())
            if not match or (not match[1] and not match[2]):
                file.close();self.send_error(416);return None
            if match[1]:start=int(match[1]);end=min(int(match[2]),size-1) if match[2] else size-1
            else:start=max(0,size-int(match[2]))
            if start>=size or start>end:
                file.close();self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return None
            self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.byte_range=(start,end)
        else:self.send_response(200)
        self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Last-Modified',self.date_time_string(path.stat().st_mtime))
        self.end_headers();file.seek(start);return file
    def copyfile(self,source,outputfile):
        if self.byte_range is None:return super().copyfile(source,outputfile)
        remaining=self.byte_range[1]-self.byte_range[0]+1
        try:
            while remaining>0:
                chunk=source.read(min(65536,remaining))
                if not chunk:break
                outputfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8088);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'dist'
    server=ThreadingHTTPServer(('127.0.0.1',args.port),functools.partial(RangeHandler,directory=str(root)))
    print(f'Local: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
