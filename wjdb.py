import sqlite3
import gzip
import os
import traceback

import binaryreader
import dbg

def openHashCache(home_dir):
    hc = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalHashCache2.sqlite')
    #vfsc = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalVFSCache5.sqlite')
    return hc.cursor()
    
class Img:
    def __init__(self,br):
        dbg.traceReader('Img:')
        self.w = br.ReadUint16()
        self.h = br.ReadUint16()
        self.mip = br.ReadByte()
        self.fmt = br.ReadByte()
        self.phash = br.ReadBytes(40)
        
    def dbg(self):
        return '{ w='+str(self.w)+' h='+str(self.h)+' mip='+str(self.mip)+' fmt='+str(self.fmt)+' phash=['+str(len(self.phash))+']}'

 
class HashedFile:
    def __init__(self,br):
        dbg.traceReader('HashedFile:')
        self.path = br.ReadString()
        self.hash = br.ReadUint64()
        if br.ReadBoolean():
            self.img = Img(br)
            # print(self.img.__dict__)
            # br.dbg()
        else:
            self.img = None
        self.size = br.ReadInt64()
        assert(self.size>=0)
        n = br.ReadInt32()
        assert(n>=0)
        self.children = []
        for i in range(0,n):
            self.children.append(HashedFile(br))
            
    def dbg(self):
        s = '{ path='+self.path+' hash='+str(self.hash)
        if self.img:
            s += ' img=' + self.img.dbg()
        if len(self.children):
            s += ' children=['
            ci = 0
            for child in self.children:
                if ci:
                    s += ','
                s += child.dbg()
                ci += 1
            s += ']'
        s += ' }'
        return s

def parseContents(hash,contents,gzipped=True):
    if gzipped:
        contents = gzip.decompress(contents)
    # print(contents)
    # print(rowi)
    # print(contents)
    try:
        br = binaryreader.BinaryReader(contents)
        
        hf = HashedFile(br)
        assert(br.isEOF())
        # print(br.contents[br.offset:])
        # print(str(hash)+':'+hf.dbg())
        return hf
    except Exception as e:
        print("Parse Exception with hash="+str(hash)+": "+str(e))
        print(traceback.format_exc())
        print(contents)
        dbg.dbgWait()
        return None

def normalizeHash(hash):
    if hash < 0:
        return hash + (1<<64)
    else:
        return hash

class ArchiveEntry:
    def __init__(self,archive_hash,intra_path,file_size,file_hash):
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.file_size = file_size
        self.file_hash = file_hash

def aEntries(paths,hf,root_archive_hash):
    aes = []
    for child in hf.children:
        cp = paths + [child.path]
        aes.append(ArchiveEntry(root_archive_hash,cp,child.size,child.hash))
        if len(child.children)>0:
            aes2 = aes + aEntries(cp,child,root_archive_hash)
            aes = aes2
            #print('NESTED:')
            #for ae in aes:
            #    print(ae.__dict__)
            #dbg.dbgWait()
    return aes

def loadVFS(allinstallfiles):
    home_dir = os.path.expanduser("~")
    con = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalVFSCache5.sqlite')
    cur = con.cursor()
    # rowi = -1
    nn = 0
    nx = 0
    archiveEntries = {}
    for row in cur.execute('SELECT Hash,Contents FROM VFSCache'): # WHERE Hash=-8778729428874073019"):
        contents = row[1]

        hf = parseContents(row[0],contents)
        nn += 1
        if hf == None:
            nx += 1
        else:
            aes = aEntries([],hf,hf.hash)
            for ae in aes:
                if archiveEntries.get(ae.file_hash) is None or allinstallfiles.get(ae.archive_hash):
                    archiveEntries[ae.file_hash]=ae
            #for child in hf.children:
            #    if len(child.children)>0:
            #        print("TODO: nested children: path="+child.path)
            #        print(child.dbg())
            #    if archiveEntries.get(child.hash)!=None:
            #        print("TODO: multiple entries for a file")
            #    archiveEntries[child.hash] = ArchiveEntry(hf.hash,child.path,child.size,child.hash)
    print('loadVFS: nn='+str(nn)+' nx='+str(nx))
    return archiveEntries

class Archive:
    def __init__(self,archive_hash,archive_modified,archive_path):
        self.archive_hash=archive_hash
        self.archive_modified=archive_modified
        self.archive_path=archive_path
        
    def eq(self,other):
        if self.archive_hash != other.archive_hash:
            return False
        if self.archive_modified != other.archive_modified:
            return False
        if self.archive_path != other.archive_path:
            return False
        return True

def loadHC():
    home_dir = os.path.expanduser("~")
    con = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalHashCache2.sqlite')
    cur = con.cursor()
    archives = {}
    nn = 0
    for row in cur.execute('SELECT Path,LastModified,Hash FROM HashCache'):
        nn += 1
        hash = normalizeHash(row[2])
        
        olda = archives.get(hash)
        newa = Archive(hash,row[1],row[0])
        if olda!=None and not olda.eq(newa):
            # print("TODO: multiple archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(newa.__dict__))
            # wait = input("Press Enter to continue.")
            pass
        else:
            archives[hash] = newa
    print('loadHC: nn='+str(nn))
    return archives
    
def findFile(chc,archives,archiveEntries,fpath):
    fpath=fpath.replace("'","''")
    chc.execute("SELECT Path,LastModified,Hash FROM HashCache WHERE Path='"+fpath.lower()+"'")
    row = chc.fetchone()
    # print(row)
    
    if row == None:
        print("WARNING: path="+fpath+" NOT FOUND")
        return None,None

    hash=normalizeHash(row[2])
    archiveEntry = archiveEntries.get(hash)
    if archiveEntry == None:
        print("WARNING: archiveEntry for path="+fpath+" with hash="+str(hash)+" NOT FOUND")
        return None,None
    #print(archiveEntry.__dict__)

    ahash = archiveEntry.archive_hash
    archive = archives.get(ahash)
    if archive == None:
        print("WARNING: archive with hash="+str(ahash)+" NOT FOUND")
        return None,None
    #print(archive.__dict__)
    return archiveEntry, archive

def findArchive(chc,archives,fpath):
    fpath=fpath.replace("'","''")
    chc.execute("SELECT Path,LastModified,Hash FROM HashCache WHERE Path='"+fpath.lower()+"'")
    row = chc.fetchone()
    # print(row)
    
    if row == None:
        print("WARNING: path="+fpath+" NOT FOUND")
        return None

    hash=normalizeHash(row[2])
    archive = archives.get(hash)
    if archive == None:
        print("WARNING: archive with hash="+str(ahash)+" NOT FOUND")
        return None
    #print(archive.__dict__)
    return archive
