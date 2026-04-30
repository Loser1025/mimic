"""
各 v4_modules/*.py ファイルに適切な import を付与するスクリプト。
split_v4.py の実行後に走らせること。
"""
from pathlib import Path

DST = Path(__file__).parent

IMPORTS: dict[str, str] = {
    "utils.py": """\
import threading
import time
import sys
import os
import re
import logging
import json
import traceback
import math
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
""",

    "config.py": """\
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from NEWUNI.utils import safe_print, C, log, TokenBucket
""",

    "tools.py": """\
import subprocess
import tempfile
import re
import os
import ast
import difflib
import shutil
import json
import time
import threading
import traceback
import math
import urllib.request
import urllib.error
import urllib.parse
import http.client
from pathlib import Path
from typing import Optional, Any
from concurrent.futures import ThreadPoolExecutor
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore
from NEWUNI.utils import safe_print, C, log, _try_read_file_text
from NEWUNI.config import AccountConfig
""",

    "autogit.py": """\
import subprocess
import os
import json
import threading
import traceback
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from NEWUNI.utils import safe_print, C, log
""",

    "rag.py": """\
import json
import math
import re
import ast
import os
import time
import threading
import traceback
import collections
import urllib.request
import urllib.error
import urllib.parse
import http.client
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
from concurrent.futures import ThreadPoolExecutor
from NEWUNI.utils import safe_print, C, log, _try_read_file_text
from NEWUNI.config import (AccountConfig, GEMINI_API_BASE,
                                _DEFAULT_MODEL, _EMBEDDING_MODEL, _HYDE_MODEL)
""",

    "agent.py": """\
import json
import time
import random
import threading
import traceback
import difflib
import http.client
import urllib.request
import urllib.error
import urllib.parse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from NEWUNI.utils import safe_print, C, log, TokenBucket
from NEWUNI.config import (AccountConfig, PortContext, build_port_context, render_port_context,
                                GEMINI_API_BASE)
from NEWUNI.rag import LongTermMemory, SessionRAG, ProjectRAG, _fmt_msg_for_summary
from NEWUNI.autogit import AutoGit, ReactLog
from NEWUNI.tools import ToolRegistry
""",

    "orchestrator.py": """\
import json
import time
import random
import threading
import traceback
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from NEWUNI.utils import safe_print, C, log
from NEWUNI.config import PortContext, build_port_context, render_port_context
from NEWUNI.agent import (GeminiAgent, AccountRotator, _stream_gemini_api,
                               _trim_messages_smart, _repair_message_sequence,
                               GeminiAPIError, RateLimitError, ServerError,
                               MAX_RETRIES, BASE_BACKOFF, MAX_BACKOFF, MAX_TOOL_ROUNDS,
                               TOOL_OUTPUT_LIMIT, _CACHEABLE_TOOLS, _print_write_diff)
from NEWUNI.tools import ToolRegistry, tools
from NEWUNI.autogit import AutoGit, ReactLog
from NEWUNI.rag import LongTermMemory, SessionRAG, ProjectRAG, _compress_lesson
""",

    "commands.py": """\
import json
import os
import sys
import time
import re
import threading
from pathlib import Path
from typing import Optional
from NEWUNI.utils import safe_print, C, log
from NEWUNI.tools import ExecutionRegistry
from NEWUNI.agent import GeminiAgent
""",

    "main.py": """\
import sys
import os
import json
import time
import threading
import io
import traceback
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from NEWUNI.utils import safe_print, C, log, print_ascii_art, render_markdown
from NEWUNI.config import load_config, AccountConfig
from NEWUNI.agent import GeminiAgent
from NEWUNI.tools import ToolRegistry, tools
from NEWUNI.rag import LongTermMemory
from NEWUNI.autogit import AutoGit
from NEWUNI.orchestrator import InteractiveOrchestrator, AgentOrchestrator
from NEWUNI.commands import cmd_registry
""",
}

HEADER_MARKER = "from __future__ import annotations"

for filename, imports in IMPORTS.items():
    fpath = DST / filename
    if not fpath.exists():
        print(f"  [SKIP] {filename} — not found")
        continue
    content = fpath.read_text(encoding="utf-8")
    # ヘッダー行の直後に imports を挿入
    idx = content.find(HEADER_MARKER)
    if idx == -1:
        new_content = f"from __future__ import annotations\n\n{imports}\n{content}"
    else:
        after_header = idx + len(HEADER_MARKER)
        new_content = content[:after_header] + "\n\n" + imports + content[after_header:]
    fpath.write_text(new_content, encoding="utf-8")
    print(f"  [OK] {filename}")

print("\nDone!")
