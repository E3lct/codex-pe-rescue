# Third-party notices for Windows portable builds

The portable build bundles CPython, `python-zstandard` and its statically linked
Zstandard library. Their license texts are copied into the release archive's
`licenses/` directory from the exact build environment, except for
`zstd-LICENSE.txt`, which is pinned in this source tree from the upstream
`python-zstandard` 0.25.0 source distribution. The archive also includes
PyInstaller's `COPYING.txt` for transparency about its bootloader and runtime
components.

The build script fails if required license files cannot be found. It does not
infer license text from package metadata. The project MIT license remains in the
archive as `LICENSE`; it does not replace any third-party license.
