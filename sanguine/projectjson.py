import re
from abc import abstractmethod

import sanguine.gitdatafile as gitdatafile
from sanguine.common import *
from sanguine.files import FileRetriever, ZeroFileRetriever
from sanguine.gitdatafile import GitDataParam, GitDataType, GitDataHandler


class GitRetrievedFileWriteHandler(GitDataHandler):
    @abstractmethod
    def legend(self) -> str:
        pass

    @abstractmethod
    def is_my_retriever(self, fr: FileRetriever) -> bool:
        pass

    @abstractmethod
    def write_line(self, writer: gitdatafile.GitDataListWriter, fr: FileRetriever) -> None:
        pass


class GitRetrievedFileReadHandler(GitDataHandler):
    retrieved_files: list[FileRetriever]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('p', GitDataType.Path, False, compress_level=0),  # no path compression for readability
        GitDataParam('s', GitDataType.Int),
        GitDataParam('h', GitDataType.Hash)
    ]

    def __init__(self, specific_fields: list[GitDataParam], files: list[FileRetriever]) -> None:
        super().__init__(specific_fields)
        self.retrieved_files = files


### specifications for Handlers (all Retrievers are known here, no need to deal with plugins)

class GitRetrievedZeroFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = []

    def __init__(self, files: list[FileRetriever]) -> None:
        super().__init__(GitRetrievedZeroFileReadHandler.SPECIFIC_FIELDS, files)

    def decompress(self, param: tuple[str | int, ...]) -> None:
        (p, s, h) = param
        assert h is None and s == 0
        self.retrieved_files.append(ZeroFileRetriever(p))


class GitRetrievedZeroFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return ''

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, ZeroFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, fr: FileRetriever) -> None:
        writer.write_line(self, (fr.rel_path, 0, None))


_write_handlers: list[GitRetrievedFileWriteHandler] = [GitRetrievedZeroFileWriteHandler()]


### GitProjectJson

class GitProjectJson:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, retrievers: list[FileRetriever]) -> None:
        rsorted: list[FileRetriever] = sorted(retrievers, key=lambda rs: rs.relative_path())
        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  files: // Legend: p=path (relative to MO2), s=size, h=hash\n')

        global _write_handlers
        for wh in _write_handlers:
            legend = wh.legend()
            if legend:
                wfile.write(
                    '         //         ' + legend + '\n')

        da = gitdatafile.GitDataList(GitRetrievedFileReadHandler.COMMON_FIELDS, _write_handlers)
        writer = gitdatafile.GitDataListWriter(da, wfile)
        writer.write_begin()
        for r in rsorted:
            handler = None
            for wh in _write_handlers:
                if wh.is_my_retriever(r):
                    assert handler is None
                    handler = wh
                    if not __debug__:
                        break
            assert handler is not None
            handler.write_line(writer, r)

        writer.write_end()
        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> list[FileRetriever]:
        retrievers: list[FileRetriever] = []

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading file_origins:  ...
        assert re.search(r'^\s*files\s*:\s*//', ln)

        handlers: list[GitRetrievedFileReadHandler] = [GitRetrievedZeroFileReadHandler(retrievers)]
        da = gitdatafile.GitDataList(GitRetrievedFileReadHandler.COMMON_FIELDS, handlers)
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return retrievers