"""Own HTTP-range ZIP reader. ZIP entry CRC is checked by Python zipfile."""
import io, pathlib, requests, re, time

class RangeReader(io.RawIOBase):
    BLOCK = 2*1024*1024
    def __init__(self, url, folder):
        self.url=url; self.folder=pathlib.Path(folder); self.folder.mkdir(parents=True,exist_ok=True)
        self.session=requests.Session(); self.pos=0; self.network_bytes=0
        r=self.session.head(url,headers={'Range':'bytes=0-0'},timeout=30); r.raise_for_status()
        cr=r.headers.get('Content-Range','')
        m=re.fullmatch(r'bytes 0-0/(\d+)',cr)
        if m: self.size=int(m.group(1))
        else:
            self.size=int(r.headers['Content-Length'])
        if self.size<1000: raise ValueError('Invalid archive size')
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        if whence==1: offset+=self.pos
        elif whence==2: offset+=self.size
        if offset<0: raise ValueError('negative seek')
        self.pos=offset; return offset
    def block(self, i):
        p=self.folder/f'{i}.bin'; start=i*self.BLOCK; end=min(start+self.BLOCK,self.size)-1
        if p.exists():
            data=p.read_bytes()
            if len(data)!=end-start+1: raise ValueError('Invalid cached block')
            return data
        for attempt in range(4):
            try:
                with self.session.get(self.url,headers={'Range':f'bytes={start}-{end}'},timeout=(15,60),stream=True) as r:
                    r.raise_for_status()
                    if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.size}':
                        raise ValueError(f'Unexpected HTTP range: {r.status_code} {r.headers.get("Content-Range")}')
                    data=r.content
                break
            except requests.RequestException:
                if attempt==3:raise
                time.sleep(attempt+1)
        if len(data)!=end-start+1: raise ValueError('Truncated range')
        self.network_bytes+=len(data); p.write_bytes(data)
        return data
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        n=min(n,self.size-self.pos); chunks=[]
        while n>0:
            i,j=divmod(self.pos,self.BLOCK); b=self.block(i)[j:j+n]
            if not b:raise ValueError('Empty archive range')
            chunks.append(b);self.pos+=len(b);n-=len(b)
        return b''.join(chunks)
