# Third-party notices

Media Collector itself is licensed under the Apache License 2.0 (see `LICENSE` and `NOTICE`). The packaged
app (`Media Collector.app`) also contains the following third-party software.

## Python runtime
The app embeds a relocatable CPython 3.13 build from the
[python-build-standalone](https://github.com/astral-sh/python-build-standalone) project, obtained through
[uv](https://github.com/astral-sh/uv). Python is licensed under the
[Python Software Foundation License](https://docs.python.org/3/license.html); the full text ships inside the
app at `Contents/Resources/engine/python/lib/python3.13/LICENSE.txt`. The distribution includes further
open-source components (for example expat, OpenSSL, SQLite, zlib, libffi) under their own permissive licenses,
which are covered by that file and the components' own notices.

## pyaaf2 1.7.1 (AAF reader and writer)
<https://github.com/markreidvfx/pyaaf2>, MIT License.

```
The MIT License (MIT)

Copyright (c) 2017 Mark Reid

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Trademarks
Adobe, Premiere Pro and After Effects are trademarks of Adobe Inc.; Final Cut Pro and macOS are trademarks of
Apple Inc.; DaVinci Resolve is a trademark of Blackmagic Design Pty Ltd; Avid is a trademark of Avid
Technology, Inc. They are named only to say which file formats Media Collector reads. Media Collector is an
independent project and is not affiliated with, endorsed by or sponsored by any of them.
